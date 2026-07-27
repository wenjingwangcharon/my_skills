---
name: beacon-data-fetcher
description: 灯塔(Beacon) DataInsight 数据获取技能。自动化从腾讯灯塔平台获取数据，支持页面抓取模式和下载管理导出模式，支持TV模式和敏捷分析模式两种页面类型，可自动检测页面类型并选择对应的时间修改方式。当用户提到"灯塔数据"、"beacon数据"、"拉取灯塔"、"灯塔取数"、"灯塔导出"时触发此技能。
---

# 灯塔(Beacon) DataInsight 数据获取

从腾讯灯塔(Beacon) DataInsight 平台自动化获取数据。灯塔是腾讯内部数据分析平台，需要 OA 认证登录，页面默认只展示 5000 行数据。

## 三维能力矩阵

本 skill 支持三个维度的灵活组合：

### 维度一：数据获取模式

| 模式 | 脚本 | 说明 |
|------|------|------|
| **页面抓取** | `beacon_page_scrape.py` | 通过拦截 API 响应获取数据，适合数据量较小或需要解析图表数据的场景 |
| **下载导出** (推荐) | `beacon_download_export.py` | 通过点击下载按钮获取原始 CSV 文件，不论数据量大小都可用，节省 token |

**推荐策略**: 优先使用下载导出模式获取原始数据文件，更稳定且不受 5000 行限制。

### 维度二：页面展示类型

| 类型 | URL 特征 | 说明 |
|------|----------|------|
| **TV 模式** | `/PanelMax/` | 面板看板页面，通过"探索分析"修改时间 |
| **敏捷分析模式** | `/Analytics_Mode/` | 灵活分析页面，通过"时间设置"修改时间 |
| **事件分析** | `/New_Event_Modify/` | 事件分析页面，使用 TV 模式的时间修改方式 |

脚本支持**自动检测**页面类型（`--page-type auto`），也可手动指定。

### 维度三：时间修改方式

| 页面类型 | 时间修改入口 | 操作流程 |
|----------|------------|---------|
| **TV 模式** | 点击"探索分析" | 展开面板 → 修改天数输入框(默认30) → 点击"确定" |
| **敏捷分析模式** | 页面顶部"时间设置"区域 | 修改天数输入框(如120) → 点击"立即分析" |

### 交叉组合示例

| 场景 | 数据模式 | 页面类型 | 时间修改 |
|------|---------|---------|---------|
| TV看板下载180天数据 | 下载导出 | TV | 探索分析→180天→确定 |
| 敏捷分析获取120天API数据 | 页面抓取 | 敏捷分析 | 时间设置→120天→立即分析 |
| TV看板直接抓取默认数据 | 页面抓取 | TV | 不修改 |
| 敏捷分析下载完整数据 | 下载导出 | 敏捷分析 | 时间设置→天数→立即分析 |

## 前置条件

- **Python 3.8+**（`python3` 或 `python` 命令可用，脚本通过 `sys.executable` 自动定位解释器）
- **Playwright** 已安装 (`pip install playwright && playwright install chromium`)
- **跨平台**: 支持 Linux/macOS/Windows，自动适配进程管理、信号处理、编码（Windows GBK fallback）
- **认证方式** (二选一):
  - Cookie 注入: 需要用户从浏览器中复制灯塔的 Cookie 字符串
  - 扫码登录: 用户通过 iOA Mobile 3.2+ 扫描二维码登录（通过 HTTP 预览窗口展示二维码）

## 核心流程（每次数据获取任务必须遵循）

### Step 1: 启动登录服务 + 打开预览

**每次数据获取任务，第一步必须运行此命令**（不论登录态是否有效）：

```bash
python3 {SKILL_DIR}/scripts/beacon_qr_server.py --start \
  --auth "{SKILL_DIR}/runtime/beacon_auth_state.json" \
  --url "<灯塔页面URL>" \
  --port 18888
```

