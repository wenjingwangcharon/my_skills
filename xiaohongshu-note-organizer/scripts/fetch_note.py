#!/usr/bin/env python3
"""
小红书笔记数据获取器
从 xhslink 短链接或笔记 URL 获取笔记详情（标题、正文、图片、标签）。

原理：小红书笔记页面的 __INITIAL_STATE__ JSON 变量中嵌入了完整笔记数据，
      无需登录、无需 cookie、无需破解 x-s 签名。

用法:
  python fetch_note.py <URL> [--download-images <DIR>] [--output <FILE>]

参数:
  URL                   小红书笔记链接（xhslink 短链接或完整 URL）
  --download-images DIR  下载图片到指定目录（可选）
  --output FILE         将笔记数据保存为 JSON 文件（可选，默认输出到 stdout）

输出:
  JSON 格式的笔记数据，包含以下字段:
  {
    "noteId":   "笔记ID",
    "title":    "标题",
    "content":  "正文内容",
    "images":   ["图片URL1", "图片URL2", ...],
    "tags":     ["标签1", "标签2", ...],
    "type":     "normal | video",
    "url":      "最终页面URL",
    "xsecToken":"xsec_token"
  }
"""
import sys
import re
import json
import argparse
from urllib.parse import urlparse, parse_qs

try:
    import requests
except ImportError:
    print("ERROR: requests library not installed. Run: pip install requests", file=sys.stderr)
    sys.exit(1)


