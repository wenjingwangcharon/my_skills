#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
小红书抓取（Playwright 真实浏览器会话）—— 三种模式：

  account  抓指定小红书号的全部帖子+评论
  post     抓指定帖子链接的内容+评论
  search   按关键词搜索，抓排序靠前的前 N 条帖子+评论

用法：
  python scrape.py --mode account --target 2610125281 --cookie cookies.json --out ./output
  python scrape.py --mode post    --url "https://www.xiaohongshu.com/explore/xxx?xsec_token=..." --cookie cookies.json
  python scrape.py --mode search  --keyword "济州岛旅游" --limit 100 --cookie cookies.json

通用：--cookie <登录cookie文件>  --out <输出目录>  --limit <搜索条数,默认100>
Cookie 支持原始串 / JSON 数组 / JSON 对象三种写法。
"""
import argparse
import asyncio
import json
import os
import sys
import urllib.parse

from playwright.async_api import async_playwright

import common


def build_browser_args():
    return ["--disable-blink-features=AutomationControlled", "--no-sandbox",
            "--disable-gpu", "--disable-dev-shm-usage"]


async def run(mode, args):
    out_dir = os.path.abspath(args.out)
    os.makedirs(out_dir, exist_ok=True)

    # 读取并解析 cookie
    if not os.path.exists(args.cookie):
        print(f"[错误] 找不到 cookie 文件: {args.cookie}", file=sys.stderr)
        sys.exit(1)
    raw = open(args.cookie, encoding="utf-8").read()
    try:
        cookies = common.normalize_cookies(json.loads(raw))
    except Exception:
        cookies = common.normalize_cookies(raw)
    if not cookies:
        print("[错误] cookie 为空或解析失败", file=sys.stderr)
        sys.exit(1)
    print(f"[info] 已载入 {len(cookies)} 个 cookie")

    store = {"comment": [], "note": [], "feed": [], "posted": []}
    notes, note_details, comments = {}, {}, {}

    exe = common.find_chromium()
    print(f"[info] chromium: {exe}")
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True, executable_path=exe or None, args=build_browser_args())
        context = await browser.new_context(
            user_agent=("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"),
            viewport={"width": 1280, "height": 900})
        await context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        await context.add_cookies(cookies)
        page = await context.new_page()
        page.on("response", lambda r: asyncio.ensure_future(common.on_response(store, r)))

        if mode == "account":
            await mode_account(page, store, args, out_dir, notes, note_details, comments)
        elif mode == "post":
            await mode_post(page, store, args, out_dir, notes, note_details, comments)
        elif mode == "search":
            await mode_search(page, store, args, out_dir, notes, note_details, comments)

        await browser.close()

    out = common.save_partial(out_dir, args.target or args.keyword or args.url, mode, notes, note_details, comments)
    notes_csv, comments_csv = common.export_csv(out_dir, out, note_details)
    print("\n==== 完成 ====")
    print(f"笔记总数 : {len(out['notes'])}")
    print(f"详情总数 : {len(out['note_details'])}")
    print(f"评论笔记数: {len(out['comments'])} (共 {sum(len(v) for v in out['comments'].values())} 条评论)")
    print(f"输出目录 : {out_dir}")
    print("  - xhs_data.json")
    print(f"  - {os.path.basename(notes_csv)}")
    print(f"  - {os.path.basename(comments_csv)}")


async def mode_account(page, store, args, out_dir, notes, note_details, comments):
    user_id, user_xsec = await common.resolve_target(page, args.target)
    profile_url = f"https://www.xiaohongshu.com/user/profile/{user_id}"
    if user_xsec:
        profile_url += f"?xsec_token={user_xsec}&xsec_source=pc_search"
    print(f"[account] 打开主页: {profile_url}")
    await page.goto(profile_url, wait_until="domcontentloaded", timeout=common.PAGE_TIMEOUT)
    await asyncio.sleep(4)
    await common.scroll(page, common.PROFILE_SCROLL, common.SCROLL_DELAY)
    for c in await common.extract_cards(page):
        if c["note_id"]:
            notes.setdefault(c["note_id"], {"note_id": c["note_id"],
                                            "xsec_token": c["xsec"],
                                            "xsec_source": c["source"]})
    print(f"     提取到 {len(notes)} 篇笔记")

    for i, nid in enumerate(notes.keys()):
        await common.collect_one_note(page, store, nid,
                                      notes[nid].get("xsec_token"),
                                      notes[nid].get("xsec_source"),
                                      notes, note_details, comments)
        if (i + 1) % 3 == 0 or i == len(notes) - 1:
            common.save_partial(out_dir, args.target, "account", notes, note_details, comments)


async def mode_post(page, store, args, out_dir, notes, note_details, comments):
    nid, xsec, xsrc = common.parse_post_url(args.url)
    if not nid:
        print(f"[错误] 无法从链接解析出 note_id: {args.url}", file=sys.stderr)
        sys.exit(1)
    print(f"[post] 目标笔记: {nid}")
    notes[nid] = {"note_id": nid, "xsec_token": xsec, "xsec_source": xsrc}
    await common.collect_one_note(page, store, nid, xsec, xsrc, notes, note_details, comments)
    common.save_partial(out_dir, args.url, "post", notes, note_details, comments)


async def mode_search(page, store, args, out_dir, notes, note_details, comments):
    limit = max(1, int(args.limit))
    kw = args.keyword
    search_url = (f"https://www.xiaohongshu.com/search_result"
                  f"?keyword={urllib.parse.quote(kw)}&type=note")
    print(f"[search] 搜索: {kw}  (目标前 {limit} 条)")
    await page.goto(search_url, wait_until="domcontentloaded", timeout=common.PAGE_TIMEOUT)
    await asyncio.sleep(5)
    seen = set()
    prev = 0
    streak = 0
    for _ in range(60):
        await common.scroll(page, 3, common.SCROLL_DELAY)
        for c in await common.extract_cards(page):
            if c["note_id"] and c["note_id"] not in seen and len(notes) < limit:
                seen.add(c["note_id"])
                notes[c["note_id"]] = {"note_id": c["note_id"],
                                       "xsec_token": c["xsec"],
                                       "xsec_source": c["source"]}
        if len(notes) >= limit:
            break
        if len(notes) == prev:
            streak += 1
            if streak >= 6:
                print("     [info] 连续多次无新结果，停止翻页")
                break
        else:
            prev = len(notes)
            streak = 0
    print(f"     搜索到 {len(notes)} 篇笔记，开始逐篇抓详情与评论...")

    nids = list(notes.keys())[:limit]  # 仅处理前 limit 篇
    for i, nid in enumerate(nids):
        await common.collect_one_note(page, store, nid,
                                      notes[nid].get("xsec_token"),
                                      notes[nid].get("xsec_source"),
                                      notes, note_details, comments)
        if (i + 1) % 3 == 0 or i == len(nids) - 1:
            common.save_partial(out_dir, kw, "search", notes, note_details, comments)


def main():
    ap = argparse.ArgumentParser(description="小红书抓取（account / post / search 三种模式）")
    ap.add_argument("--mode", required=True, choices=["account", "post", "search"],
                    help="抓取模式")
    ap.add_argument("--target", help="[account] 小红书号 / red_id / user_id")
    ap.add_argument("--url", help="[post] 帖子链接")
    ap.add_argument("--keyword", help="[search] 搜索关键词")
    ap.add_argument("--limit", default=100, help="[search] 抓取前 N 条，默认 100")
    ap.add_argument("--cookie", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "cookies.json"),
                    help="登录 cookie 文件，默认 scripts/cookies.json")
    ap.add_argument("--out", default=os.path.join(os.getcwd(), "output"),
                    help="输出目录，默认 ./output")
    args = ap.parse_args()

    if args.mode == "account" and not args.target:
        print("[错误] account 模式必须提供 --target", file=sys.stderr); sys.exit(1)
    if args.mode == "post" and not args.url:
        print("[错误] post 模式必须提供 --url", file=sys.stderr); sys.exit(1)
    if args.mode == "search" and not args.keyword:
        print("[错误] search 模式必须提供 --keyword", file=sys.stderr); sys.exit(1)

    asyncio.run(run(args.mode, args))


if __name__ == "__main__":
    main()
