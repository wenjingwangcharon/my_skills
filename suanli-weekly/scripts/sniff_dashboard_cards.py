import asyncio
import json
import os
import re
from pathlib import Path
from playwright.async_api import async_playwright

AUTH_FILE = os.path.expanduser("~/.workbuddy/skills/beacon-data-fetcher/runtime/beacon_auth_state.json")
OUTPUT_DIR = Path(os.path.join(os.getcwd(), "beacon_output"))

TARGET_CARDS = {
    "line_0hj7sgin": "分发放类型",
    "table_xaw0lw80": "KB激励",
    "table_ueub7onq": "SK激励",
}

async def close_modal(page):
    try:
        await page.evaluate("""
            () => {
                const closers = document.querySelectorAll('.ant-modal-close, [class*="close-icon"], [class*="closeIcon"]');
                closers.forEach(c => { if (c.offsetParent !== null) c.click(); });
                const knowBtns = Array.from(document.querySelectorAll('button')).filter(b => {
                    const t = (b.textContent || '').trim();
                    return t === '关闭' || t === '关 闭' || t === '知道了' || t === '我知道了';
                });
                knowBtns.forEach(b => { if (b.offsetParent !== null) b.click(); });
            }
        """)
    except Exception:
        pass

async def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    captured = {}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = await browser.new_context(storage_state=AUTH_FILE, viewport={"width": 1600, "height": 1000})
        page = await context.new_page()
        page.set_default_timeout(90000)

        async def on_response(response):
            url = response.url
            if response.request.resource_type not in ("xhr", "fetch"):
                return
            try:
                ct = response.headers.get("content-type", "")
                if "json" not in ct:
                    return
                if "analysis/lite/model" in url:
                    card_match = re.search(r'card_id=([^&]+)', url)
                    card_id = card_match.group(1) if card_match else "?"
                    post_data = response.request.post_data
                    body = await response.json()
                    captured[card_id] = {
                        "card_id": card_id,
                        "url": url,
                        "post": post_data,
                        "code": body.get("code"),
                        "message": body.get("message"),
                        "objects_count": len(body.get("data", {}).get("objects", [])) if body.get("code") == 0 else 0,
                    }
                    if card_id in TARGET_CARDS:
                        print(f"  *** TARGET HIT: {card_id} ({TARGET_CARDS[card_id]}) code={body.get('code')} objs={captured[card_id]['objects_count']}")
            except Exception as e:
                pass

        page.on("response", on_response)

        print("[1] Navigating...")
        await page.goto("https://beacon.woa.com/datatalk/ima/dashboard/335857", wait_until="domcontentloaded")
        await page.wait_for_timeout(20000)
        await close_modal(page)
        await page.wait_for_timeout(2000)

        print("[2] Click 算力券明细...")
        await page.evaluate("""
            () => {
                const tabs = document.querySelectorAll('span.lite-publish-menu-tab-name');
                for (const t of tabs) {
                    if ((t.textContent || '').trim() === '算力券明细') {
                        t.click();
                        return;
                    }
                }
            }
        """)
        await page.wait_for_timeout(8000)

        print("[3] Scroll the dashboard canvas way down (to y=74+, 93+, 112+)...")
        canvas = await page.evaluate("""
            () => {
                const all = document.querySelectorAll('*');
                for (const el of all) {
                    if (el.className && el.className.includes && el.className.includes('lite-publish-canvas-scroll')) {
                        return {found: true, scrollH: el.scrollHeight, clientH: el.clientHeight};
                    }
                }
                return {found: false};
            }
        """)
        print(f"  canvas: {canvas}")

        # 滚 canvas 内部容器从 0 到 scrollH
        if canvas.get("found"):
            steps = 40
            for i in range(steps):
                y = int(canvas["scrollH"] * (i + 1) / steps)
                await page.evaluate(f"""
                    () => {{
                        const el = document.querySelector('.lite-publish-canvas-scroll');
                        if (el) el.scrollTop = {y};
                    }}
                """)
                await page.wait_for_timeout(1500)
                cur = await page.evaluate("document.querySelector('.lite-publish-canvas-scroll')?.scrollTop || 0")
                if i % 5 == 0 or i == steps - 1:
                    print(f"    step {i+1}/{steps}: scrollTop={cur}, scrollH={canvas['scrollH']}")
        else:
            # fallback
            for i in range(50):
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight * 0.5)")
                await page.wait_for_timeout(1500)
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")

        print("[4] Wait for all responses...")
        await page.wait_for_timeout(10000)

        # Print summary
        print(f"\n[5] Captured {len(captured)} cards:")
        for cid in TARGET_CARDS:
            if cid in captured:
                v = captured[cid]
                print(f"  ✓ {cid} ({TARGET_CARDS[cid]}): code={v['code']}, objs={v['objects_count']}")
            else:
                print(f"  ✗ {cid} ({TARGET_CARDS[cid]}): NOT CAPTURED")

        # Save full captured
        with open(OUTPUT_DIR / "captured_full_scroll.json", "w") as f:
            json.dump(captured, f, ensure_ascii=False, indent=2, default=str)

        # If captured, also save target posts separately
        target_posts = {}
        for cid in TARGET_CARDS:
            if cid in captured:
                target_posts[cid] = captured[cid]
        if target_posts:
            with open(OUTPUT_DIR / "target_card_posts.json", "w") as f:
                json.dump(target_posts, f, ensure_ascii=False, indent=2, default=str)
            print(f"\n[6] Saved target posts for {len(target_posts)} cards")
            for cid, v in target_posts.items():
                print(f"\n=== {cid} ===")
                print(f"  post: {v['post'][:500]}")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
