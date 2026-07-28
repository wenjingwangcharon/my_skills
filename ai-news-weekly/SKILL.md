---
name: ai-news-weekly
description: 'AI 科技商业新闻日报技能。采集新智元、36氪、量子位、APPSO 等硬核科技/商业媒体最新 AI 新闻，生成结构化日报 markdown 并渲染为自包含可交互网页（site/index.html），支持 GitHub Pages 等静态托管与每日定时自动更新。两种用法：①Agent 手动按流程生成；②无人值守脚本流水线（run_today.py，抓取→摘要→渲染→部署一键完成，仅标准库+可选 LLM API）。对应 Coze 工作流 weixinnews_XZY（已扩展为多信源+日报+网页+自动部署）。'
agent_created: true
---

# AI 科技商业新闻日报

## 概述

把原 Coze 工作流 `weixinnews_XZY`（仅抓「新智元」一个信源）改造为可复用的**多信源采集 + 日报 + 网页 + 每日自动更新**技能。

两种用法（同一套抓取与渲染内核）：

- **无人值守流水线（脚本模式）**：运行 `scripts/run_today.py`，自动完成
  「抓取 → 只保留有链接的文章 → 按链接补全正文 → LLM 摘要卡 → LLM 趋势/小结 →
  生成 daily markdown → 渲染网页 → 推送托管」，全程零人工。仅需标准库，LLM 为可选（无 Key 降级）。
  适合已配 LLM API Key 的用户。
- **Agent 模式（零 Key，推荐作每日自动化）**：抓取与渲染仍由脚本承担，但**摘要/趋势/小结改由
  WorkBuddy 自带模型撰写**，无需任何外部 LLM Key。通过 `run_today.py --fetch-only` 产出 JSON，
  Agent 读后写 markdown，再渲染推送。本技能内置的每日自动化即用此模式。

**网页特性**：`site/index.html` 是单文件、零依赖、浅色、可交互（信源筛选 / 高重要性切换 /
标题搜索 / 排序 / 整卡跳转原文）。风格由 `build_daily_html.py` 固定，**每天只变卡片数量**，
头部（标题/日期/chips）、「今日趋势」、导航、底部（今日小结/footer）结构恒定。

---

## 目录结构

```
ai-news-weekly/
├── SKILL.md                       # 本文件（完整指南）
├── config.example.json           # 配置模板（复制到 config.json 填值，密钥勿提交）
├── .gitignore                     # 忽略 config.json 与 output/
├── scripts/
│   ├── fetch_feeds.py             # 抓取：RSS/Atom + WordPress API，容错/去重/过滤
│   ├── run_today.py               # 无人值守流水线（调度一切）
│   └── build_daily_html.py        # daily markdown → 自包含交互网页
├── references/
│   ├── sources.md                 # 默认信源清单、扩展信源、自定义格式
│   ├── prompts.md                 # 摘要卡/周报规范（Agent 模式遵循）
│   ├── design.md                  # 网页设计规范（配色/布局/组件/交互）
│   └── deploy.md                  # 部署 + 定时更新指南
└── output/                        # 运行时产物（gitignore；site/ 用于部署）
    ├── data/daily/YYYY-MM-DD.md
    └── site/index.html
```

---

## 快速开始（无人值守流水线）

```bash
cd ai-news-weekly
cp config.example.json config.json
# 编辑 config.json：填 AI_NEWS_LLM_KEY（可选）与 AI_NEWS_GH_REMOTE（可选）
python scripts/run_today.py
```

- 零依赖：纯 Python 标准库，无需 `pip install`。
- 无 LLM Key 也能跑：摘要自动降级为「用正文/摘要」的极简版，流水线不中断。
- 路径全部相对脚本自身推导，配置读 `config.json`（或环境变量），**复制即可用**。
- 产物：`output/data/daily/YYYY-MM-DD.md` 与 `output/site/index.html`。
- 单独改样式后只重渲染网页：`python scripts/build_daily_html.py`（自动找最新 daily md）。

---

## 数据流

```
fetch_feeds.py ──► latest.json (articles[])
      │
      ▼
[质量闸] 只保留 link 以 http 开头的文章
      │
      ▼
[正文补全] feed 无全文的，按 link 抓原文页提取正文（失败仍保留链接）
      │
      ▼
[LLM 摘要] 每篇 → {summary, importance 1-5, toc[]}   （无 Key 降级）
      │
      ▼  Agent 模式：此步改由 Agent 读 latest.json 后直接写 daily markdown，跳过 LLM API
[LLM 总览] 全部标题 → {trend 今日趋势, bullets 今日小结}
      │
      ▼
build_md() ──► output/data/daily/YYYY-MM-DD.md
      │
      ▼
build_daily_html.build() ──► output/site/index.html   （数据驱动，布局恒定）
      │
      ▼
deploy() ──► （可选）git 推送 site/ 到 GitHub Pages 等
```

