# 我的 WorkBuddy Skills 合集（分享清单）

> 原创 skills 集合，可直接分享给其他人使用。

- **仓库**：https://github.com/wenjingwangcharon/my_skills
- **整仓下载（zip）**：https://github.com/wenjingwangcharon/my_skills/archive/refs/heads/main.zip
- **说明**：单个 skill 没有独立 zip 下载，对方 `git clone` 后取对应文件夹即可；下面每个都给了文件夹直链。

## 使用方法
1. `git clone https://github.com/wenjingwangcharon/my_skills.git`
2. 把需要的 skill 文件夹整体复制到本机 `~/.workbuddy/skills/`（Windows 为 `C:\Users\<用户名>\.workbuddy\skills\`）。
3. 重启 / 新建对话即可触发。部分 skill 依赖外部账号或 API（见各条说明），需自行配置。

---

## 一、原创 skills（agent_created，共 9 个）

### 1. ai-news-weekly — AI 科技商业新闻日报
- 采集新智元 / 36氪 / 量子位 / APPSO 等多信源最新 AI 新闻 → 结构化日报 markdown → 渲染为自包含交互网页，支持 GitHub Pages 自动部署与每日定时更新。
- 链接：https://github.com/wenjingwangcharon/my_skills/tree/main/ai-news-weekly

### 2. email-interview-organizer — 面试邮件整理
- 从 QQ 邮箱拉取邮件，筛选面试 / 招聘类，分类（日程 / 待办 / 信息）并自动创建飞书日历事件或任务；零 API 成本，靠 Agent 自身能力。
- 链接：https://github.com/wenjingwangcharon/my_skills/tree/main/email-interview-organizer

### 3. emblem-logo-design — Emblem 图形 logo 设计
- 从业务功能提炼核心隐喻，设计线条干净、可单色、可缩放的 emblem，含 favicon 小尺寸验证工作流。
- 链接：https://github.com/wenjingwangcharon/my_skills/tree/main/emblem-logo-design

### 4. interview-recording-organizer — 面试录音转写整理
- 把录音转写文本按"问题 + 回答"结构化拆分，过滤语气词 / 寒暄，修正错别字，输出结构化问答文档。
- 链接：https://github.com/wenjingwangcharon/my_skills/tree/main/interview-recording-organizer

### 5. investment-tracker — 投资追踪与宏观研究
- 基于"七层国家分析框架"建立可持续更新的投资研究工作台，指导获取关键数据、判断更新优先级。
- 链接：https://github.com/wenjingwangcharon/my_skills/tree/main/investment-tracker

### 6. job-application-tracker — 面试投递追踪
- 投递信息结构化存为 JSON，模糊匹配定位记录、动态状态管理、终态标记，随时新增状态类型。
- 链接：https://github.com/wenjingwangcharon/my_skills/tree/main/job-application-tracker

### 7. wordmark-logo-letter-substitution — 字标 logo 字母替换
- 基于固定品牌名做字标，把 1–2 个字母替换成图标（在 Ardot 画布实现）的可靠工作流。
- 链接：https://github.com/wenjingwangcharon/my_skills/tree/main/wordmark-logo-letter-substitution

### 8. xhs-playwright-scraper — 小红书抓取
- Playwright 真实浏览器会话，支持账号 / 帖子 / 搜索三种模式，产出带图 Excel（已解决 x-s 签名等坑）。
- 链接：https://github.com/wenjingwangcharon/my_skills/tree/main/xhs-playwright-scraper

### 9. xiaohongshu-note-organizer — 小红书笔记整理
- 给定笔记链接，提取标题 / 正文 / 图片 / 标签，识别图中文字，整合为结构化 Markdown。
- 链接：https://github.com/wenjingwangcharon/my_skills/tree/main/xiaohongshu-note-organizer

---

## 二、其他 skills（共 7 个，其中 4 个已停用）

> 标〔已停用〕的，其 `SKILL.md` 内含 `disable: true`，导入后默认不生效；需要时在文件里改为 `false` 即可。

### 10. activity-data-processor 〔已停用〕 — 活动算力数据处理
- 把 ima 算力活动底表转换为周报 Excel（双 sheet），支持每周追加。
- 链接：https://github.com/wenjingwangcharon/my_skills/tree/main/activity-data-processor

### 11. beacon-data-fetcher — 灯塔(Beacon) DataInsight 数据获取
- 自动化从腾讯灯塔平台取数，支持页面抓取 / 下载导出两种模式、TV / 敏捷分析两种页面类型。
- 链接：https://github.com/wenjingwangcharon/my_skills/tree/main/beacon-data-fetcher

### 12. monthly-macro-report 〔已停用〕 — 月度宏观经济分析报告
- 搜集中国宏观数据（GDP / CPI / PMI / 社融等）、财政货币政策、产业政策、全球经济，判断经济周期位置，推导利好 / 回避板块。
- 链接：https://github.com/wenjingwangcharon/my_skills/tree/main/monthly-macro-report

### 13. morning-market-scan 〔已停用〕 — 每日晨间市场扫描
- 搜集隔夜外盘、A50、商品、汇率利率、国内要闻 / 公告，整理成结构化报告并给市场基调预判与操作建议。
- 链接：https://github.com/wenjingwangcharon/my_skills/tree/main/morning-market-scan

### 14. suanli-weekly — 算力周报
- 算力底表处理 + 饼图、算力券周报（仪表盘 API + SQL）、活动算力周报 SQL 三个子任务。
- 链接：https://github.com/wenjingwangcharon/my_skills/tree/main/suanli-weekly

### 15. table-to-chart — 表格生成图表偏好
- 把数据表渲染成图表，固化该用户的视觉 / 协作偏好（三色配色、极简、柱高精确等），用 show_widget 内联渲染。
- 链接：https://github.com/wenjingwangcharon/my_skills/tree/main/table-to-chart

### 16. tencent-survey-images-to-excel 〔已停用〕 — 腾讯问卷数据整理
- 把问卷导出原始数据清洗为含内嵌图片的成品 Excel，可选访问内容链接打分。
- 链接：https://github.com/wenjingwangcharon/my_skills/tree/main/tencent-survey-images-to-excel

---

## 备注
- 部分 skill 依赖外部账号 / API（QQ 邮箱、飞书、小红书 cookie、腾讯灯塔、腾讯问卷等），对方需自行配置。
- `disable: true` 的 skill 只是暂时关闭，不影响其余 skill 使用。
