---
name: xhs-playwright-scraper
description: 用 Playwright 真实浏览器会话抓取小红书内容，支持三种模式——① account：指定小红书号抓全部帖子+评论；② post：给定帖子链接抓该帖内容+评论；③ search：按关键词搜索抓排序靠前的前 N 条帖子+评论。产出带图片的 Excel。当用户要抓某个小红书号/帖子/关键词的帖子与评论、或导出带图 Excel 时使用。已踩过所有坑（red_id 解析、x-s 签名、v2 评论接口、has_more 位置、SPA 点击、图片嵌入），脚本与流程直接可复用。
agent_created: true
---

# 小红书抓取工作流（三种模式）

用 Playwright 注入登录态驱动真实 Chromium（浏览器自动完成 `x-s` 动态签名），按用户需求以三种模式之一抓取内容，并产出「带图片的 Excel」。

## 必填输入（向用户索取）
1. **`xhs_cookie`**：用户登录后的完整 Cookie 串（含 `web_session`/`id_token` 等）。
   - 支持三种写法：① 原始串 `a1=...; web_session=...; ...`；② JSON 数组；③ JSON 对象。写入工作目录的 `cookies.json`。
   - ⚠️ Cookie = 登录态，用完必须提醒用户**退出登录使其失效并删除文件**。
   - **小白不会取 cookie？** 见文末「如何获取小红书登录 Cookie（引导话术）」。
2. **抓取目标**，取决于模式（见下）。

## 先识别模式（关键）
收到抓取请求后，**先判断用户要哪种模式**，再决定要什么参数：
- 给了**帖子链接**（含 `xiaohongshu.com/explore/...` 或 `/discovery/item/...`）→ **post 模式**。
- 给了**关键词 / 话题**（如「济州岛旅游」「618 护肤」）→ **search 模式**。
- 给了**小红书号 / 昵称**（如 `2610125281`）→ **account 模式**。
- **不确定时主动反问**，例如：「你是想抓某个账号的全部帖子、抓某一条具体帖子，还是按关键词搜索一批帖子？把链接/账号/关键词发我，我按对应模式来。」不要凭空假设。

## 三种模式
### 模式 A：account（抓指定账号）
- 输入：`--target <小红书号/red_id/user_id>`。
- 行为：解析出真实 `user_id` → 打开主页 → 提取全部笔记 → 逐篇抓详情+评论。

### 模式 B：post（抓指定帖子）
- 输入：`--url <帖子链接>`（脚本自动从链接清洗出 `note_id` / `xsec_token` / `xsec_source`）。
- 行为：直接打开该帖详情页，收集笔记内容 + 全部评论（含子评论）。
- 也可手工给 `note_id` + `xsec_token`（链接里自带，无需记忆）。

### 模式 C：search（关键词搜索）
- 输入：`--keyword <关键词>`、`--limit <前N条，默认100>`。
- 行为：打开搜索结果页 → 滚动加载、累计去重直到达到 `limit`（或翻完）→ 逐篇抓详情+评论。
- 排序沿用小红书默认推荐序（即「排序靠前」的结果）。

## 环境准备（首次运行前，任意机器）
```bash
# 建一个干净的 Python 环境（二选一）
python -m venv .venv && source .venv/bin/activate     # Linux/macOS
# 或 Windows:  python -m venv .venv && .venv\Scripts\activate

pip install -r requirements.txt
playwright install chromium        # 浏览器自动下载到用户目录，脚本自动定位，无需手填路径
```
- 脚本用 `common.find_chromium()` 自动探测 macOS / Linux / Windows 的 Playwright 浏览器位置，`headless=True` 可用，已加反检测参数。

## 编排步骤
脚本都在 `scripts/`。建议建工作目录（例如 `xhs_work/`）并进入。

### Stage 0 — 准备输入
```bash
mkdir -p xhs_work && cd xhs_work
# 把用户给的 cookie 写成 cookies.json（整串用引号包住即可）
```
`cookies.json` 三种写法都行：
```json
"abRequestId=xxx; a1=xxx; web_session=xxx; id_token=xxx"
```
或 `[{"name":"a1","value":"..."}, ...]` 或 `{"a1":"...","web_session":"..."}`。

### Stage 1 — 抓取（按模式选一条）
```bash
SCRIPTS=./scripts     # 或 skill 的 scripts 目录绝对路径
# A. 账号
python $SCRIPTS/scrape.py --mode account --target 2610125281 --cookie cookies.json --out ./output
# B. 帖子
python $SCRIPTS/scrape.py --mode post --url "https://www.xiaohongshu.com/explore/xxxx?xsec_token=yyy&xsec_source=pc_search" --cookie cookies.json --out ./output
# C. 搜索（前100条）
python $SCRIPTS/scrape.py --mode search --keyword "济州岛旅游" --limit 100 --cookie cookies.json --out ./output
```
产出 `output/xhs_data.json`、`output/notes.csv`、`output/comments.csv`。