脚本会：
1. 清理旧的 HTTP 服务和浏览器进程
2. 启动 HTTP 服务子进程（后台运行）
3. 输出 `HTTP_READY` 信号后快速退出

**⚡ 关键：看到 `HTTP_READY` 后，必须立即调用 `preview_url` 打开 `http://localhost:18888`，不需要等待二维码就绪或任何其他状态。** 页面内置了 2 秒轮询机制，会自动从"检查中"更新到"显示二维码"或"登录有效"，用户无需等待。

**❌ 错误做法**：先轮询 `.scan_status` 等待 `need_scan` 再打开预览 —— 这会浪费 10-15 秒。
**✅ 正确做法**：`HTTP_READY` → 立即 `preview_url` → 然后再轮询状态等待登录结果。

预览页面会自动显示当前状态：
- **"正在检查登录态..."** → 后台正在用 Playwright 检测登录状态
- **"登录态有效，爬取任务即将开始..."** → 认证正常，可以运行主爬取脚本
- **显示二维码** → 登录态失效，等待用户用 iOA Mobile 扫码
- **"登录成功！"** → 扫码完成，可以运行主爬取脚本

> **iOA 快捷登录兼容**: 如果用户本地安装了 iOA，灯塔登录页可能显示"快速登录"模式（含用户头像和快速登录按钮）而非直接展示二维码。脚本会自动检测此情况，点击"账号密码"切换到扫码登录页面后再截取二维码，无需人工干预。

### Step 2: 运行主爬取脚本

**不需要等待 Step 1 的 HTTP 页面显示完成结果**，可以直接运行主爬取脚本。脚本内部会自动轮询信号文件等待登录完成：

#### 下载导出模式 (推荐)

```bash
# 直接下载 (页面默认时间范围)
python3 {SKILL_DIR}/scripts/beacon_download_export.py \
  --auth "{SKILL_DIR}/runtime/beacon_auth_state.json" \
  --url "<灯塔页面URL>" \
  --output-dir "<输出目录>" \
  --trigger-export

# TV模式：修改天数后下载
python3 {SKILL_DIR}/scripts/beacon_download_export.py \
  --auth "{SKILL_DIR}/runtime/beacon_auth_state.json" \
  --url "https://beacon.woa.com/datainsight/.../PanelMax/..." \
  --output-dir "<输出目录>" \
  --days 180 \
  --trigger-export \
  --wait-query 120

# 敏捷分析模式：修改天数后下载
python3 {SKILL_DIR}/scripts/beacon_download_export.py \
  --auth "{SKILL_DIR}/runtime/beacon_auth_state.json" \
  --url "https://beacon.woa.com/datainsight/.../Analytics_Mode/..." \
  --output-dir "<输出目录>" \
  --days 120 \
  --trigger-export \
  --wait-query 120

# 仅下载已有任务 (不触发新导出)
python3 {SKILL_DIR}/scripts/beacon_download_export.py \
  --auth "{SKILL_DIR}/runtime/beacon_auth_state.json" \
  --url "<灯塔页面URL>" \
  --output-dir "<输出目录>"
```

#### 页面抓取模式

```bash
# 直接抓取页面默认数据
python3 {SKILL_DIR}/scripts/beacon_page_scrape.py \
  --auth "{SKILL_DIR}/runtime/beacon_auth_state.json" \
  --url "<灯塔页面URL>" \
  --output-dir "<输出目录>" \
  --wait 15

# TV模式修改天数
python3 {SKILL_DIR}/scripts/beacon_page_scrape.py \
  --auth "{SKILL_DIR}/runtime/beacon_auth_state.json" \
  --url "https://beacon.woa.com/datainsight/.../PanelMax/..." \
  --output-dir "<输出目录>" \
  --days 180 \
  --poll-timeout 300

# 敏捷分析模式修改天数
python3 {SKILL_DIR}/scripts/beacon_page_scrape.py \
  --auth "{SKILL_DIR}/runtime/beacon_auth_state.json" \
  --url "https://beacon.woa.com/datainsight/.../Analytics_Mode/..." \
  --output-dir "<输出目录>" \
  --days 120 \
  --poll-timeout 300
```

