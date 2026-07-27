import asyncio
import json
import pandas as pd
from datetime import datetime
from pathlib import Path
from playwright.async_api import async_playwright

import os
AUTH_FILE = os.path.expanduser("~/.workbuddy/skills/beacon-data-fetcher/runtime/beacon_auth_state.json")
OUTPUT_DIR = Path(os.path.join(os.getcwd(), "beacon_output"))

CARDS = {
    "分发放类型": {
        "card_id": "line_0hj7sgin",
        "date_key": "dim_ds_0",
        "type_key": "dim_issued_reason_0",
        "type_col": "发放类型",
        "date_col": "时间",
        "type_values": {
            "创建知识号": {"应发算力券（张）": "index_coupon_should_issue_count_0",
                       "实际发放算力券（张）\t": "index_coupon_issued_cnt_0",
                       "实发算力总面额（算力）\t": "index_coupon_issued_amount_0",
                       "实际发放人数": "index_coupon_issued_uid_cnt_0",
                       "人均发放算力券（张）\t": "index_coupon_issued_cnt_per_1",
                       "人均实发算力总面额（算力）\t": "index_coupon_issued_amount_per_0"},
            "运营知识库": {"应发算力券（张）": "index_coupon_should_issue_count_0",
                       "实际发放算力券（张）\t": "index_coupon_issued_cnt_0",
                       "实发算力总面额（算力）\t": "index_coupon_issued_amount_0",
                       "实际发放人数": "index_coupon_issued_uid_cnt_0",
                       "人均发放算力券（张）\t": "index_coupon_issued_cnt_per_1",
                       "人均实发算力总面额（算力）\t": "index_coupon_issued_amount_per_0"},
            "运营skill": {"应发算力券（张）": "index_coupon_should_issue_count_0",
                       "实际发放算力券（张）\t": "index_coupon_issued_cnt_0",
                       "实发算力总面额（算力）\t": "index_coupon_issued_amount_0",
                       "实际发放人数": "index_coupon_issued_uid_cnt_0",
                       "人均发放算力券（张）\t": "index_coupon_issued_cnt_per_1",
                       "人均实发算力总面额（算力）\t": "index_coupon_issued_amount_per_0"},
        },
        "columns": ["时间", "发放类型", "应发算力券（张）", "实际发放算力券（张）\t", "实发算力总面额（算力）\t", "实际发放人数", "人均发放算力券（张）\t", "人均实发算力总面额（算力）\t"],
    },
    "KB激励": {
        "card_id": "table_xaw0lw80",
        "date_key": "dim_imp_date_0",
        "type_key": "dim_issued_count_0",
        "columns": ["日期", "应发算力券梯度（张）", "发放人数", "实际发放总算力券（张）", "实发总面额（算力）", "人均实发算力券（张）", "人均实发面额（算力）"],
    },
    "SK激励": {
        "card_id": "table_ueub7onq",
        "date_key": "dim_imp_date_0",
        "type_key": "dim_skill_issued_count_0",
        "columns": ["日期", "应发算力券梯度（张）", "发放人数", "实际发放总算力券（张）", "实发总面额（算力）", "人均实发算力券（张）", "人均实发面额（算力）"],
    },
}

KB_SK_FIELD_MAP = {
    "应发算力券梯度（张）": "dim_issued_count_0",  # or dim_skill_issued_count_0 for SK
    "发放人数": "index_coupon_management_cnt_0",
    "实际发放总算力券（张）": "index_coupon_count_day_0",
    "实发总面额（算力）": "index_coupon_management_amount_day_0",
    "人均实发算力券（张）": "index_per_coupon_count_0",
    "人均实发面额（算力）": "index_per_coupon_management_amount_0",
}

SK_FIELD_MAP = {
    "应发算力券梯度（张）": "dim_skill_issued_count_0",
    "发放人数": "index_coupon_management_skill_uid_cnt_0",
    "实际发放总算力券（张）": "index_coupon_management_skill_issued_cnt_0",
    "实发总面额（算力）": "index_coupon_management_skill_amount_day_0",
    "人均实发算力券（张）": "index_coupon_management_skill_issued_per_0",
    "人均实发面额（算力）": "index_coupon_management_skill_amount_per_0",
}


def ymd_int_to_date(ymd_int):
    """20260605 -> datetime(2026, 6, 5, 8, 0, 0) (8:00 like original)"""
    s = str(ymd_int)
    return datetime(int(s[:4]), int(s[4:6]), int(s[6:8]), 8, 0, 0)


def to_fenlei_df(objs):
    """Convert API objects to DataFrame matching the 分发放类型 xlsx format"""
    rows = []
    for o in objs:
        issued_reason = o.get("dim_issued_reason_0", "")
        ds = o.get("dim_ds_0")
        if not ds:
            continue
        row = {
            "时间": ymd_int_to_date(ds),
            "发放类型": issued_reason,
            "应发算力券（张）": o.get("index_coupon_should_issue_count_0"),
            "实际发放算力券（张）\t": o.get("index_coupon_issued_cnt_0"),
            "实发算力总面额（算力）\t": o.get("index_coupon_issued_amount_0"),
            "实际发放人数": o.get("index_coupon_issued_uid_cnt_0"),
            "人均发放算力券（张）\t": o.get("index_coupon_issued_cnt_per_1"),
            "人均实发算力总面额（算力）\t": o.get("index_coupon_issued_amount_per_0"),
        }
        rows.append(row)
    df = pd.DataFrame(rows, columns=CARDS["分发放类型"]["columns"])
    df = df.sort_values(["时间", "发放类型"]).reset_index(drop=True)
    return df