### Stage 2 — 下载图片
```bash
python $SCRIPTS/download_images.py --data ./output/xhs_data.json --out ./output
```
从 JSON 的 `note_details[].image_list` 抽 URL 下载到 `output/images/<note_id>/`，回写 JSON 与 CSV。无需重新抓。

### Stage 3 — 生成嵌入图片的 Excel
```bash
python $SCRIPTS/build_xlsx.py --data ./output/xhs_data.json --xlsx ./output/notes.xlsx
```
每行一个帖子，前 11 列元数据，最后按最大图数生成 `image_1..image_N` 列，图片直接嵌入单元格（转 JPEG 缩略图，xlsx 自包含）。

## 关键流程与踩坑（脚本已内置，照做即可）
1. **解析目标**：short 数字/昵称 ≠ 内部 `user_id`（十六进制长串）。脚本：已是 `[0-9a-f]{20,}` 当 user_id；否则用搜索 onebox 解析。
2. **主页/搜索结果提取笔记**：从 DOM `section.note-item a.cover` 取 href → `note_id` + 该笔记**自己的** `xsec_token`（主页有 `display:none` 隐藏 `<a>` 无 token，要点 `a.cover`）。
3. **逐篇抓详情+评论**：直接 `page.goto` 到带 xsec_token 的详情页，页面 JS 自动触发 v2 评论接口；用 `page.on("response")` 监听按 `note_id` 过滤去重。
4. **评论接口是 v2**：`/api/sns/web/v2/comment/page`。评论对象：`id, content, user_info.{user_id,nickname}, like_info.liked_count, create_time, ip_location, sub_comments[]`。
5. **`has_more` 在 `data.has_more`**（不是 `cursor_info.has_more`）。滚动评论区，命中 `has_more is False` 结束；否则滚动上限兜底。
6. **笔记正文**：`/api/sns/web/v1/feed` 响应的 `data.items[].note_card` 含 `title/desc/interact_info/time`。DOM 兜底取 `.title`/`.desc`。
7. **不要**直接 `page.goto` 直连 `/api/.../user_posted` 或 `comment/page` —— 缺 x-s 会 `code=-1`，必须由页面 JS 触发。

## 输出物
- `output/xhs_data.json`：`{target, mode, notes[], note_details[], comments{note_id:[...]}}`。
- `output/notes.csv`：每帖一行，含互动数与图片列（图片列为本地相对路径，用 `|` 分隔）。
- `output/comments.csv`：评论（`parent_id` 标记子评论）。
- `output/images/<note_id>/NN.webp`：图片本地副本。
- `output/notes.xlsx`：嵌入图片的 Excel，每行一帖。

## 时间字段
小红书返回**毫秒时间戳**（如 `1783521931000`）。脚本自动转成北京时间 `YYYY-MM-DD HH:MM:SS` 写入 `time_text`（笔记与评论均有，原始毫秒值保留）；CSV/Excel 的 `time` 列展示可读时间。

## 如何获取小红书登录 Cookie（引导话术，给小白用户）
很多用户不知道 cookie 在哪。**不要只说"把 cookie 给我"**，按下面话术一步步教：

> 你用电脑浏览器（Chrome / Edge 都行）打开 https://www.xiaohongshu.com 并**登录你的账号**，然后：
> 1. 按 **F12**（Mac 按 `Command + Option + I`）打开「开发者工具」。
> 2. 点顶部的 **「网络 / Network」** 标签；如果列表是空的，按 **F5 刷新**一下页面。
> 3. 在左侧请求列表里随便点一条名字带 `xiaohongshu.com` 的请求（比如 `feed` 或首页请求）。
> 4. 在右侧点 **「标头 / Headers」**，往下找到 **「请求标头 / Request Headers」** 里的 **`Cookie`** 这一行。
> 5. 把 `Cookie:` 后面**那一长串**全部复制发给我（通常以 `abRequestId=` 或 `a1=` 开头，包含 `web_session=...`）。
> 6. 如果太长不好复制，也可以用「应用 / Application」标签 → 左侧「Cookie」→ `xiaohongshu.com`，把出现的那些值整段复制给我；或者装个浏览器插件 **Cookie-Editor / EditThisCookie**，点「导出 / Export」把整段复制给我。

引导注意点：
- 提醒用户：**cookie 等同于账号密码，只能发给我这次抓取用，用完我会提醒你退出登录并删掉它，别发给别人或贴到公开地方。**
- 如果用户只给了 `web_session` 一个值，也能用，但带上整段 cookie 更稳（部分接口需要 `a1`/`gid` 等风控字段）。
- 复制时容易多复制一个引号或换行，落地到 `cookies.json` 后先确认 cookie 数量没截断。

## 注意
- 小红书有反爬/风控，大量抓取可能触发验证码；单账号小批量（几十~上百篇笔记、数千评论）通常稳。search 模式 `--limit 100` 偏多，遇到风控可减小。
- 抓取他人公开内容仅用于合规分析；评论含其他用户个人信息，注意用途合规。
- 前台长任务可能被杀，长任务用 `run_in_background` 并在后台轮询。
- CDN 图片 URL 带时间戳会过期，但本地 `images/` 副本是永久的，看图片以本地为准。