### Step 3: 数据整理

下载完成后，对 CSV 数据进行基本整理:
- 灯塔导出的 CSV 使用 **UTF-8 with BOM** 编码，读取时用 `encoding='utf-8-sig'`
- 字段名可能包含中文括号和长描述，建议保持原始字段名
- 使用 `csv.DictReader` 读取，按需生成数据概览报告

## Cookie 注入登录（可选替代方式）

如果用户已有灯塔 Cookie，可直接注入而不走扫码流程：

```bash
python3 {SKILL_DIR}/scripts/beacon_login.py \
  --cookie "<用户提供的Cookie字符串>" \
  --output "{SKILL_DIR}/runtime/beacon_auth_state.json"
```

获取 Cookie 方法：
1. 在本地浏览器打开 `https://beacon.woa.com` 并完成 OA 登录
2. F12 → Network → 刷新页面 → 点击任意请求
3. 在 Request Headers 中找到 `Cookie:` 行，复制完整值

使用 Cookie 注入后，可跳过 Step 1 直接运行 Step 2 的主爬取脚本。

## 关键注意事项

1. **idle timeout 防护**: 所有等待环节必须有定期 stdout 输出（每 5 秒一次），否则执行环境可能因 idle timeout 杀掉进程
2. **干扰弹窗处理**: 点击导出按钮后可能弹出"保存到分析列表"对话框，需要先关闭再继续操作
3. **登录态自动恢复**: 主爬取脚本如果检测到登录态失效，会自动轮询 `{SKILL_DIR}/runtime/.scan_status` 信号文件等待登录恢复，登录成功后自动重新加载认证状态继续爬取，无需人工介入
4. **HTTP 服务始终先启动**: 每次数据获取任务的第一步总是运行 `beacon_qr_server.py --start` + 调用 `preview_url`，不需要根据登录态判断是否启动，这确保了流程的一致性和可靠性
5. **页面加载时间**: 灯塔页面自动执行查询，首次加载可能需要 20-40 秒
6. **`{SKILL_DIR}` 占位符**: 在实际使用时，将 `{SKILL_DIR}` 替换为此 skill 的实际安装路径
7. **页面类型自动检测**: 默认 `--page-type auto`，通过 URL 中的 `PanelMax` / `Analytics_Mode` 关键词判断
8. **大文件下载管理不自动刷新**: 灯塔的下载管理列表不会自动刷新，脚本会自动循环刷新（关闭弹窗→重新展开侧边栏→重新打开下载管理）
9. **天数输入使用键盘方式**: 天数修改统一使用三击全选+退格+键入方式，而非 `nativeSetter`。灯塔基于 Vue/Element UI 的输入框在已有非默认值（如 120）时，`nativeSetter` 可能无法正确触发框架的响应式更新，导致提交的仍是旧值

## 通信机制

### HTTP 服务和浏览器之间（同进程）

`beacon_qr_server.py --serve` 模式下，HTTP 服务和 Playwright 检测线程运行在同一进程中，通过 Python 类变量 `StatusManager` 直接共享状态。简单可靠，无跨进程同步问题。

### HTTP 服务和主爬取脚本之间（跨进程）

通过文件信号 `{SKILL_DIR}/runtime/.scan_status` 通信：
- `beacon_qr_server.py` 的检测线程在状态变化时写入此文件
- `beacon_page_scrape.py` / `beacon_download_export.py` 轮询读取此文件

信号文件值含义：
| 值 | 含义 |
|----|------|
| `checking` | 正在检查登录态 |
| `auth_ok` | 登录态有效，可直接爬取 |
| `need_scan` | 需要扫码 |
| `success` | 扫码成功，登录完成 |
| `failed` | 扫码失败/超时 |

