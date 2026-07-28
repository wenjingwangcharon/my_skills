#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ai-news-weekly 每日无人值守流水线（脚本化，无需人工介入）。

完整流程：
  抓取 RSS/官网 (+) → 只保留带有效链接的文章 → 按链接补全全文正文 →
  LLM 生成单篇摘要卡 → LLM 生成「今日趋势 / 今日小结」→
  组装当日 daily markdown → 渲染自包含 HTML (site/index.html) →
  (可选) 推送到 GitHub Pages 等静态托管。

设计原则：本脚本尽量零依赖（仅 Python 标准库），路径全部相对脚本自身推导，
配置优先读环境变量、其次读同级 config.json，方便「复制即可用」。

配置（环境变量 或 脚本同级 config.json，环境变量优先）：
  AI_NEWS_LLM_BASE     OpenAI 兼容 API 基址（默认 https://api.openai.com/v1）
  AI_NEWS_LLM_KEY      API Key（必填；缺失时降级为「仅用正文/摘要」的极简模式，流水线不中断）
  AI_NEWS_LLM_MODEL    模型名（默认 gpt-4o-mini）
  AI_NEWS_GH_REMOTE    GitHub Pages 仓库 remote（如 https://github.com/user/repo.git）；留空则不推送
  AI_NEWS_OUTPUT       产物根目录（默认 <skill>/output，其下 data/ 与 site/）
  AI_NEWS_CONFIG       config.json 路径（默认 <skill>/config.json）

说明：定时任务触发时不会继承交互式会话的环境变量，因此 key / remote 推荐写入
      <skill>/config.json。该文件位于 site/ 之外，不会被推送到托管平台。

产物：
  <OUTPUT>/data/daily/YYYY-MM-DD.md      当日日报 markdown
  <OUTPUT>/site/index.html               部署用静态页（GitHub Pages 源）
