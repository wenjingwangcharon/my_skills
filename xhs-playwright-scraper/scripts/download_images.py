#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 xhs_data.json 提取每篇笔记的图片/视频封面 URL，下载到本地，并把图片信息
写回 JSON / 生成 notes.csv(含图片列) / images.csv。无需重新抓取。

用法：
  python download_images.py --data output/xhs_data.json --out output
"""
import argparse
import csv
import json
import os
import urllib.request
from datetime import datetime, timezone, timedelta

BEIJING = timezone(timedelta(hours=8))


def fmt_time(v):
    """把时间戳(秒/毫秒)转成 'YYYY-MM-DD HH:MM:SS'(北京时间)；非时间戳原样返回。"""
    if v is None:
        return ""
    try:
        v = float(v)
    except (TypeError, ValueError):
        return str(v)
    if v > 1e11:
        v = v / 1000.0
    elif v <= 0:
        return str(v)
    try:
        dt = datetime.fromtimestamp(v, tz=timezone.utc).astimezone(BEIJING)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(v)


UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
HEADERS = {
    "User-Agent": UA,
    "Referer": "https://www.xiaohongshu.com/",
    "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
}


def pick_url(img):
    if not isinstance(img, dict):
        return None
    u = img.get("url_default") or img.get("url_pre") or img.get("url")
    if not u and img.get("info_list"):
        u = (img.get("info_list") or [{}])[0].get("url")
    return u


def download(url, path):
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=30) as r:
            data = r.read()
            ct = r.headers.get("Content-Type", "")
        if not data or len(data) < 500:
            return False
        ext = ".webp" if "webp" in ct else (".png" if "png" in ct else ".jpg")
        base, _ = os.path.splitext(path)
        path = base + ext
        with open(path, "wb") as f:
            f.write(data)
        return path
    except Exception as e:
        print(f"    [warn] 下载失败 {url[:60]}... : {e}")
        return False


def run(data_file, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    d = json.load(open(data_file, encoding="utf-8"))
    notes = d.get("notes", [])
    # note_details 可能是 list 或 dict，统一成按 note_id 的映射
    nd = d.get("note_details", [])
    det_by_id = {n.get("note_id"): n for n in nd} if isinstance(nd, list) else nd

    img_manifest = []
    total = ok = 0
    for n in notes:
        nid = n.get("note_id")
        det = det_by_id.get(nid, {})
        urls = []
        for img in (det.get("image_list") or []):
            u = pick_url(img)
            if u:
                urls.append(u)
        vid = det.get("video")
        if isinstance(vid, dict):
            cover = vid.get("cover") or {}
            cu = cover.get("url_default") or cover.get("url") or cover.get("url_pre")
            if cu:
                urls.append(cu)

        local = []
        if urls:
            folder = os.path.join(out_dir, "images", nid)
            os.makedirs(folder, exist_ok=True)
            n["image_count"] = len(urls)
            n["image_urls"] = urls
            for i, u in enumerate(urls):
                dest = os.path.join(folder, f"{i+1:02d}")
                got = download(u, dest)
                if got:
                    local.append(os.path.relpath(got, out_dir))
                    ok += 1
                else:
                    local.append("")
                total += 1
                img_manifest.append({
                    "note_id": nid, "index": i + 1, "url": u,
                    "local": os.path.relpath(got, out_dir) if got else "",
                })
            n["image_local"] = local
        else:
            n["image_count"] = 0
            n["image_urls"] = []
            n["image_local"] = []

    json.dump(d, open(data_file, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"图片下载完成：{ok}/{total} 张成功")

    notes_csv = os.path.join(out_dir, "notes.csv")
    with open(notes_csv, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["note_id", "type", "title", "desc", "likes", "collected",
                    "comment_count", "share_count", "time", "image_count",
                    "image_local", "url"])
        for n in notes:
            ii = n.get("interact_info") or {}
            w.writerow([
                n.get("note_id"), n.get("type"),
                (n.get("title") or "").replace("\n", " "),
                (n.get("desc") or "").replace("\n", " "),
                ii.get("liked_count"), ii.get("collected_count"),
                ii.get("comment_count"), ii.get("share_count"),
                n.get("time_text") or fmt_time(n.get("time")),
                n.get("image_count", 0),
                " | ".join(p for p in (n.get("image_local") or []) if p),
                f"https://www.xiaohongshu.com/explore/{n.get('note_id')}",
            ])

    images_csv = os.path.join(out_dir, "images.csv")
    with open(images_csv, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["note_id", "index", "url", "local_path"])
        for m in img_manifest:
            w.writerow([m["note_id"], m["index"], m["url"], m["local"]])

    print(f"已更新: {data_file}")
    print(f"已更新: {notes_csv}")
    print(f"已生成: {images_csv}")
    print(f"图片目录: {os.path.join(out_dir, 'images')}")


def main():
    ap = argparse.ArgumentParser(description="下载小红书笔记图片并写入数据")
    ap.add_argument("--data", default=os.path.join(os.getcwd(), "output", "xhs_data.json"),
                    help="xhs_data.json 路径")
    ap.add_argument("--out", default=None, help="输出目录（CSV/图片根），默认同 --data 所在目录")
    args = ap.parse_args()
    if args.out is None:
        args.out = os.path.dirname(os.path.abspath(args.data))
    run(args.data, args.out)


if __name__ == "__main__":
    main()
