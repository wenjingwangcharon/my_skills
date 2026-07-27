import asyncio
import json
import os
from pathlib import Path
from collections import defaultdict
from playwright.async_api import async_playwright

AUTH_FILE = os.path.expanduser("~/.workbuddy/skills/beacon-data-fetcher/runtime/beacon_auth_state.json")
OUTPUT_DIR = Path(os.path.join(os.getcwd(), "beacon_output"))

WEEKS = [
    ("20260605", "20260611"),
    ("20260612", "20260618"),
    ("20260619", "20260625"),
]

CARD_DISPLAY = {
    "line_0hj7sgin": "分发放类型",
    "table_xaw0lw80": "KB激励",
    "table_ueub7onq": "SK激励",
}

DATE_KEYS = {
    "line_0hj7sgin": "dim_ds_0",
    "table_xaw0lw80": "dim_imp_date_0",
    "table_ueub7onq": "dim_imp_date_0",
}


def get_date_alias_name(card_id, qp):
    """Find the date field alias name from the query"""
    for d in qp.get("dims", []):
        if d.get("fieldKey") in ("imp_date", "ds"):
            return d.get("fieldAliasName")
    return None


def filter_by_week(objects, card_id, week_start, week_end):
    """Filter objects whose date is in [week_start, week_end]"""
    s = int(week_start)
    e = int(week_end)
    date_key = DATE_KEYS.get(card_id, "dim_imp_date_0")
    return [o for o in objects if date_key in o and s <= int(o[date_key]) <= e]


async def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    targets_path = OUTPUT_DIR / "target_card_posts.json"
    if not targets_path.exists():
        print(f"ERROR: {targets_path} not found. Run sniff_with_deep_scroll.py first.")
        return

    with open(targets_path) as f:
        targets = json.load(f)

    all_results = {}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = await browser.new_context(storage_state=AUTH_FILE)
        page = await context.new_page()
        page.set_default_timeout(120000)

        for card_id, target in targets.items():
            display_name = CARD_DISPLAY.get(card_id, card_id)
            print(f"\n=== {display_name} (card={card_id}) ===")

            # 拉 dateRange=49 拿全部 6.5-7.23 数据
            post = json.loads(target["post"])
            fk = post["query"]["queryDate"]["fieldKey"]
            post["query"]["queryDate"] = {
                "fieldKey": fk,
                "dateFormat": "relative_time",
                "dateRange": "49",
                "dateType": "day",
                "recentTimeCount": 1,
            }

            url = f"https://beacon.woa.com/api/datatalk/server/analysis/lite/model?cache_strategy=NO_CACHE&verify=1&bizId=ima&pageId=335857&card_id={card_id}"

            all_results[display_name] = {
                "card_id": card_id,
                "weeks": {},
            }

            try:
                resp = await page.request.post(
                    url, data=json.dumps(post),
                    headers={"Content-Type": "application/json"},
                    timeout=120000,
                )
                body = await resp.json()
                if body.get("code") == 0:
                    all_objects = body.get("data", {}).get("objects", [])
                    total = body.get("data", {}).get("rowCountFromMixQuery")
                    print(f"  Total: {len(all_objects)} rows (rowCount={total})")
                    if all_objects:
                        date_key = get_date_alias_name(card_id, post["query"])
                        if date_key:
                            dates = sorted({o[date_key] for o in all_objects if date_key in o})
                            print(f"  Date range: {dates[0]} to {dates[-1]} ({len(dates)} unique days)")

                    # 按周过滤
                    for week_start, week_end in WEEKS:
                        week_label = f"{week_start}-{week_end}"
                        week_objs = filter_by_week(all_objects, card_id, week_start, week_end)
                        print(f"  {week_label}: {len(week_objs)} rows")
                        all_results[display_name]["weeks"][week_label] = {
                            "objects": week_objs,
                            "rowCount": len(week_objs),
                        }
                else:
                    err = body.get("message", "?")
                    print(f"  API error: {err}")
                    for week_start, week_end in WEEKS:
                        week_label = f"{week_start}-{week_end}"
                        all_results[display_name]["weeks"][week_label] = {"error": err}
            except Exception as e:
                print(f"  Exception: {e}")
                for week_start, week_end in WEEKS:
                    week_label = f"{week_start}-{week_end}"
                    all_results[display_name]["weeks"][week_label] = {"error": str(e)}

        with open(OUTPUT_DIR / "missing_weeks_complete.json", "w") as f:
            json.dump(all_results, f, ensure_ascii=False, indent=2, default=str)
        print(f"\n\n=== Saved to {OUTPUT_DIR / 'missing_weeks_complete.json'} ===")

        print("\n=== Summary ===")
        for view_name, view_data in all_results.items():
            print(f"\n{view_name}:")
            for week, data in view_data.get("weeks", {}).items():
                if "error" in data:
                    print(f"  {week}: ERROR - {data['error']}")
                else:
                    print(f"  {week}: {data.get('rowCount', 0)} rows")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