def resolve_short_url(short_url: str) -> dict:
    """解析 xhslink 短链接，获取实际笔记 URL 和参数"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }

    resp = requests.get(short_url, headers=headers, allow_redirects=True, timeout=15)
    final_url = resp.url

    parsed = urlparse(final_url)
    path_parts = parsed.path.strip("/").split("/")
    note_id = path_parts[-1] if path_parts else ""

    query_params = parse_qs(parsed.query)
    xsec_token = query_params.get("xsec_token", [""])[0]

    return {
        "final_url": final_url,
        "note_id": note_id,
        "xsec_token": xsec_token,
        "html": resp.text,
    }


def extract_note_data_from_html(html: str, note_id: str) -> dict:
    """从页面 HTML 中提取笔记数据（__INITIAL_STATE__）"""
    # 小红书页面在 __INITIAL_STATE__ 变量中嵌入初始数据
    pattern = r"window\.__INITIAL_STATE__\s*=\s*(\{.*?\})\s*</script>"
    match = re.search(pattern, html, re.DOTALL)

    if not match:
        pattern2 = r"window\.__INITIAL_STATE__\s*=\s*(\{.*?\})\s*$"
        match = re.search(pattern2, html, re.DOTALL | re.MULTILINE)

    if not match:
        pattern3 = r"window\.__INITIAL_STATE__\s*=\s*(.+?)(?:\n</script>|\n<script)"
        match = re.search(pattern3, html, re.DOTALL)

    if not match:
        return extract_from_html_fallback(html, note_id)

    raw_json = match.group(1).strip()
    raw_json = re.sub(r"\bundefined\b", "null", raw_json)

    try:
        state = json.loads(raw_json)
    except json.JSONDecodeError:
        try:
            raw_json_clean = raw_json.replace("undefined", "null")
            state = json.loads(raw_json_clean)
        except Exception:
            return extract_from_html_fallback(html, note_id)

    note_data = None

    if "note" in state:
        note_section = state["note"]
        if "noteDetailMap" in note_section:
            detail_map = note_section["noteDetailMap"]
            if note_id in detail_map:
                note_data = detail_map[note_id].get("note")
            elif len(detail_map) > 0:
                first_key = list(detail_map.keys())[0]
                note_data = detail_map[first_key].get("note")

    if not note_data:
        for key in ["noteDetailMap", "note"]:
            if key in state:
                if isinstance(state[key], dict):
                    for k, v in state[key].items():
                        if isinstance(v, dict) and "note" in v:
                            note_data = v["note"]
                            break
                if note_data:
                    break

    if not note_data:
        return extract_from_html_fallback(html, note_id)

    return parse_note_data(note_data, note_id)


def extract_from_html_fallback(html: str, note_id: str) -> dict:
    """从 HTML meta 标签中提取基本信息（降级方案）"""
    result = {
        "noteId": note_id, "title": "", "content": "",
        "images": [], "tags": [], "type": "normal",
        "url": "", "xsecToken": "",
    }
    title_match = re.search(r'<meta\s+name="og:title"\s+content="([^"]*)"', html)
    if title_match:
        result["title"] = title_match.group(1)
    desc_match = re.search(r'<meta\s+name="description"\s+content="([^"]*)"', html)
    if desc_match:
        result["content"] = desc_match.group(1)
    img_matches = re.findall(r'<meta\s+name="og:image"\s+content="([^"]*)"', html)
    result["images"] = img_matches
    return result


def parse_note_data(note_data: dict, note_id: str) -> dict:
    """解析笔记数据为统一格式"""
    result = {
        "noteId": note_id,
        "title": note_data.get("title", "") or "",
        "content": note_data.get("desc", "") or "",
        "images": [],
        "tags": [],
        "type": note_data.get("type", "normal"),
        "url": "",
        "xsecToken": "",
    }

    image_list = note_data.get("imageList", []) or []
    result["images"] = [
        img.get("urlDefault", "") or img.get("url", "")
        for img in image_list
        if img.get("urlDefault") or img.get("url")
    ]

    if result["type"] == "video":
        video = note_data.get("video", {})
        if video:
            media = video.get("media", {})
            stream = media.get("stream", {})
            for fmt, streams in stream.items():
                if streams and len(streams) > 0:
                    result["images"] = [streams[0].get("masterUrl", "")]
                    break

    tag_list = note_data.get("tagList", []) or []
    result["tags"] = [tag.get("name", "") for tag in tag_list if tag.get("name")]

    if not result["tags"] and result["content"]:
        result["tags"] = re.findall(r"#([^#\s]+)#?", result["content"])

    return result


def download_images(images: list, output_dir: str) -> list:
    """下载图片到本地目录，返回本地路径列表"""
    import os
    os.makedirs(output_dir, exist_ok=True)

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://www.xiaohongshu.com/",
    }

    local_paths = []
    for i, url in enumerate(images):
        try:
            resp = requests.get(url, headers=headers, timeout=15)
            if resp.status_code == 200:
                filepath = os.path.join(output_dir, f"img_{i+1}.jpg")
                with open(filepath, "wb") as f:
                    f.write(resp.content)
                local_paths.append(filepath)
            else:
                local_paths.append(None)
        except Exception:
            local_paths.append(None)

    return local_paths


def get_note_data(url: str) -> dict:
    """主函数：获取小红书笔记数据"""
    resolved = resolve_short_url(url)
    note_data = extract_note_data_from_html(resolved["html"], resolved["note_id"])
    note_data["url"] = resolved["final_url"]
    note_data["xsecToken"] = resolved["xsec_token"]
    return note_data


def main():
    parser = argparse.ArgumentParser(description="小红书笔记数据获取器")
    parser.add_argument("url", help="小红书笔记链接（xhslink 短链接或完整 URL）")
    parser.add_argument("--download-images", default=None, help="下载图片到指定目录")
    parser.add_argument("--output", default=None, help="将笔记数据保存为 JSON 文件（默认输出到 stdout）")
    args = parser.parse_args()

    note_data = get_note_data(args.url)

    if args.download_images and note_data.get("images"):
        local_paths = download_images(note_data["images"], args.download_images)
        note_data["localImages"] = local_paths

    output = json.dumps(note_data, ensure_ascii=False, indent=2)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"Saved to {args.output}", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