---

## 网页设计

见 `references/design.md` 完整规范。要点：浅色主题、`--accent:#3b6ef5`；
信源徽标按源着色、卡片左侧 4px 色条；sticky 吸顶导航含信源 pill / 高重要性切换 / 搜索 / 排序；
「📈 今日趋势」摘要区；「📌 今日小结」渐变卡片；响应式（窄屏单列）。
改样式只动 `build_daily_html.py` 的 CSS/JS，不影响数据层。

---

## 部署与每日更新

见 `references/deploy.md`。关键：部署 = 把 `site/index.html` 放到静态托管；
更新 = 每天重跑 `run_today.py` 覆盖同一文件（风格恒定）。支持 GitHub Pages（脚本内置 git 推送）、
Vercel/Netlify、自有服务器/对象存储；定时可用 WorkBuddy 自动化、系统 cron 或 GitHub Actions。
**定时任务不会继承交互式环境变量，Key/remote 务必写入 `config.json`。**

---

## 信源

默认 10 家：新智元（WordPress API 自带正文）、36氪（官网 RSS，已验证可用）、智东西（WordPress API 自带正文，已验证可用）、
量子位、APPSO（ifanr 作者过滤）、机器之心、爱范儿、少数派、极客公园、虎嗅。
**已排除**：财新（正文付费墙，按需求剔除）；甲子光年（SPA 站点、无标准 RSS、WP API 重定向死循环，当前抓取器无法获取，待评估首页抓取模式）。
完整清单、可达性备注、扩展信源与自定义 JSON 见
`references/sources.md`。增删信源改 `fetch_feeds.py` 的 `DEFAULT_SOURCES` 或运行时 `--sources`。
容错：每源可配 `fallback` 候选；超时重试 1 次，确定性错误立即失败；单源失败隔离不中断。

---

## 提示词 / 摘要规范

- **无人值守模式**：摘要由 `run_today.py` 内的 `summarize()` / `summarize_overview()` 调 LLM API
  生成，提示词已内嵌（单篇 JSON：summary/importance/toc；总览 JSON：trend/bullets）。
- **Agent 手动模式**：遵循 `references/prompts.md` 的「单篇摘要卡规范 / 周报综合规范」。
  该文件同时存档了原 Coze 工作流的三段提示词，便于追溯。

---

## Agent 模式（零 Key 每日自动化，推荐）

由 WorkBuddy 自带模型直接撰写摘要/趋势/小结，**无需任何外部 LLM Key**。与脚本模式共享抓取与渲染内核，
仅「摘要」一步改由 Agent 完成。本技能的每日定时自动化默认走此模式。

流程：

1. 抓取并补全正文（不调 LLM）：
   ```bash
   python scripts/run_today.py --fetch-only
   ```
   产出 `output/data/latest.json`：`{date, articles[], errors[]}`。
   `articles[]` 每条已含 `title / link / source / category / published / content`
   （`content` 为按链接抓到的原文正文；可能为空则降级）。
2. Agent 读取 `latest.json`，**逐篇基于 `content` 撰写摘要卡**，汇总为
   `output/data/daily/YYYY-MM-DD.md`。markdown 必须严格符合下方格式（渲染器按此解析）。

   **内容门槛（硬性，务必遵守）**：日报只收录**与 AI 强相关**的文章，范围包括——
   大模型 / 模型发布与更新、AI 公司动态、AI 产品 / 应用 / 工具、算力 / 芯片 / AI 基础设施、
   智能体(Agent) / 具身智能 / 机器人、AI 政策与监管、AI 科研突破等。
   **凡是下列内容一律剔除，不要写入日报**：纯消费电子（手机/电脑评测）、汽车（除非以智驾或车载 AI 系统为核心）、
   普通互联网 / App 评测、与 AI 无关的财经 / 税务 / 社会 / 生活技巧类。
   若某信源整批偏题（如 爱范儿 的汽车 / 数码、少数派 的 App 评测 / 桌搭技巧），
   只挑其中**真正 AI 相关**的少数几条，宁缺毋滥。

   **每日上限（硬性）**：日报**最多收录 30 篇**。全部候选先按「重要性」降序（5→1）排好，
   只保留前 30 篇，其余一律剔除——即便当日好稿再多也不超过 30；宁缺毋滥，不凑数。
