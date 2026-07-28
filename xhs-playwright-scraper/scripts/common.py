#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""小红书抓取的公共工具：浏览器定位、Cookie 解析、时间格式化、响应监听、
评论/笔记详情收集、保存与导出。被 scrape.py 的三种模式共用。

所有路径均相对/自动探测，不写死任何机器专属路径，可在任意机器运行。
"""
import asyncio
import csv
import glob
import json
import os
import re
import urllib.parse
from datetime import datetime, timezone, timedelta

from playwright.async_api import async_playwright

# 小红书时间按北京时间(UTC+8)展示
BEIJING = timezone(timedelta(hours=8))

# ===== 抓取参数（可按需调整）=====
PROFILE_SCROLL = 25
COMMENT_SCROLL = 80
SCROLL_DELAY = 1.0
PAGE_TIMEOUT = 60000


def find_chromium():
    """自动定位 Playwright 下载的 chromium（兼容 macOS / Linux / Windows 用户目录）。"""
    bases = [
        os.path.expanduser("~/Library/Caches/ms-playwright"),   # macOS
        os.path.expanduser("~/.cache/ms-playwright"),           # Linux
        os.path.expanduser("~/AppData/Local/ms-playwright"),    # Windows
    ]
    patterns = [
        os.path.join(b, "chromium-*", "chrome-mac-arm64",
                     "Google Chrome for Testing.app", "Contents", "MacOS",
                     "Google Chrome for Testing") for b in bases
    ] + [
        os.path.join(b, "chromium-*", "chrome-linux", "chrome") for b in bases
    ] + [
        os.path.join(b, "chromium-*", "chrome-win", "chrome.exe") for b in bases
    ]
    for pat in patterns:
        hits = sorted(glob.glob(pat))
        if hits:
            return hits[-1]
    # 兜底：用 playwright 自带默认路径
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            return p.chromium.executable_path
    except Exception:
        return None


def normalize_cookies(raw):
    """支持：原始 cookie 串、JSON 数组、JSON 对象(dict)。统一成 add_cookies 格式。"""
    if isinstance(raw, str):
        s = raw.strip()
        if s.startswith("["):
            try:
                raw = json.loads(s)
            except Exception:
                raw = None
        elif s.startswith("{"):
            try:
                raw = json.loads(s)
            except Exception:
                raw = None
        else:
            out = []
            for p in raw.split(";"):
                p = p.strip()
                if "=" in p:
                    k, v = p.split("=", 1)
                    out.append({"name": k.strip(), "value": v.strip()})
            raw = out
    if isinstance(raw, dict):
        raw = [{"name": k, "value": v} for k, v in raw.items()]
    out = []
    for c in (raw or []):
        if not c.get("name"):
            continue
        d = c.get("domain") or ".xiaohongshu.com"
        if not d.startswith("."):
            d = "." + d.lstrip(".")
        out.append({"name": c["name"], "value": c["value"], "description": c.get("description", ""),
                    "domain": d, "path": c.get("path") or "/",
                    "secure": True, "sameSite": "Lax"})
    return out


def fmt_time(v):
    """把时间戳(秒/毫秒)转成 'YYYY-MM-DD HH:MM:SS'(北京时间)；非时间戳原样返回。"""
    if v is None:
        return ""
    try:
        v = float(v)
    except (TypeError, ValueError):
        return str(v)
    if v > 1e11:        # 毫秒
        v = v / 1000.0
    elif v <= 0:
        return str(v)
    try:
        dt = datetime.fromtimestamp(v, tz=timezone.utc).astimezone(BEIJING)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(v)


def classify(url: str):
    if "/comment" in url:
        return "comment"
    if "/api/sns/web/v1/note/" in url:
        return "note"
    if "/api/sns/web/v1/feed" in url:
        return "feed"
    if "/user_posted" in url:
        return "posted"
    return None


async def on_response(store, response):
    url = response.url
    kind = classify(url)
    if not kind:
        return
    try:
        body = await response.json()
    except Exception:
        return
    if isinstance(body, dict):
        store[kind].append((url, body))


async def scroll(page, times, delay):
    for _ in range(times):
        await page.mouse.wheel(0, 1200)
        await asyncio.sleep(delay)


async def extract_cards(page):
    """从当前页面的笔记卡片 DOM 提取 {note_id, xsec, source} 列表（去重）。"""
    return await page.evaluate(
        """() => {
            const res = [];
            const seen = new Set();
            document.querySelectorAll('section.note-item a.cover').forEach(a => {
                const u = new URL(a.href, location.origin);
                const parts = u.pathname.split('/').filter(Boolean);
                const nid = parts[parts.length - 1];
                if (!nid || seen.has(nid)) return;
                seen.add(nid);
                res.push({ note_id: nid, xsec: u.searchParams.get('xsec_token'),
                           source: u.searchParams.get('xsec_source') || 'pc_search' });
            });
            return res;
        }""")


def parse_post_url(url):
    """从帖子链接解析出 note_id / xsec_token / xsec_source。"""
    u = urllib.parse.urlparse(url)
    parts = [p for p in u.path.split('/') if p]
    nid = None
    for i, p in enumerate(parts):
        if p == 'explore' and i + 1 < len(parts):
            nid = parts[i + 1]
            break
        if p == 'discovery' and i + 1 < len(parts) and parts[i + 1] == 'item':
            nid = parts[i + 2]
            break
    qs = urllib.parse.parse_qs(u.query)
    xsec = (qs.get('xsec_token') or [None])[0]
    xsrc = (qs.get('xsec_source') or ['pc_search'])[0]
    return nid, xsec, xsrc


async def resolve_target(page, target):
    """red_id/昵称 -> user_id + xsec_token；已是十六进制 user_id 则直接用。"""
    if re.fullmatch(r"[0-9a-f]{20,}", target):
        print(f"[resolve] {target} 似为 user_id，直接作为 user_id")
        return target, None
    print(f"[resolve] 用搜索解析目标: {target}")
    box = {}

    async def cap(r):
        if "/api/sns/web/v1/search/onebox" in r.url:
            try:
                b = await r.json()
            except Exception:
                return
            if isinstance(b, dict):
                box["body"] = b

    page.on("response", lambda r: asyncio.ensure_future(cap(r)))
    await page.goto(f"https://www.xiaohongshu.com/search_result?keyword={urllib.parse.quote(target)}&type=user",
                    wait_until="domcontentloaded", timeout=PAGE_TIMEOUT)
    await asyncio.sleep(5)
    for _ in range(4):
        await page.mouse.wheel(0, 1500)
        await asyncio.sleep(0.6)
    b = box.get("body") or {}
    onebox = (b.get("data") or {}).get("onebox_list") or []
    for ob in onebox:
        uo = ob.get("user_one_box") or {}
        rid = uo.get("red_id")
        uid = uo.get("id")
        xsec = uo.get("xsec_token")
        if rid == target or uid:
            print(f"[resolve] 命中用户: {uo.get('title')} | user_id={uid} | red_id={rid} | note_count={uo.get('note_count')}")
            return uid, xsec
    print("[resolve] onebox 未命中，尝试直接当 user_id")
    return target, None


async def extract_note_from_state(page, nid):
    """从小红书详情页内嵌的 window.__INITIAL_STATE__ 提取笔记详情（直接打开详情页时
    内容走服务端渲染，不在 /feed、/note 接口里）。返回已转成 snake_case 的 note_card，
    与 API 返回结构一致；取不到返回 None。"""
    js = """(nid) => {
        try {
            const S = window.__INITIAL_STATE__;
            if (!S || !S.note || !S.note.noteDetailMap) return null;
            const entry = S.note.noteDetailMap[nid];
            if (!entry || !entry.note) return null;
            const n = entry.note;
            const img = (n.imageList || []).map(function(im){
                return {
                    url_default: im.urlDefault || im.url_default || '',
                    url_pre: im.urlPre || im.url_pre || '',
                    url: im.url || '',
                    info_list: im.infoList || im.info_list || []
                };
            });
            const ii = n.interactInfo || {};
            return {
                note_id: n.noteId || nid,
                title: n.title || '',
                desc: n.desc || '',
                type: n.type || '',
                time: n.time,
                ip_location: n.ipLocation || '',
                interact_info: {
                    liked_count: ii.likedCount, collected_count: ii.collectedCount,
                    comment_count: ii.commentCount, share_count: ii.shareCount
                },
                image_list: img,
                user: n.user || {},
                last_update_time: n.lastUpdateTime
            };
        } catch (e) { return {__err: String(e)}; }
    }"""
    try:
        r = await page.evaluate(js, nid)
    except Exception:
        return None
    if isinstance(r, dict) and "__err" not in r and r.get("note_id"):
        return r
    return None


async def collect_one_note(page, store, nid, xsec, xsec_source,
                           notes, note_details, comments):
    """打开单篇笔记详情页，收集笔记详情 + 全部评论。xsec_token 缺失时仍尝试（可能限流）。"""
    url = f"https://www.xiaohongshu.com/explore/{nid}"
    if xsec:
        url += f"?xsec_token={xsec}&xsec_source={xsec_source or 'pc_search'}"
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=PAGE_TIMEOUT)
    except Exception as e:
        print(f"     [warn] 打开笔记 {nid} 失败: {e}")
        return
    await asyncio.sleep(3)

    # 自适应滚动收集评论（以接口 has_more 为准）
    before = 0
    stable = 0
    for _ in range(COMMENT_SCROLL):
        await page.mouse.wheel(0, 1200)
        await asyncio.sleep(SCROLL_DELAY)
        # 去重写入 comments[nid]
        for u, j in store["comment"]:
            if nid not in u:
                continue
            for c in ((j.get("data") or {}).get("comments") or []):
                cid = c.get("id")
                if cid:
                    c["time_text"] = fmt_time(c.get("create_time"))
                    for sub in (c.get("sub_comments") or []):
                        sub["time_text"] = fmt_time(sub.get("create_time"))
                    comments.setdefault(nid, {})[cid] = c
        has_more = None
        for u, j in reversed(store["comment"]):
            if nid in u:
                has_more = (j.get("data") or {}).get("has_more")
                break
        now = len(comments.get(nid, {}))
        if has_more is False:
            break
        if now == before:
            stable += 1
        else:
            stable = 0
        before = now
        if now > 0 and stable >= 5:
            break
        if now == 0 and stable >= 6:
            break

    # 笔记详情：优先用内嵌 __INITIAL_STATE__（直接打开详情页时最可靠）
    state_note = await extract_note_from_state(page, nid)
    if state_note:
        state_note["time_text"] = fmt_time(state_note.get("time"))
        note_details[nid] = state_note
        notes.setdefault(nid, {"note_id": nid})
        notes[nid].setdefault("title", state_note.get("title"))
        notes[nid].setdefault("desc", state_note.get("desc") or state_note.get("content"))
        notes[nid].setdefault("type", state_note.get("type") or state_note.get("note_type"))
        notes[nid].setdefault("time", state_note.get("time"))
        notes[nid].setdefault("time_text", state_note.get("time_text"))
        notes[nid].setdefault("interact_info", state_note.get("interact_info"))
    else:
        # 兜底：扫描 feed/note 接口响应（note_card 嵌套）
        for _, j in store["note"] + store["feed"]:
            data = (j.get("data") or {})
            cands = []
            if isinstance(data.get("note"), dict):
                cands.append(data["note"])
            for it in (data.get("items") or []):
                if isinstance(it, dict):
                    cands.append(it.get("note_card") or it)
            for cand in cands:
                cid = cand.get("note_id") or cand.get("id")
                if cid == nid:
                    cand["time_text"] = fmt_time(cand.get("time") or cand.get("create_time"))
                    note_details[nid] = cand
                    notes.setdefault(nid, {"note_id": nid})
                    notes[nid].setdefault("title", cand.get("title"))
                    notes[nid].setdefault("desc", cand.get("desc") or cand.get("content"))
                    notes[nid].setdefault("type", cand.get("type") or cand.get("note_type"))
                    notes[nid].setdefault("time", cand.get("time") or cand.get("create_time"))
                    notes[nid].setdefault("time_text", cand.get("time_text"))
                    notes[nid].setdefault("interact_info", cand.get("interact_info"))

    # DOM 兜底：抓取标题/正文（当内嵌状态与接口都缺失时）
    try:
        dom = await page.evaluate(
            """() => {
                const t = document.querySelector('.title');
                const d = document.querySelector('.desc');
                const c = document.querySelector('.note-content, .content');
                return { title: t ? t.innerText.trim() : '',
                         desc: d ? d.innerText.trim() : (c ? c.innerText.trim() : '') };
            }""")
        notes.setdefault(nid, {"note_id": nid})
        if dom.get("title") and not notes[nid].get("title"):
            notes[nid]["title"] = dom["title"]
        if dom.get("desc") and not notes[nid].get("desc"):
            notes[nid]["desc"] = dom["desc"]
    except Exception:
        pass

    cnt = len(comments.get(nid, {}))
    title = (note_details.get(nid, {}) or {}).get("title") or notes.get(nid, {}).get("title") or ""
    print(f"     -> {nid} | {cnt} 条评论" + (f" | {title[:30]}" if title else ""))


def save_partial(out_dir, target, mode, notes, note_details, comments):
    out = {
        "target": target,
        "mode": mode,
        "notes": list(notes.values()),
        "note_details": list(note_details.values()),
        "comments": {k: list(v.values()) for k, v in comments.items()},
    }
    with open(os.path.join(out_dir, "xhs_data.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    return out


def export_csv(out_dir, out, note_details):
    notes_csv = os.path.join(out_dir, "notes.csv")
    with open(notes_csv, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["note_id", "type", "title", "desc", "likes", "collected",
                    "comment_count", "share_count", "time", "url"])
        for n in out["notes"]:
            ii = ((n.get("interact_info")) or (note_details.get(n.get("note_id")) or {}).get("interact_info") or {})
            det = note_details.get(n.get("note_id")) or {}
            w.writerow([
                n.get("note_id"), n.get("type") or det.get("type"),
                (det.get("title") or n.get("title") or "").replace("\n", " "),
                (det.get("desc") or n.get("desc") or "").replace("\n", " "),
                ii.get("liked_count"), ii.get("collected_count"),
                ii.get("comment_count"), ii.get("share_count"),
                n.get("time_text") or fmt_time(n.get("time") or det.get("time") or det.get("create_time")),
                f"https://www.xiaohongshu.com/explore/{n.get('note_id')}",
            ])
    comments_csv = os.path.join(out_dir, "comments.csv")
    with open(comments_csv, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["note_id", "comment_id", "parent_id", "user_id", "nickname",
                    "content", "likes", "time", "ip_location"])
        for nid, clist in out["comments"].items():
            for c in clist:
                w.writerow([
                    nid, c.get("id"), "",
                    (c.get("user_info") or {}).get("user_id"),
                    (c.get("user_info") or {}).get("nickname"),
                    (c.get("content") or "").replace("\n", " "),
                    (c.get("like_info") or {}).get("liked_count"),
                    c.get("time_text") or fmt_time(c.get("create_time")), c.get("ip_location"),
                ])
                for sub in (c.get("sub_comments") or []):
                    w.writerow([
                        nid, sub.get("id"), c.get("id"),
                        (sub.get("user_info") or {}).get("user_id"),
                        (sub.get("user_info") or {}).get("nickname"),
                        (sub.get("content") or "").replace("\n", " "),
                        (sub.get("like_info") or {}).get("liked_count"),
                        sub.get("time_text") or fmt_time(sub.get("create_time")), sub.get("ip_location"),
                    ])
    return notes_csv, comments_csv
