#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch_feeds.py — 抓取多源 AI / 科技商业媒体最新文章（纯标准库，无需 feedparser）

将 Coze 工作流 weixinnews_XZY 中依赖的「获取新智元节点代码」插件替换为可稳定访问的信源。
支持三类抓取：
  - "官网RSS"           : 标准 RSS 2.0 / Atom（含 RDF）。
  - "WordPress API"     : WordPress 站点的 /wp-json/wp/v2/posts 接口，直接返回完整正文，
                          无需再做逐篇网页抓取；新智元官网 aiera.com.cn 即用此方式。
  - "微信公众号镜像"     : 第三方公众号镜像 RSS（仅能拿到标题，正文需另抓，已不推荐）。
APPSO 内容发布在爱范儿(ifanr.com)，通过其主 feed 的 <dc:creator> 按作者 "APPSO" 过滤得到。

容错策略（针对信源时常抽风）：
  - 每个信源可配 `fallback` 候选地址列表，主地址失败（网络错误 / 返回网页而非 feed / 解析无条目）
    时自动尝试下一个。
  - 网络类错误（超时 / 不可达）自动重试 1 次（退避 1.5s）。
  - 拉回的内容若不是 feed（SPA 空壳页、WAF 拦截页）会被识别为「返回网页而非 feed」并切换候选。
  - 单信源彻底失败不影响其他信源，失败原因分类汇总到 errors 字段，供日报/周报标注。

脚本只负责「拉取 + 解析 + 过滤 + 去重」，把文章列表输出为 JSON，后续的「摘要 / 目录 /
周报」由 Agent（LLM）完成。带 "content" 字段的文章（WordPress API 来源）可直接使用正文，
无需再次 WebFetch。

用法：
    python fetch_feeds.py --output articles.json [--days 1] [--since 2026-07-20]
                          [--max-per-source 8] [--max-total 60]
                          [--keyword "AI,大模型,智能体"] [--sources sources.json]
    python fetch_feeds.py --list-sources        # 打印内置默认信源

输出 JSON 为对象列表，单条结构：
    {
      "source":      "量子位",
      "source_url":  "https://www.qbitai.com/feed",
      "category":    "AI",
      "title":       "文章标题",
      "link":        "https://...",
      "published":   "2026-07-20T13:00:00+08:00" | null,
      "summary":     "feed 提供的纯文本摘要（截断到 400 字）",
      "tags":        ["标签1", "标签2"]
    }

说明：
- 同时兼容 RSS 2.0（含 RDF/RSS）与 Atom，自动处理命名空间。
- 单个信源抓取失败不影响其他信源（失败信息汇总到 stderr 与返回 JSON 的 _errors 字段）。
- 无网络时可用 --sources 指向一个本地 JSON（结构同默认信源），每条可带 "local" 字段指向
  本地 xml 文件用于离线测试。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import html
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

# ---------------------------------------------------------------------------
# 默认信源：硬核科技 / 商业媒体。扩展时改这里或传入 --sources。
# category 用于周报分组；type 仅作备注。
# ---------------------------------------------------------------------------
DEFAULT_SOURCES = [
    {"name": "新智元",   "url": "https://aiera.com.cn/wp-json/wp/v2/posts?per_page=20",  "category": "AI",      "type": "WordPress API"},
    {"name": "36氪",     "url": "https://36kr.com/feed",                                  "category": "商业/创投", "type": "官网RSS"},
    {"name": "智东西",   "url": "https://www.zhidx.com/wp-json/wp/v2/posts?per_page=20", "category": "AI/硬科技", "type": "WordPress API"},
    {"name": "量子位",   "url": "https://www.qbitai.com/feed",                            "category": "AI",      "type": "官网RSS"},
    {"name": "APPSO",    "url": "https://www.ifanr.com/feed", "category": "消费科技", "type": "官网RSS", "author": "APPSO"},
    {"name": "机器之心", "url": "https://decemberpei.cyou/rssbox/wechat-jiqizhixin.xml", "category": "AI", "type": "微信公众号镜像",
     "fallback": ["https://syncedreview.com/feed/", "https://www.jiqizhixin.com/rss"]},
    {"name": "爱范儿",   "url": "https://www.ifanr.com/feed", "category": "消费科技", "type": "官网RSS", "author_exclude": ["APPSO"]},
    {"name": "少数派",   "url": "https://sspai.com/feed",                                  "category": "效率/工具", "type": "官网RSS"},
    {"name": "极客公园", "url": "https://www.geekpark.net/rss",                          "category": "科技",     "type": "官网RSS",
     "fallback": ["https://rsshub.app/geekpark/index"]},
    {"name": "虎嗅",     "url": "https://www.huxiu.com/rss/0.xml",                       "category": "商业",     "type": "官网RSS",
     "fallback": ["https://rsshub.app/huxiu"]},
]

USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
TIMEOUT = 12
SUMMARY_MAX = 400
CONTENT_MAX = 6000


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------
def local(tag: str) -> str:
    """取带命名空间标签的本地名，如 '{http://www.w3.org/2005/Atom}entry' -> 'entry'。"""
    return tag.split("}", 1)[-1] if "}" in tag else tag


def strip_html(s: str) -> str:
    if not s:
        return ""
    s = re.sub(r"<(script|style).*?</\1>", "", s, flags=re.S | re.I)
    s = re.sub(r"<[^>]+>", "", s)
    s = html.unescape(s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def parse_date_to_dt(s: str):
    """解析 RFC822 或 ISO8601 时间为感知型 datetime；失败返回 None。"""
    if not s or not s.strip():
        return None
    s = s.strip()
    # RFC822（RSS pubDate）：'Mon, 20 Jul 2026 13:00:00 +0800'
    try:
        dt = parsedate_to_datetime(s)
        if dt is not None:
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
    except (TypeError, ValueError, IndexError):
        pass
    # ISO8601（Atom published/updated）：'2026-07-20T13:00:00+08:00' 或带 'Z'
    try:
        t = s.replace("Z", "+00:00")
        dt = datetime.fromisoformat(t)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def child_text(elem, name: str):
    for c in list(elem):
        if local(c.tag) == name and (c.text or "").strip():
            return c.text.strip()
    return None


def first_child_text(elem, names):
    for n in names:
        t = child_text(elem, n)
        if t:
            return t
    return None


def extract_link(elem):
    """从 RSS <item> 或 Atom <entry> 取出文章链接。"""
    links = [c for c in list(elem) if local(c.tag) == "link"]
    # RSS：<link>https://...</link>
    for c in links:
        if c.text and c.text.strip():
            return c.text.strip()
    # Atom：<link rel="alternate" href="..."/> 或 <link href="..."/>
    for c in links:
        href = c.get("href")
        if href and (c.get("rel") in (None, "alternate")):
            return href.strip()
    for c in links:
        if c.get("href"):
            return c.get("href").strip()
    return None


def extract_categories(elem):
    """RSS <category>文本 或 Atom <category term="..."/>。"""
    out = []
    for c in elem.iter():
        if local(c.tag) == "category":
            term = c.get("term")
            if term and term.strip():
                out.append(term.strip())
            elif c.text and c.text.strip():
                out.append(c.text.strip())
    # 去重保序
    seen = set()
    uniq = []
    for x in out:
        if x not in seen:
            seen.add(x)
            uniq.append(x)
    return uniq


def extract_author(elem):
    """RSS <dc:creator>/<author> 或 Atom <author><name>。无则返回 ''。"""
    # RSS: <dc:creator>NAME</dc:creator> 或 <author>NAME</author>
    for c in list(elem):
        lt = local(c.tag)
        if lt in ("creator", "author") and (c.text or "").strip():
            return c.text.strip()
    # Atom: <author><name>NAME</name></author>
    for c in list(elem):
        if local(c.tag) == "author":
            nm = child_text(c, "name")
            if nm:
                return nm
    return ""


# ---------------------------------------------------------------------------
# 解析单个 feed
# ---------------------------------------------------------------------------
def parse_feed(raw: bytes, source: dict) -> list:
    entries = []
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as e:
        sys.stderr.write(f"[parse-error] {source['name']}: {e}\n")
        return entries

    items = [e for e in root.iter() if local(e.tag) in ("item", "entry")]
    for e in items:
        title = child_text(e, "title")
        if not title:
            continue
        link = extract_link(e)
        if not link:
            continue
        author = extract_author(e)
        # 作者过滤（含/排除）——用于同一 feed 内按栏目拆分（如 ifanr 的 APPSO）
        inc = source.get("author")
        if inc:
            if not author or inc.lower() not in author.lower():
                continue
        exc = source.get("author_exclude") or []
        if exc and author and any(x.lower() in author.lower() for x in exc):
            continue
        pub = parse_date_to_dt(
            first_child_text(e, ["pubDate", "published", "updated", "date", "dc_date"])
        )
        summary_raw = first_child_text(
            e, ["description", "summary", "content", "encoded", "content_encoded"]
        )
        summary = strip_html(summary_raw)[:SUMMARY_MAX] if summary_raw else ""
        tags = extract_categories(e)
        entries.append({
            "source": source["name"],
            "source_url": source["url"],
            "category": source.get("category", ""),
            "title": title,
            "link": link,
            "published": pub.isoformat() if pub else None,
            "_published_dt": pub,
            "summary": summary,
            "tags": tags,
            "author": author,
            "content": "",
        })
    return entries


def parse_wp_json(raw: bytes, source: dict) -> list:
    """解析 WordPress REST API (/wp-json/wp/v2/posts) 返回的 JSON。

    直接包含完整正文，无需后续逐篇抓取。每条 post 字段：
      title.rendered / link / date / content.rendered / excerpt.rendered
    """
    entries = []
    try:
        posts = json.loads(raw)
    except (json.JSONDecodeError, ValueError) as e:
        sys.stderr.write(f"[wp-json-error] {source['name']}: {e}\n")
        return entries
    if not isinstance(posts, list):
        sys.stderr.write(f"[wp-json-error] {source['name']}: 返回非列表\n")
        return entries
    for p in posts:
        try:
            title = strip_html(p.get("title", {}).get("rendered", "")).strip()
            link = p.get("link", "").strip()
            if not title or not link:
                continue
            pub = parse_date_to_dt(p.get("date", ""))
            content_html = p.get("content", {}).get("rendered", "")
            content = strip_html(content_html)[:CONTENT_MAX]
            excerpt_html = p.get("excerpt", {}).get("rendered", "")
            summary = strip_html(excerpt_html)[:SUMMARY_MAX] or content[:SUMMARY_MAX]
            tags = []
            for t in p.get("categories", []) if isinstance(p.get("categories"), list) else []:
                if isinstance(t, str):
                    tags.append(t)
            entries.append({
                "source": source["name"],
                "source_url": source["url"],
                "category": source.get("category", ""),
                "title": title,
                "link": link,
                "published": pub.isoformat() if pub else None,
                "_published_dt": pub,
                "summary": summary,
                "tags": tags,
                "author": "",
                "content": content,
            })
        except Exception as e:
            sys.stderr.write(f"[wp-json-item-error] {source['name']}: {e}\n")
            continue
    return entries


# ---------------------------------------------------------------------------
# 抓取（含重试 + 多候选兜底 + 非 feed 识别）
# ---------------------------------------------------------------------------
def _is_timeout(e: Exception) -> bool:
    """仅真正的超时（连接/读取）才值得重试；连接被拒/不可达是确定性的，重试无意义。"""
    return "timed out" in str(e).lower() or "timeout" in str(e).lower()


def _classify_net(e: Exception) -> str:
    """把网络异常归类成可读原因。"""
    msg = str(e)
    if "timed out" in msg or "timeout" in msg.lower():
        return "连接超时（网络不通/被墙/服务器无响应）"
    if "10060" in msg or "getaddrinfo" in msg or "name or service" in msg:
        return "连接不可达（主机无响应/域名解析失败）"
    if "connection" in msg.lower() or "refused" in msg.lower():
        return "连接被拒/重置"
    return f"网络错误: {msg[:80]}"


def _fetch_bytes(url: str):
    """下载 URL，返回 (raw_bytes, None) 或 (None, 错误说明)。

    重试策略：仅对「真正的超时」重试 1 次（退避 1.5s）；连接被拒/不可达等确定性错误立即失败，
    避免对死信源无意义地长时间等待。
    """
    last_err = None
    for attempt in range(2):  # 原始 + 1 次重试（仅限超时）
        try:
            req = Request(url, headers={"User-Agent": USER_AGENT})
            with urlopen(req, timeout=TIMEOUT) as resp:
                raw = resp.read()
            if raw:
                return raw, None
            return None, "空响应（0 字节）"
        except HTTPError as e:
            return None, f"HTTP {e.code} {e.reason}"
        except (URLError, OSError) as e:
            last_err = e
            if attempt == 0 and _is_timeout(e):
                time.sleep(1.5)
                continue
            return None, _classify_net(e)
    return None, _classify_net(last_err) if last_err else "未知网络错误"


def _looks_like_feed(raw: bytes) -> bool:
    """粗略判断响应是否为 feed（而非 SPA 空壳页 / WAF 拦截页）。"""
    head = raw[:600].decode("utf-8", "ignore")
    return bool(re.search(r"<rss|<feed|<item|<entry|<channel|<rdf:RDF", head, re.I))


def fetch_source(source: dict):
    """抓取单个信源，返回 (entries, error_or_None)。

    - 优先用 source["url"]，失败则依次尝试 source["fallback"] 列表。
    - 拉回内容若不是 feed（如 SPA / WAF 页），视作失败并切换候选地址。
    - 任何异常都不会抛出，单信源失败隔离，不影响其他信源。
    - 支持 local 字段指向本地文件离线测试。
    """
    stype = (source.get("type") or "官网RSS").strip()
    urls = [source.get("url")] + list(source.get("fallback") or [])
    urls = [u for u in urls if u]
    local_path = source.get("local")
    tried = []
    if local_path and os.path.exists(local_path):
        with open(local_path, "rb") as f:
            raw = f.read()
        if stype == "WordPress API":
            if raw.lstrip()[:1] not in (b"[", b"{"):
                return [], f"{local_path} → 本地文件不是有效 JSON"
            return parse_wp_json(raw, source), None
        if not _looks_like_feed(raw):
            return [], f"{local_path} → 本地文件不是有效 feed"
        return parse_feed(raw, source), None
    for url in urls:
        raw, err = _fetch_bytes(url)
        if err:
            tried.append(f"{url} → {err}")
            continue
        if stype == "WordPress API":
            # WordPress REST API 返回 JSON，不是 XML feed
            if raw.lstrip()[:1] not in (b"[", b"{"):
                tried.append(f"{url} → 返回内容非 JSON（SPA/WAF 拦截）")
                continue
            ents = parse_wp_json(raw, source)
        else:
            if not _looks_like_feed(raw):
                # 拿到的是网页（SPA 空壳 / WAF 拦截），不是 feed
                tried.append(f"{url} → 返回网页而非 feed（SPA/WAF 拦截）")
                continue
            ents = parse_feed(raw, source)
        if ents:
            return ents, None
        tried.append(f"{url} → feed 解析成功但无条目")
    return [], "；".join(tried) or "无可用地址"


def normalize_link(link: str) -> str:
    """用于去重：去掉协议、末尾斜杠、fragment。"""
    l = link.strip().lower()
    l = re.sub(r"^https?://", "", l)
    l = re.sub(r"/+$", "", l)
    l = re.split(r"#", l)[0]
    return l


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="Fetch latest AI/tech news from RSS/Atom sources.")
    ap.add_argument("--output", help="输出 JSON 路径（不传则打印到 stdout）")
    ap.add_argument("--sources", help="信源 JSON 路径（结构同默认信源列表）")
    ap.add_argument("--days", type=int, default=0, help="仅保留最近 N 天的文章（与 --since 二选一）")
    ap.add_argument("--since", help="仅保留该日期及之后的文章，格式 YYYY-MM-DD")
    ap.add_argument("--max-per-source", type=int, default=8, help="每个信源最多取几条")
    ap.add_argument("--max-total", type=int, default=80, help="整体最多保留几条")
    ap.add_argument("--keyword", help="逗号分隔关键词，标题或摘要命中其一才保留（为空=不过滤）")
    ap.add_argument("--list-sources", action="store_true", help="打印内置默认信源并退出")
    args = ap.parse_args()

    if args.list_sources:
        print(json.dumps(DEFAULT_SOURCES, ensure_ascii=False, indent=2))
        return

    # 信源
    if args.sources:
        with open(args.sources, "r", encoding="utf-8") as f:
            sources = json.load(f)
    else:
        sources = DEFAULT_SOURCES

    # 时间窗口
    cutoff = None
    if args.since:
        d = datetime.strptime(args.since, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        cutoff = d
    elif args.days and args.days > 0:
        cutoff = datetime.now(timezone.utc) - timedelta(days=args.days)

    # 关键词
    kws = [k.strip().lower() for k in (args.keyword or "").split(",") if k.strip()] if args.keyword else []

    # 抓取
    all_entries = []
    errors = []
    for src in sources:
        ents, err = fetch_source(src)
        if err:
            errors.append(f"{src['name']}: {err}")
        for e in ents[: args.max_per_source]:
            all_entries.append(e)

    # 过滤：时间
    if cutoff is not None:
        kept = []
        for e in all_entries:
            dt = e.get("_published_dt")
            if dt is None:
                kept.append(e)  # 时间未知则保留（无法判断）
            elif dt >= cutoff:
                kept.append(e)
        all_entries = kept

    # 过滤：关键词
    if kws:
        kept = []
        for e in all_entries:
            hay = (e["title"] + " " + e.get("summary", "") + " " + " ".join(e.get("tags", []))).lower()
            if any(k in hay for k in kws):
                kept.append(e)
        all_entries = kept

    # 去重（按归一化链接，保留首次出现）
    seen = set()
    deduped = []
    for e in all_entries:
        key = normalize_link(e["link"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(e)

    # 排序：有时间的在前，新的在前
    deduped.sort(key=lambda e: (e.get("_published_dt") is not None, e.get("_published_dt") or datetime.min.replace(tzinfo=timezone.utc)), reverse=True)

    if args.max_total and args.max_total > 0:
        deduped = deduped[: args.max_total]

    # 清理内部字段
    for e in deduped:
        e.pop("_published_dt", None)

    result = {
        "count": len(deduped),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sources_used": [s["name"] for s in sources],
        "errors": errors,
        "articles": deduped,
    }

    out_json = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(out_json)
        print(f"已写入 {len(deduped)} 条文章 -> {args.output}")
        if errors:
            print(f"警告：{len(errors)} 个信源异常：{'; '.join(errors)}", file=sys.stderr)
    else:
        print(out_json)


if __name__ == "__main__":
    main()