def to_kb_sk_df(objs, is_skill=False):
    """Convert API objects to DataFrame matching KB/SK xlsx format"""
    field_map = SK_FIELD_MAP if is_skill else KB_SK_FIELD_MAP
    rows = []
    for o in objs:
        date = o.get("dim_imp_date_0")
        if not date:
            continue
        row = {
            "日期": ymd_int_to_date(date),
        }
        for col, alias in field_map.items():
            row[col] = o.get(alias)
        rows.append(row)
    df = pd.DataFrame(rows, columns=CARDS["KB激励"]["columns"])
    df = df.sort_values(["日期", "应发算力券梯度（张）"]).reset_index(drop=True)
    return df


async def fetch_all(targets):
    """Fetch 49 days of data for each card, return raw API response objects"""
    results = {}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = await browser.new_context(storage_state=AUTH_FILE)
        page = await context.new_page()
        page.set_default_timeout(120000)

        for card_id, target in targets.items():
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
            resp = await page.request.post(
                url, data=json.dumps(post),
                headers={"Content-Type": "application/json"},
                timeout=120000,
            )
            body = await resp.json()
            if body.get("code") == 0:
                results[card_id] = body.get("data", {}).get("objects", [])
                print(f"  {card_id}: {len(results[card_id])} rows")
            else:
                results[card_id] = []
                print(f"  {card_id}: ERROR - {body.get('message')}")

        await browser.close()
    return results


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    targets_path = OUTPUT_DIR / "target_card_posts.json"
    if not targets_path.exists():
        print(f"ERROR: {targets_path} not found")
        return

    with open(targets_path) as f:
        targets = json.load(f)

    targets_by_id = {t["card_id"]: t for t in targets.values()}

    # 同步拉取所有 49 天数据
    print("[1] Fetching 49 days of data via API...")
    all_objects = asyncio.run(fetch_all(targets_by_id))

    # 转换为 3 个 DataFrame
    print("\n[2] Converting to DataFrames...")
    fl_objs = all_objects.get("line_0hj7sgin", [])
    kb_objs = all_objects.get("table_xaw0lw80", [])
    sk_objs = all_objects.get("table_ueub7onq", [])

    df_fl = to_fenlei_df(fl_objs)
    df_kb = to_kb_sk_df(kb_objs, is_skill=False)
    df_sk = to_kb_sk_df(sk_objs, is_skill=True)

    print(f"  分发放类型: {df_fl.shape}")
    print(f"  KB激励: {df_kb.shape}")
    print(f"  SK激励: {df_sk.shape}")

    # 保存 49 天原始数据 xlsx 到 beacon_output
    print("\n[3] Saving 49-day xlsx files...")
    fl_path = OUTPUT_DIR / "charoniwang_copilot算力报表_算力券发放-分发放类型_49d.xlsx"
    kb_path = OUTPUT_DIR / "charoniwang_copilot算力报表_算力券发放-运营知识库激励_49d.xlsx"
    sk_path = OUTPUT_DIR / "charoniwang_copilot算力报表_算力券发放-运营skill激励_49d.xlsx"
    df_fl.to_excel(fl_path, index=False)
    df_kb.to_excel(kb_path, index=False)
    df_sk.to_excel(sk_path, index=False)
    print(f"  Saved: {fl_path.name}")
    print(f"  Saved: {kb_path.name}")
    print(f"  Saved: {sk_path.name}")

    # 同时也按周分文件保存到 Downloads（让用户可以选择使用）
    print("\n[4] Saving per-week xlsx files to Downloads...")
    weeks = [
        ("20260605", "20260611"),
        ("20260612", "20260618"),
        ("20260619", "20260625"),
    ]
    downloads = Path("/Users/lalalacharon/Downloads")
    for week_start, week_end in weeks:
        fl_w = df_fl[df_fl["时间"].between(
            ymd_int_to_date(int(week_start)), ymd_int_to_date(int(week_end))
        )]
        kb_w = df_kb[df_kb["日期"].between(
            ymd_int_to_date(int(week_start)), ymd_int_to_date(int(week_end))
        )]
        sk_w = df_sk[df_sk["日期"].between(
            ymd_int_to_date(int(week_start)), ymd_int_to_date(int(week_end))
        )]
        ts = datetime.now().strftime("%Y%m%d%H%M")
        fl_w.to_excel(downloads / f"charoniwang_copilot算力报表_算力券发放-分发放类型_{week_end}_{ts}.xlsx", index=False)
        kb_w.to_excel(downloads / f"charoniwang_copilot算力报表_算力券发放-运营知识库激励_{week_end}_{ts}.xlsx", index=False)
        sk_w.to_excel(downloads / f"charoniwang_copilot算力报表_算力券发放-运营skill激励_{week_end}_{ts}.xlsx", index=False)
        print(f"  {week_start}-{week_end}: fl={len(fl_w)} rows, kb={len(kb_w)} rows, sk={len(sk_w)} rows")

    print(f"\n[5] All done. Files saved.")


if __name__ == "__main__":
    main()