"""
import os, sys, json, re, subprocess, datetime, urllib.request, urllib.error, shutil
from html.parser import HTMLParser

HERE = os.path.dirname(os.path.abspath(__file__))          # .../scripts
SKILL_ROOT = os.path.dirname(HERE)                          # .../ai-news-weekly
CONFIG_PATH = os.environ.get("AI_NEWS_CONFIG", os.path.join(SKILL_ROOT, "config.json"))

SKILL_FEED = os.path.join(HERE, "fetch_feeds.py")
if not os.path.exists(SKILL_FEED):
    # 回退到已安装的 skill 目录（工作区实例未自带 fetch_feeds.py 时也能跑）
    _alt = os.path.join(os.path.expanduser("~"), ".workbuddy", "skills",
                        "ai-news-weekly", "scripts", "fetch_feeds.py")
    if os.path.exists(_alt):
        SKILL_FEED = _alt
PY = sys.executable                                      # 用运行本脚本的同一解释器

TODAY = datetime.date.today().isoformat()

# 正文补全阈值：feed 自带正文不足该字数时，按文章链接抓取原文页补全。
# （注意：这并非「质量闸」。质量闸是「有 http 链接才保留」，见 main()）
MIN_FULLTEXT = 200


# --------------------------------------------------------------------------- 配置读取
def load_config():
    """环境变量优先，其次同级 config.json，最后默认值。"""
    cfg = {}
    if os.path.exists(CONFIG_PATH):
        try:
            cfg = json.load(open(CONFIG_PATH, encoding="utf-8"))
        except Exception as e:
            print(f"[config] 读取 {CONFIG_PATH} 失败：{e}")
    return cfg

_CFG = load_config()
def cfgv(env_name, key, default=""):
    if os.environ.get(env_name):
        return os.environ[env_name]
    return _CFG.get(key, default)

# 产物目录：环境变量 > config.json > 默认 <SKILL_ROOT>/output
OUTPUT_BASE = cfgv("AI_NEWS_OUTPUT", "AI_NEWS_OUTPUT", os.path.join(SKILL_ROOT, "output"))
DATA_DIR = os.path.join(OUTPUT_BASE, "data")
SITE_DIR = os.path.join(OUTPUT_BASE, "site")
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(SITE_DIR, exist_ok=True)

LLM_BASE = cfgv("AI_NEWS_LLM_BASE", "AI_NEWS_LLM_BASE", "https://api.openai.com/v1").rstrip("/")
LLM_KEY = cfgv("AI_NEWS_LLM_KEY", "AI_NEWS_LLM_KEY", "")
LLM_MODEL = cfgv("AI_NEWS_LLM_MODEL", "AI_NEWS_LLM_MODEL", "gpt-4o-mini")
GH_REMOTE = cfgv("AI_NEWS_GH_REMOTE", "AI_NEWS_GH_REMOTE", "")


sys.path.insert(0, HERE)
import build_daily_html


# --------------------------------------------------------------------------- LLM
def llm(system, user, expect_json=False, max_retries=2):
    if not LLM_KEY:
        return None
    url = LLM_BASE + "/chat/completions"
    payload = {
        "model": LLM_MODEL,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
        "temperature": 0.3,
    }
    if expect_json:
        payload["response_format"] = {"type": "json_object"}
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LLM_KEY}",
    })
    last = None
    for _ in range(max_retries):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                resp = json.loads(r.read().decode("utf-8"))
            content = resp["choices"][0]["message"]["content"].strip()
            if expect_json:
                if content.startswith("```"):
                    content = content.strip("`")
                    if content.startswith("json"):
                        content = content[4:]
                return json.loads(content)
            return content
        except Exception as e:  # 网络/解析失败 -> 交给调用方降级
            last = e
    sys.stderr.write(f"[llm-error] {last}\n")
    return None


# --------------------------------------------------------------------------- 抓取
def fetch_articles():
    tmp = os.path.join(DATA_DIR, "latest.json")
    subprocess.run([PY, SKILL_FEED, "--days", "1", "--max-per-source", "8",
                    "--max-total", "60", "--output", tmp], check=True)
    data = json.load(open(tmp, encoding="utf-8"))
    return data.get("articles", []), data.get("errors", [])


# --------------------------------------------------------------------------- 按链接抓原文正文
class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skip = False
        self.in_p = False
        self.parts = []
        self._buf = []
        self.all_text = []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript", "header", "footer", "nav", "aside"):
            self.skip = True
        if tag == "p":
            self.in_p = True

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "header", "footer", "nav", "aside"):
            self.skip = False
        if tag == "p" and self.in_p:
            self.in_p = False
            t = "".join(self._buf).strip()
            if len(t) >= 15:
                self.parts.append(t)
            self._buf = []

    def handle_data(self, data):
        if self.skip:
            return
        if self.in_p:
            self._buf.append(data)
        self.all_text.append(data)


def fetch_fulltext(url, timeout=12, max_chars=4000):
    """按文章链接抓取原文页面并提取正文。失败/被反爬拦截返回 ''（文章仍保留链接）。"""
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/120 Safari/537.36",
            "Accept-Language": "zh-CN,zh;q=0.9",
        })
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read(1_000_000)
            enc = r.headers.get_content_charset()
            if not enc:
                m = re.search(r'charset=["\']?([\w-]+)', raw[:500].decode("ascii", "ignore").lower())
                enc = m.group(1) if m else "utf-8"
            try:
                html = raw.decode(enc)
            except Exception:
                html = raw.decode("utf-8", "ignore")
    except Exception:
        return ""
    ex = _TextExtractor()
    try:
        ex.feed(html)
    except Exception:
        return ""
    body = "\n".join(ex.parts).strip()
    if len(body) < 200:
        body = " ".join(ex.all_text).strip()
    body = re.sub(r"\s+", " ", body)
    return body[:max_chars]


# --------------------------------------------------------------------------- 单篇摘要
def summarize(art):
    content = (art.get("content") or art.get("summary") or "").strip()
    user = (f"标题：{art['title']}\n信源：{art['source']}\n分类：{art.get('category','') or '未知'}\n"
            f"可用正文/摘要：{(content or art['title'])[:3500]}")
    sys_p = ("你是 AI 科技商业新闻编辑。针对单篇文章，只输出 JSON："
             '{"summary": "一句中文摘要，80字内，说清核心信息", '
             '"importance": 1到5的整数（5=重大行业事件，1=边缘），'
             '"toc": ["3到5个要点，每个10字内"]}。不要任何解释。')
    r = llm(sys_p, user, expect_json=True)
    if not r:
        # 降级：优先用正文（质量闸已保证保留文章都有链接，且多数已补全正文），其次摘要/标题
        base = (art.get("content") or art.get("summary") or art["title"]).strip()
        return base[:300], 3, []
    toc = r.get("toc") or []
    if isinstance(toc, str):
        toc = [toc]
    return (r.get("summary") or art["title"])[:300], int(r.get("importance") or 3), toc[:5]


# --------------------------------------------------------------------------- 趋势 + 小结
def summarize_overview(articles):
    titles = "\n".join(f"- {a['title']}（{a['source']}）" for a in articles)
    user = (f"今日共 {len(articles)} 篇 AI 科技商业新闻，标题如下：\n{titles}\n\n"
            "请输出 JSON："
            '{"trend": "一句今日趋势总结，60字内，点明主线与三大焦点", '
            '"bullets": ["4条今日小结要点，每条30字内，涵盖主线/安全/开源/异常等"]}。不要解释。')
    sys_p = "你是 AI 新闻主编，善于从标题中提炼趋势与要点。"
    r = llm(sys_p, user, expect_json=True)
    if not r:
        return (f"今日共收录 {len(articles)} 篇，覆盖多家信源，详见下方卡片。",
                [f"今日收录 {len(articles)} 篇，涉及 AI 科技商业多个方向。",
                 "部分信源抓取异常，详见底部说明。"])
    bullets = r.get("bullets") or []
    if isinstance(bullets, str):
        bullets = [bullets]
    return r.get("trend") or f"今日共收录 {len(articles)} 篇。", bullets[:4]

# --------------------------------------------------------------------------- AI 相关性闸
def is_ai_related(a):
    """用 LLM 判断文章是否「与 AI 强相关」。无 Key 时返回 True（不靠脚本过滤，交给 Agent）。"""
    if not LLM_KEY:
        return True
    title = a.get("title", "")
    cat = a.get("category", "") or ""
    snippet = (a.get("content") or a.get("summary") or "")[:600]
    sys_p = ("你是 AI 资讯筛选器。判断一篇文章是否「与 AI 强相关」。\n"
              "强相关：大模型/模型发布与更新、AI 公司动态、AI 产品/应用/工具、"
              "算力/芯片/AI 基础设施、智能体(Agent)/具身智能/机器人、AI 政策监管、AI 科研突破。\n"
              "非强相关（一律 false）：纯消费电子(手机/电脑)评测、汽车(除非以智驾或车载 AI 系统为核心)、"
              "普通互联网/App 评测、与 AI 无关的财经/税务/社会/生活技巧类。\n"
              "只回答 JSON：{\"ai\": true 或 false}，不要任何解释。")
    user = f"标题：{title}\n分类：{cat}\n正文片段：{snippet}"
    r = llm(sys_p, user, expect_json=True)
    if not r:
        return True  # 判断失败则保留，避免误删
    return bool(r.get("ai", True))

def filter_ai(articles, mode_label=""):
    """丢弃非 AI 强相关文章；无 Key 时原样返回。返回 (保留, 丢弃)。"""
    if not LLM_KEY:
        return articles, []
    kept, dropped = [], []
    for a in articles:
        (kept if is_ai_related(a) else dropped).append(a)
    if dropped:
        by_src = {}
        for a in dropped:
            s = a.get("source", "?")
            by_src[s] = by_src.get(s, 0) + 1
        detail = "、".join(f"{s}×{n}" for s, n in by_src.items())
        print(f"      [AI 闸{mode_label}] 丢弃 {len(dropped)} 篇非 AI 相关 → {detail}；保留 {len(kept)} 篇。")
    return kept, dropped


# --------------------------------------------------------------------------- 组装 md
def build_md(articles, errors, trend, bullets):
    src_order = []
    groups = {}
    for a in articles:
        s = a["source"]
        if s not in groups:
            groups[s] = []
            src_order.append(s)
        groups[s].append(a)

    L = []
    L.append(f"# AI 科技商业日报（{TODAY}）")
    L.append("")
    L.append(f"> 信源：{', '.join(src_order)}")
    L.append(f"> 收录文章：{len(articles)} 篇（自动抓取 + LLM 摘要）")
    L.append("")
    L.append("## 今日趋势")
    L.append(trend)
    L.append("")

    seq = 0
    for s in src_order:
        L.append(f"## {s}")
        L.append("")
        for a in groups[s]:
            seq += 1
            pub = (a.get("published") or "")[:10]
            if not pub:
                pub = "发布时间未知"
            meta = f"{a['source']} · {a.get('category') or '未分类'} · {pub}"
            summary, imp, toc = a.get("_sum", ""), a.get("_imp", 3), a.get("_toc", [])
            L.append(f"### {seq}. {a['title']}")
            L.append(f"- 来源：{meta}")
            L.append(f"- 链接：{a['link']}")
            L.append(f"- 重要性：{imp}")
            L.append("**摘要**")
            L.append(summary)
            if toc:
                L.append("**目录**")
                for i, t in enumerate(toc, 1):
                    L.append(f"{i}. {t}")
            L.append("")

    L.append("## 今日小结")
    for b in bullets:
        L.append(f"- {b}")
    L.append("")
    return "\n".join(L)


# --------------------------------------------------------------------------- 部署（git）
def deploy():
    if not GH_REMOTE:
        print("[deploy] 未配置 AI_NEWS_GH_REMOTE，跳过推送（本地 site/index.html 已就绪）。")
        return
    git = shutil.which("git")
    if not git:
        print("[deploy] 未找到 git，跳过推送。")
        return
    open(os.path.join(SITE_DIR, ".nojekyll"), "w").close()
    try:
        if not os.path.exists(os.path.join(SITE_DIR, ".git")):
            subprocess.run([git, "-C", SITE_DIR, "init"], check=True)
            subprocess.run([git, "-C", SITE_DIR, "remote", "add", "origin", GH_REMOTE], check=True)
        subprocess.run([git, "-C", SITE_DIR, "add", "-A"], check=True)
        msg = f"daily {TODAY}"
        # commit 允许空（无变化则不推）
        rc = subprocess.run([git, "-C", SITE_DIR, "commit", "-m", msg],
                            capture_output=True, text=True)
        if rc.returncode != 0:
            print("[deploy] 无内容变化，无需提交。")
            return
        branch = subprocess.run([git, "-C", SITE_DIR, "rev-parse", "--abbrev-ref", "HEAD"],
                                capture_output=True, text=True).stdout.strip() or "main"
        subprocess.run([git, "-C", SITE_DIR, "push", "-u", "origin", branch], check=True)
        print(f"[deploy] 已推送到 {GH_REMOTE} ({branch})。")
    except subprocess.CalledProcessError as e:
        print(f"[deploy] 推送失败（可能需要先连接托管平台 / 配置凭证）：{e}")


# --------------------------------------------------------------------------- main
def main():
    print(f"[1/5] 抓取信源 ...")
    articles, errors = fetch_articles()
    if not articles:
        print("[!] 未抓到任何文章，终止。")
        sys.exit(1)
    print(f"      抓到 {len(articles)} 篇；异常信源 {len(errors)} 家。")

    # 质量闸：只保留带有效 http 链接的文章（无链接=无法溯源/读原文，直接丢弃）
    linked, nolink = [], []
    for a in articles:
        link = (a.get("link") or "").strip()
        if link.startswith("http"):
            linked.append(a)
        else:
            nolink.append(a)
    if nolink:
        by_src = {}
        for a in nolink:
            by_src[a.get("source", "?")] = by_src.get(a.get("source", "?"), 0) + 1
        detail = "、".join(f"{s}×{n}" for s, n in by_src.items())
        print(f"      质量闸：丢弃 {len(nolink)} 篇（无链接）→ {detail}；保留 {len(linked)} 篇。")
    articles = linked
    if not articles:
        print("[!] 过滤后无可用文章，终止。")
        sys.exit(1)

    # 正文补全：feed 未带全文的，按链接抓取原文页面提取正文（有链接即可溯源/读原文）
    filled = 0
    for a in articles:
        if len((a.get("content") or "").strip()) < MIN_FULLTEXT:
            txt = fetch_fulltext(a["link"])
            if txt:
                a["content"] = txt
                filled += 1
    if filled:
        print(f"      正文补全：从原文链接抓取 {filled} 篇正文成功。")

    # Agent 模式：只抓取+补全正文，写出 latest.json，由 Agent（WorkBuddy 自带模型）写摘要
    # AI 相关性闸（有 Key 时）：先过滤，让 fetch-only 产出的 latest.json 只含 AI 相关文章
    if LLM_KEY:
        articles, _ = filter_ai(articles, "·fetch-only")
        if not articles:
            print("[!] AI 相关性闸过滤后无可用文章，终止。")
            sys.exit(1)

    if "--fetch-only" in sys.argv:
        os.makedirs(DATA_DIR, exist_ok=True)
        lp = os.path.join(DATA_DIR, "latest.json")
        json.dump({"date": TODAY, "articles": articles, "errors": errors},
                  open(lp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"[fetch-only] 已写出 {lp}（{len(articles)} 篇，{len(errors)} 家异常）。"
              f"下一步由 Agent 读取并撰写摘要 markdown。")
        return

    print("[2/5] LLM 生成单篇摘要卡 ...")
    for a in articles:
        a["_sum"], a["_imp"], a["_toc"] = summarize(a)

    print("[3/5] LLM 生成趋势与小结 ...")
    trend, bullets = summarize_overview(articles)

    print("[4/5] 组装当日 markdown ...")
    md = build_md(articles, errors, trend, bullets)
    md_path = os.path.join(DATA_DIR, "daily", f"{TODAY}.md")
    os.makedirs(os.path.dirname(md_path), exist_ok=True)
    open(md_path, "w", encoding="utf-8").write(md)
    print(f"      -> {md_path}")

    print("[5/5] 渲染 HTML 并部署 ...")
    html_path = os.path.join(SITE_DIR, "index.html")
    info = build_daily_html.build(md_path, html_path)
    print(f"      -> {html_path}  (卡片 {info['total']} 张)")
    deploy()
    print("完成。")


if __name__ == "__main__":
    main()