## 文件结构

```
beacon-data-fetcher/
├── SKILL.md                           # 本文件 — skill 说明文档
├── runtime/                           # 运行时数据目录（动态生成，不含代码）
│   ├── .gitkeep                       # 保持目录存在
│   ├── beacon_auth_state.json         # (动态) 认证状态文件
│   ├── qr_code.png                    # (动态) 二维码截图
│   ├── .scan_status                   # (动态) 状态标记文件
│   └── serve.log                      # (动态) HTTP 服务日志
├── scripts/
│   ├── beacon_qr_server.py            # 扫码登录服务：--start 启动 HTTP 子进程 / --serve HTTP五态页面+后台登录检测
│   ├── beacon_login.py                # Cookie 注入登录 + 公共函数 (is_login_page/parse_cookie_string)
│   ├── beacon_page_scrape.py          # 页面抓取模式：API拦截+DOM解析+ECharts提取
│   └── beacon_download_export.py      # 下载导出模式：触发导出+下载管理+文件下载
└── references/
    └── beacon_ui_elements.md          # 灯塔 UI 元素定位参考 (含TV模式和敏捷分析模式)
```

## 下载导出模式详细说明

**关键参数**:
- `--days, -d`: 目标天数。不指定或为 0 则使用页面默认天数
- `--page-type`: 页面类型 `auto`/`tv`/`analytics`，默认 `auto` 根据 URL 自动判断
- `--trigger-export`: 是否点击下载按钮触发新导出任务
- `--wait-query`: 修改天数后等待查询完成秒数 (默认: 120)
- `--wait-download`: 文件下载等待秒数 (默认: 120)

**工作原理** (参照 `references/beacon_ui_elements.md` 了解 UI 元素细节):
1. 打开灯塔页面，等待数据加载完成
2. (可选) 根据页面类型修改查询天数并等待查询完成
3. (可选) 找到 `download.png` 图标并点击触发导出
4. **智能判断下载方式** (最多10秒):
   - **小文件模式**: 浏览器直接触发 download 事件（< 5000行，通常1-3秒）
   - **大文件模式**: 检测页面顶部蓝色提示条（"已发起下载任务"等），通常1秒即可判定
5. (仅大文件) 展开右侧快捷工具侧边栏 → 点击"下载管理"
6. (仅大文件) **循环刷新下载管理** (每8秒):
   - 检查最新任务状态：如果是"计算中"则等待刷新
   - 如果任务"完成"则点击下载按钮
   - 关闭弹窗 → **重新展开侧边栏** → 重新打开下载管理
7. 通过 Playwright download 事件拦截并保存文件

**输出**: 下载的 CSV 文件保存在 `<output-dir>/downloads/` 目录，并自动整理为 `灯塔导出数据_<timestamp>.csv`

## 页面抓取模式详细说明

**关键参数**:
- `--days, -d`: 目标天数，不指定或为 0 则使用页面默认天数
- `--page-type`: 页面类型 `auto`/`tv`/`analytics`，默认 `auto` 根据 URL 自动判断
- `--poll-timeout`: 修改天数后等待查询结果的超时秒数（默认 300）
- `--no-step-screenshots`: 关闭逐步截图
- `--wait, -w`: 建议设为 12 以上，确保默认数据加载完成

**修改天数流程 (TV 模式)**:
1. 点击"探索分析"按钮展开左侧设置面板
2. 找到天数输入框（默认值 30），修改为目标天数
3. 点击"确定"按钮触发重新查询
4. 轮询 API 响应等待 `query_state=SUCCESS`

**修改天数流程 (敏捷分析模式)**:
1. 找到页面顶部"时间设置"区域的天数输入框
2. 修改为目标天数
3. 点击"立即分析"按钮触发查询
4. 轮询 API 响应等待数据就绪

**输出**: `beacon_data_<timestamp>.csv`, `api_responses_<timestamp>.json`
