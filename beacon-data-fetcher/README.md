# 🔦 灯塔数据获取助手 (Beacon Data Fetcher)

> 一句话让 AI 帮你从灯塔平台自动拉取数据，告别手动导出的繁琐操作！

## ✨ 这个 Skill 能做什么？

**自动化从腾讯灯塔 (Beacon) DataInsight 平台获取数据**，支持：

- 📊 **页面抓取模式** — 通过拦截 API 响应获取表格/图表数据
- 📥 **下载导出模式** — 自动点击下载按钮，获取完整 CSV 文件（推荐）
- 🔄 **自动修改时间范围** — 支持 TV 模式和敏捷分析模式的天数调整
- 🔐 **扫码登录** — 通过 iOA Mobile 扫码完成 OA 认证

---

## 🚀 快速开始

### 第一步：安装 Skill

将 `beacon-data-fetcher` 文件夹复制到你的 CodeBuddy 项目的 `.codebuddy/skills/` 目录下：

```
你的项目/
└── .codebuddy/
    └── skills/
        └── beacon-data-fetcher/    ← 放在这里
            ├── SKILL.md
            ├── scripts/
            └── references/
```

### 第二步：确保环境就绪

**必要依赖：**
- Python 3.8+（`python3` 或 `python` 命令可用）
- Playwright 浏览器自动化库
- 支持 Linux / macOS / Windows

```bash
# 安装 Playwright（如果还没安装）
pip install playwright
playwright install chromium
```

### 第三步：开始使用！

直接用自然语言告诉 CodeBuddy 你想要什么数据：

---

## 💬 使用示例

### 示例 1：下载灯塔看板数据

```
帮我从这个灯塔页面下载数据：
https://beacon.woa.com/datainsight/xxx/PanelMax/xxx
```

### 示例 2：获取过去 180 天的数据

```
从这个灯塔链接拉取 180 天的数据：
https://beacon.woa.com/datainsight/xxx/Analytics_Mode/xxx
```

### 示例 3：抓取页面表格数据

```
帮我抓取这个灯塔页面的数据，保存到 /data/output 目录：
https://beacon.woa.com/datainsight/xxx/PanelMax/xxx
```

### 触发关键词

当你的对话中包含以下关键词时，这个 Skill 会被自动激活：

| 关键词 | 示例 |
|-------|------|
| `灯塔数据` | "帮我拉灯塔数据" |
| `beacon数据` | "获取 beacon 数据" |
| `拉取灯塔` | "拉取灯塔这个链接的数据" |
| `灯塔取数` | "灯塔取数，链接是..." |
| `灯塔导出` | "灯塔导出 180 天" |

---

## 📱 登录认证

首次使用或登录态过期时，需要通过 **iOA Mobile 扫码登录**：

1. AI 会自动启动一个本地网页，显示二维码
2. 打开 **iOA Mobile 3.2+** App（企业微信工作台搜索"iOA"）
3. 使用 App 扫描二维码完成登录
4. 登录成功后，AI 会自动继续数据获取任务

> 💡 **提示**：登录态会被保存，短期内再次使用无需重复扫码

> 💡 **iOA 快捷登录兼容**：如果你本地安装了 iOA 客户端，灯塔登录页可能显示"快速登录"而非二维码。脚本会自动检测并切换到扫码模式，无需人工干预。

---

## 🎯 支持的页面类型

| 页面类型 | URL 特征 | 说明 |
|---------|----------|------|
| **TV 模式** | 包含 `/PanelMax/` | 面板看板，通过"探索分析"修改时间 |
| **敏捷分析** | 包含 `/Analytics_Mode/` | 灵活分析页，通过"时间设置"修改时间 |
| **事件分析** | 包含 `/New_Event_Modify/` | 事件分析，使用 TV 模式方式 |

AI 会自动检测页面类型，你不需要关心具体是哪种模式。

---

## 📂 输出文件

数据获取完成后，文件会保存在你指定的目录：

```
你指定的输出目录/
├── downloads/
│   └── 灯塔导出数据_20240315_143022.csv    # 下载的原始数据
└── beacon_data_20240315_143022.csv          # 整理后的数据（如有）
```

> ⚠️ **注意**：灯塔导出的 CSV 使用 `UTF-8 with BOM` 编码，用 Python 读取时请使用 `encoding='utf-8-sig'`

---

## ❓ 常见问题

### Q: 为什么页面加载很慢？
A: 灯塔页面打开后会自动执行查询，首次加载通常需要 20-40 秒，这是正常的。

### Q: 数据量很大时怎么办？
A: 推荐使用**下载导出模式**（默认），它会通过灯塔的"下载管理"功能导出完整数据，不受 5000 行限制。

### Q: 二维码扫不出来？
A: 确保使用 **iOA Mobile 3.2 或更高版本**。如果 App 版本较旧，可能无法识别二维码。

### Q: 可以用 Cookie 登录吗？
A: 可以！如果你已经在浏览器登录了灯塔，可以告诉 AI：
```
用这个 Cookie 登录灯塔：<你的 Cookie 字符串>
```
获取 Cookie 方法：浏览器 F12 → Network → 刷新 → 任意请求的 Request Headers → Cookie

---

## 🔧 进阶用法

### 指定输出目录

```
帮我把灯塔数据下载到 /data/workspace/yyb_project/2024年/灯塔数据/
链接：https://beacon.woa.com/...
```

### 指定时间范围

```
获取过去 90 天的灯塔数据：
https://beacon.woa.com/...
```

### 仅抓取页面数据（不下载文件）

```
抓取这个灯塔页面的 API 数据（不要下载文件）：
https://beacon.woa.com/...
```

---

## 📁 Skill 文件结构

```
beacon-data-fetcher/
├── README.md                    # 👈 你正在看的使用指南
├── SKILL.md                     # Skill 技术文档（AI 读取）
├── runtime/                     # 运行时数据（自动生成）
│   ├── beacon_auth_state.json   # 保存的登录态
│   ├── qr_code.png              # 登录二维码
│   └── .scan_status             # 状态标记
├── scripts/                     # 自动化脚本
│   ├── beacon_qr_server.py      # 扫码登录服务
│   ├── beacon_login.py          # Cookie 登录
│   ├── beacon_page_scrape.py    # 页面抓取
│   └── beacon_download_export.py # 下载导出
└── references/                  # 参考文档
    └── beacon_ui_elements.md    # UI 元素定位参考
```

---

## 🤝 贡献与反馈

遇到问题或有改进建议？欢迎联系 Skill 作者或提交 Issue！

---

## 📝 更新日志

| 版本 | 日期 | 更新内容 |
|-----|------|---------|
| v1.0 | 2024-03 | 初始版本，支持页面抓取和下载导出两种模式 |

---

> 💡 **小贴士**：这个 Skill 的核心优势是**自动化**——你只需要提供灯塔链接，AI 会自动完成登录、修改时间、触发下载、等待完成、保存文件的全部流程！
