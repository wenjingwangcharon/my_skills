#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 ai-news-weekly 的 daily markdown 渲染成自包含、可交互的 HTML 网页。

设计：函数式 build(src_path, out_path) 可被 run_today.py 直接调用，也支持通过环境变量
AI_NEWS_MD / AI_NEWS_HTML 指定输入输出。「今日趋势」与「今日小结」均从 markdown 读取，
做到数据驱动、布局恒定——每天只变卡片数量，头部 / 导航 / 底部结构始终一致。

风格规范见 references/design.md；本文件是规范的「实现」，改样式只动这里。
"""
import os, re, html, sys, glob

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(HERE)
OUTPUT_BASE = os.environ.get("AI_NEWS_OUTPUT", os.path.join(SKILL_ROOT, "output"))

SRC_COLOR = {
    "量子位": "#3b6ef5", "爱范儿": "#14b8a6", "少数派": "#f59e0b",
    "新智元": "#8b5cf6", "36氪": "#ff6a3d", "APPSO": "#0ea5e9",
}
IMP_COLOR = {5: "#e5484d", 4: "#f76808", 3: "#3b82f6", 2: "#94a3b8", 1: "#cbd5e1"}

def esc(s):
    return html.escape(str(s), quote=True)

def _latest_daily():
    d = os.path.join(OUTPUT_BASE, "data", "daily")
    files = sorted(glob.glob(os.path.join(d, "*.md")), reverse=True)
    return files[0] if files else None

def parse_section(line):
    m = re.match(r"##\s+(.+?)(?:\s*（(\d+)\s*篇[^）]*）)?\s*$", line)
    name = m.group(1).strip() if m else line[3:].strip()
    return name

def parse_article_header(line):
    m = re.match(r"###\s+(\d+)\.\s+(.*)$", line)
    if m:
        return int(m.group(1)), m.group(2).strip()
    return None, line[4:].strip()

def render_toc(items):
    if not items:
        return ""
    def helper(i, lvl):
        out = []
        while i < len(items) and items[i][0] == lvl:
            _, txt = items[i]
            i += 1
            sub = ""
            if i < len(items) and items[i][0] > lvl:
                sub_html, i = helper(i, items[i][0])
                sub = f"<ol>{sub_html}</ol>"
            out.append(f"<li>{esc(txt)}{sub}</li>")
        return "".join(out), i
    body, _ = helper(0, items[0][0])
    return f'<ol class="toc">{body}</ol>'

def card_html(a):
    color = SRC_COLOR.get(a["source"], "#94a3b8")
    imp = a["imp"] or 0
    dots = "".join(
        f'<i class="dot {"on" if i < imp else "off"}" style="--c:{IMP_COLOR.get(imp, "#cbd5e1")}"></i>'
        for i in range(5)
    )
    toc = render_toc(a["toc"])
    nobody_cls = " nobody" if a["nobody"] else ""
    note = ('<div class="note-body">⚠ 正文未获取（微信反爬拦截），以下仅基于标题整理，'
            '建议手动打开链接查看全文。</div>') if a["nobody"] else ""
    return f'''<article class="card{nobody_cls}" data-src="{esc(a['source'])}" data-imp="{imp}" data-seq="{a['num']}" data-title="{esc(a['title'].lower())}" data-url="{esc(a['link'])}">
  <div class="card-head">
    <span class="src-badge" style="background:{color}">{esc(a['source'])}</span>
    <span class="imp" title="重要性 {imp}/5">{dots}<b>&nbsp;{imp}</b></span>
  </div>
  <h3 class="title"><a href="{esc(a['link'])}" target="_blank" rel="noopener">{esc(a['title'])}</a></h3>
  <div class="cat">{esc(a['meta'])}</div>
  <div class="summary">{esc(a['summary'])}</div>
  {toc}
  {note}
</article>'''

def build(src_path=None, out_path=None):
    src_path = src_path or os.environ.get("AI_NEWS_MD") or _latest_daily()
    out_path = out_path or os.environ.get("AI_NEWS_HTML",
                                          os.path.join(OUTPUT_BASE, "site", "index.html"))
    if not src_path or not os.path.exists(src_path):
        raise SystemExit(f"[build] 找不到日报 markdown：{src_path}（先跑 run_today.py 生成）")

    text = open(src_path, encoding="utf-8").read()
    lines = text.split("\n")

    title_full = ""
    date_str = ""
    meta_lines = []
    sections = []
    articles = []
    summary_points = []
    trend_lines = []
    in_summary_section = False
    in_trend_section = False
    cur = None
    seen_section = False

    for line in lines:
        if line.startswith("# "):
            title_full = line[2:].strip()
            m = re.search(r"（(\d{4}-\d{2}-\d{2})）", title_full)
            if m:
                date_str = m.group(1)
            continue
        if line.startswith("## "):
            if cur:
                articles.append(cur); cur = None
            name = parse_section(line)
            if name == "今日趋势":
                in_trend_section = True; in_summary_section = False; seen_section = True
                continue
            if name == "今日小结":
                in_summary_section = True; in_trend_section = False
                continue
            in_trend_section = False; in_summary_section = False; seen_section = True
            if name not in sections:
                sections.append(name)
            continue
        if in_trend_section:
            if line.startswith("### "):
                in_trend_section = False
            elif line.strip():
                trend_lines.append(line.strip())
            if in_trend_section:
                continue
        if in_summary_section:
            if line.startswith("- "):
                summary_points.append(line[2:].strip())
            continue
        if not seen_section:
            if line.startswith("> "):
                meta_lines.append(line[2:].strip())
            continue
        if line.startswith("### "):
            if cur:
                articles.append(cur)
            num, t = parse_article_header(line)
            cur = {"num": num or len(articles) + 1, "title": t, "source": sections[-1] if sections else "",
                   "meta": "", "link": "", "imp": None, "summary": "", "toc": [],
                   "nobody": False, "in_summary": False, "in_toc": False}
            continue
        if cur is None:
            continue
        if line.startswith("- 来源："):
            meta = line[5:].strip()
            cur["meta"] = meta
            src = meta.split(" · ")[0].strip()
            if src:
                cur["source"] = src
        elif line.startswith("- 链接："):
            cur["link"] = line[5:].strip()
        elif line.startswith("- 重要性："):
            mm = re.search(r"\d+", line)
            if mm:
                cur["imp"] = int(mm.group())
        elif line.startswith("- 摘要（基于标题）"):
            cur["nobody"] = True
            cur["summary"] = re.sub(r"^-\s*摘要（基于标题）：", "", line).strip()
        elif line.strip() == "**摘要**":
            cur["in_summary"] = True; cur["in_toc"] = False
        elif line.strip() == "**目录**":
            cur["in_summary"] = False; cur["in_toc"] = True
        else:
            if cur.get("in_summary"):
                cur["summary"] = (cur["summary"] + " " + line.strip()).strip()
            elif cur.get("in_toc"):
                m = re.match(r"^(\s*)(\d+(?:\.\d+)*)\s*(.*)$", line)
                if m:
                    indent = len(m.group(1))
                    level = 1 + indent // 3
                    cur["toc"].append((level, m.group(0).strip()))
    if cur:
        articles.append(cur)

    cards_html = "\n".join(card_html(a) for a in articles)

    total = len(articles)
    avail_src = len(sections)
    high = sum(1 for a in articles if (a["imp"] or 0) >= 4)
    waic = sum(1 for a in articles if "WAIC" in (a["meta"] or ""))
    trend_text = " ".join(trend_lines).strip()
    if not trend_text:
        trend_text = f"今日共收录 {total} 篇，覆盖 {avail_src} 家信源，详见下方卡片。"

    summary_html = "\n".join(f"<li>{esc(p)}</li>" for p in summary_points)

    doc = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AI 科技商业日报 · {date_str}</title>
<style>
  :root{{--bg:#f5f6f8;--card:#fff;--text:#1d2129;--muted:#86909c;--border:#e5e6eb;--accent:#3b6ef5;}}
  *{{box-sizing:border-box}}
  body{{margin:0;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;background:var(--bg);color:var(--text);line-height:1.62;}}
  .container{{max-width:1140px;margin:0 auto;padding:34px 20px 90px;}}
  header h1{{font-size:30px;margin:0 0 6px;letter-spacing:.5px;}}
  .sub{{color:var(--muted);font-size:14px;}}
  .meta-row{{display:flex;flex-wrap:wrap;gap:8px;margin-top:14px;}}
  .meta-chip{{background:#eef1f6;color:#51565d;font-size:12.5px;padding:5px 11px;border-radius:999px;}}
  .trend-summary{{background:var(--card);border:1px solid var(--border);border-radius:14px;padding:18px 20px;margin:26px 0;}}
  .trend-summary h2{{margin:0 0 10px;font-size:16px;color:var(--accent);}}
  .trend-summary p{{margin:0;font-size:14px;line-height:1.7;color:#3c4250;}}
  .trend-summary b{{color:var(--text);}}
  .grid{{display:grid;grid-template-columns:repeat(2,1fr);gap:16px;}}
  .card{{background:var(--card);border:1px solid var(--border);border-radius:14px;padding:17px 18px 15px;position:relative;overflow:hidden;transition:box-shadow .18s,transform .18s;cursor:pointer;}}
  .card::before{{content:"";position:absolute;left:0;top:0;bottom:0;width:4px;background:var(--src-c,#ccc);}}
  .card:hover{{box-shadow:0 6px 22px rgba(20,30,60,.08);transform:translateY(-2px);}}
  .card.nobody{{opacity:.74;}}
  .card-head{{display:flex;align-items:center;justify-content:space-between;gap:8px;}}
  .src-badge{{font-size:12px;font-weight:600;color:#fff;padding:3px 10px;border-radius:7px;}}
  .imp{{display:inline-flex;align-items:center;gap:3px;}}
  .imp .dot{{width:9px;height:9px;border-radius:50%;background:#e3e6eb;display:inline-block;}}
  .imp .dot.on{{background:var(--c);}}
  .imp b{{font-size:12px;color:var(--muted);font-weight:600;}}
  .title{{font-size:16.5px;font-weight:650;margin:11px 0 4px;line-height:1.42;}}
  .title a{{color:inherit;text-decoration:none;}}
  .title a:hover{{color:var(--accent);text-decoration:underline;}}
  .cat{{font-size:12.5px;color:var(--muted);}}
  .summary{{font-size:14px;color:#3c4250;margin:10px 0;}}
  .toc{{font-size:13px;color:#4e5969;padding-left:20px;margin:8px 0 2px;}}
  .toc li{{margin:2px 0;}}
  .note-body{{font-size:12.5px;color:#b0b7c3;font-style:italic;margin-top:8px;}}
  .summary-box{{margin-top:34px;background:linear-gradient(135deg,#eef3ff,#f6f0ff);border:1px solid #d9e2ff;border-radius:16px;padding:22px 26px;}}
  .summary-box h2{{margin:0 0 12px;font-size:19px;}}
  .summary-box ul{{margin:0;padding-left:20px;}}
  .summary-box li{{margin:8px 0;font-size:14px;}}
  footer{{text-align:center;color:#b0b7c3;font-size:12px;margin-top:40px;}}
  @media (max-width:760px){{.grid{{grid-template-columns:1fr;}}}}
</style>
</head>
<body>
<div class="container">
  <header>
    <h1>AI 科技商业日报</h1>
    <div class="sub">📅 {date_str} · 由 <code>ai-news-weekly</code> skill 自动生成</div>
    <div class="meta-row">
      {''.join(f'<span class="meta-chip">{esc(m)}</span>' for m in meta_lines)}
    </div>
  </header>

  <section class="trend-summary">
    <h2>📈 今日趋势</h2>
    <p>{esc(trend_text)}</p>
  </section>

  <div class="grid" id="grid">
    {cards_html}
  </div>

  <div class="summary-box">
    <h2>📌 今日小结</h2>
    <ul>{summary_html}</ul>
  </div>

  <footer>本页由 daily markdown 自动渲染 · 数据时间 {date_str}</footer>
</div>

<script>
  const cards = Array.from(document.querySelectorAll('.card'));
  cards.forEach(c => {{
    if (c.dataset.url) {{
      c.addEventListener('click', e => {{
        if (e.target.closest('a')) return;
        window.open(c.dataset.url, '_blank', 'noopener');
      }});
    }}
  }});
</script>
</body>
</html>'''

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    open(out_path, "w", encoding="utf-8").write(doc)
    return {"total": total, "sources": sections, "high": high, "waic": waic,
            "summary_pts": len(summary_points), "out": out_path}


if __name__ == "__main__":
    info = build()
    print(f"OK -> {info['out']}")
    print(f"articles={info['total']} sources={info['sources']} high={info['high']} waic={info['waic']} summary_pts={info['summary_pts']}")
