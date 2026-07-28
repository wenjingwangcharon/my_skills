# 部署与定时更新指南（deploy）

本 skill 的产出是 `output/site/index.html`——一个**自包含静态页**。部署 = 把这个文件放到任何
静态托管，并把「更新」做成一个每天重跑 `run_today.py` 的动作。风格/布局/头部/尾部完全由
`build_daily_html.py` 固定，每天只变卡片数量，网址不变。

---

## 1. 本地先跑通（验证）

```bash
cd ai-news-weekly
cp config.example.json config.json      # 填入 LLM Key 与仓库地址
python scripts/run_today.py
```

- 无 LLM Key 也能跑（自动降级为「仅用正文/摘要」的极简摘要，不中断）。
- 产物：`output/data/daily/YYYY-MM-DD.md` 与 `output/site/index.html`。
- 想单独改样式后只重渲染网页：`python scripts/build_daily_html.py`（自动找最新的 daily md）。

---

## 2. 部署方式（任选其一，关键是「固定网址」）

### A. GitHub Pages（推荐，免费、URL 固定）

1. 建仓库：仓库名 `你的用户名.github.io` → 网址直接是 `https://你的用户名.github.io`；
   或任意名 `repo`，在仓库 **Settings → Pages** 选部署分支即可（网址 `https://你的用户名.github.io/repo`）。
2. 在 `config.json` 填 `"AI_NEWS_GH_REMOTE":"https://github.com/你的用户名/仓库.git"`。
3. `run_today.py` 末尾会自动：`site/` 内 `git init → add → commit → push` 到该 remote
   （自动写 `.nojekyll` 适配 Pages）。首次需本机已连 GitHub（HTTPS 凭证或 SSH）。
4. 之后每次跑流水线，网页即更新到同一网址。

> 注意：`site/` 是独立 git 仓库（仅含静态页），`config.json` 在 `site/` 之外不会被推送。
> 若把整个 skill 目录也提交了，记得保留 `.gitignore`（忽略 `config.json` 与 `output/`）。

### B. Vercel / Netlify / Cloudflare Pages

- 这些平台支持「拖一个文件夹部署」或 CLI 推送。
- 把 `output/site/` 当作站点根目录即可。可写一小段部署脚本，在 `run_today.py` 之后调用
  平台 CLI（如 `vercel --prod` / `netlify deploy --prod --dir output/site`），
  或把 `output/site` 作为构建产物目录接入 Git 自动部署。

### C. 自有服务器 / 对象存储（OSS / COS / S3）

- 用 `scp` / `rsync` / 云 SDK 把 `output/site/*` 覆盖到站点目录或存储桶。
- 在 `run_today.py` 的 `deploy()` 里加一步即可（或另写 `deploy_custom()`）。

### D. WorkBuddy CloudStudio 预览（仅看效果，URL 会变）

- 适合临时预览，不适合长期固定访问——每次部署会新建 workspace，URL 随之变化。

---

## 3. 更新方式（每天自动刷新同一网址）

**核心思想**：不做「增量更新页面」，而是「每天重新生成整页覆盖」。因为渲染是数据驱动的，
重新生成的页面风格 100% 一致，只是卡片数量/内容不同——这正是「头部尾部结构恒定」的来源。

更新步骤（每天由定时任务一键完成）：
1. 重新抓取信源（`fetch_feeds.py`）。
2. 重新生成当日 daily markdown（`run_today.py`）。
3. 重新渲染 `index.html`（`build_daily_html.py`）。
4. 覆盖推送到托管（`deploy()`）。

---

## 4. 定时任务配置

### 方式一：WorkBuddy 自动化（本项目已建示例）

在 WorkBuddy 中创建「每日」自动化（如每天 08:00），prompt 大意：

```
运行 python <skill>/scripts/run_today.py
（Key 与 remote 已写入 <skill>/config.json，无需环境变量）
完成后用一句中文汇报：今日卡片数、是否成功推送。
```

要点：**定时任务不会继承交互式会话的环境变量**，所以 Key/remote 必须落在 `config.json`
（脚本已支持读取同级 config.json）。

### 方式二：系统 cron / 任务计划程序

```cron
# 每天 08:00
0 8 * * * cd /path/to/ai-news-weekly && /usr/bin/python3 scripts/run_today.py >> cron.log 2>&1
```

### 方式三：GitHub Actions（若仓库已含 site/ 自部署）

在仓库加 `.github/workflows/daily.yml`，用 `cron` 触发 `run_today.py` 并 `git push` 回 Pages 分支。
注意 Actions 秘密里放 `AI_NEWS_LLM_KEY`（脚本支持读取环境变量，优先于 config.json）。

---

## 5. 容错与可观测

- **信源挂了**：`fetch_feeds.py` 对单源失败隔离、优雅降级，日报注明异常信源，不中断。
- **LLM 挂了 / 无 Key**：`summarize()` 自动降级为「用正文/摘要」的占位摘要，流水线不中断。
- **推送失败**：`deploy()` 捕获异常并告警，本地 `site/index.html` 仍可用。
- 日志：流水线每步打印 `[n/5] ...`，cron 时重定向到日志文件便于排查。