3. 渲染网页：
   ```bash
   python scripts/build_daily_html.py
   # 或显式指定：AI_NEWS_MD=路径 AI_NEWS_HTML=路径 python scripts/build_daily_html.py
   ```
4. 推送（已配 `AI_NEWS_GH_REMOTE`，或本地 `output/site/.git` 已设 `origin`）：
   ```bash
   cd output/site && git add -A && git commit -m "daily YYYY-MM-DD" && git push origin main
   ```

### daily markdown 格式（必须严格遵循，否则渲染错乱）

```
# AI 科技商业日报（YYYY-MM-DD）

> 信源：新智元, 36氪, 量子位, ...
> 收录文章：N 篇（自动抓取 + Agent 摘要）
> 抓取异常：M 家信源失败（<列表>）

## 今日趋势
<2-4 句，点明今日主线与 2-3 个焦点；相关时提及 WAIC 等关键词>

### 1. <文章标题>            ← 文章全局按「重要性」降序排列（5→1），不按信源分组
- 来源：<信源名1> · <category 或 未分类> · <发布日期 YYYY-MM-DD 或 发布时间未知>
- 链接：<文章 URL>
- 重要性：<1-5 整数>
**摘要**
<3-5 句中文摘要，基于 content 正文，客观准确，不编造>
**目录**
<可选：若文章有清晰小节，列 1. / 2. / 3.，可嵌套 2.1 / 2.2>

### 2. <文章标题>
...

## 今日小结
- <要点 1>
- <要点 2>
- <要点 3>
```

解析要点（决定渲染是否正确）：
- 标题行 `# AI 科技商业日报（YYYY-MM-DD）` 的日期会被提取；`> ` 开头的元信息行必须放在第一个 `##` 之前。
- `## 今日趋势` 之后、`## 今日小结` 之前的非空行拼成趋势文案；`## 今日小结` 下 `- ` 行是要点。
- 文章直接以 `### N. 标题` 连续排列在趋势之后、小结之前，**不要写 `## 信源名` 分组标题**；`N` 为全局递增序号（1..总篇数），按重要性降序。卡片来源由每篇的 `- 来源：` 行（第一个 ` · ` 之前的部分）驱动，徽章自动显示。
- 每篇文章**必须有** `- 重要性：<整数>`，否则重要性显示为 0。
- 摘要写在 `**摘要**` 独占一行之后；目录写在 `**目录**` 独占一行之后（可多级缩进）。
- 微信公众号镜像类（如机器之心）仅标题、无正文：仍以正常卡片呈现，摘要基于标题客观简述，注明需点开原文，勿反复抓取浪费额度。

---

## 错误处理与容错

- 单信源失败：`fetch_feeds.py` 隔离 + 降级，`errors` 字段记录原因；日报注明异常信源。
- 无链接文章：质量闸直接丢弃（用户需求：只保留能溯源/读原文者）。
- LLM 不可用 / 无 Key：`summarize()` 降级为用正文/摘要的占位摘要，流水线不中断。
- 推送失败：`deploy()` 捕获告警，本地 `site/index.html` 仍可用。

---

## 与原 Coze 工作流的差异

- 入口从 Coze 私有插件改为公开信源（官网 RSS / WordPress API），无需 API Key；
  微信公众号镜像仅作官方 feed 失活时的兜底。
- 抓取脚本内置容错（fallback 候选、超时重试、单源隔离）。
- 新增「网页渲染」与「每日自动部署」能力，输出自包含静态页，可固定网址长期访问。
- 新增「周报」聚合（Agent 模式）；无人值守模式专注于每日日报。
- 原工作流三段提示词完整存档于 `references/prompts.md` 第一节。

---

## 复制给他人使用（checklist）

1. 把整个 `ai-news-weekly/` 目录发给对方（或提交到 Git 仓库）。
2. 对方 `cp config.example.json config.json` 并填 `AI_NEWS_LLM_KEY` / `AI_NEWS_GH_REMOTE`。
3. 对方 `python scripts/run_today.py` 即可每天生成并（可选）部署网页。
4. 无需安装任何 Python 包；若用 GitHub Pages，需本机连 GitHub 凭证。
5. `.gitignore` 已忽略 `config.json` 与 `output/`，分享时不泄露密钥、不夹带产物。
