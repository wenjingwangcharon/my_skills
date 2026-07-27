# Beacon DataTalk SQL 自动化操作路径

## 环境要求

- Python 3.9+，Playwright（`pip install playwright && playwright install chromium`）
- 内网环境，能访问 `https://beacon.woa.com`
- 目标数据源权限：`Xingpan_StarRocks_ima(新)`

## 认证流程

### 首次 / 过期时：QR 扫码登录

认证状态文件由本 skill 自带的 `scripts/beacon_qr_server.py` 生成，**不需要额外安装 beacon-data-fetcher skill**。

```bash
python3 scripts/beacon_qr_server.py \
  --start \
  --auth beacon_auth_state.json \
  --url "https://beacon.woa.com/datatalk/ima/card?mode=sql" \
  --port 18888
```

浏览器打开 `http://localhost:18888`，用 iOA 手机 App 扫码确认。成功后 `beacon_auth_state.json` 即生成。

### 运行时：自动发现认证文件

`beacon_sql_runner.py` 按以下优先级查找认证文件：
1. 环境变量 `BEACON_AUTH_STATE`
2. `<cwd>/beacon_auth_state.json`
3. `~/.workbuddy/skills/beacon-data-fetcher/runtime/beacon_auth_state.json`
4. `<cwd>/beacon-data-fetcher/runtime/beacon_auth_state.json`

### 过期检测

如果脚本报 `iOA Mobile` 二次认证页面，说明 auth state 已过期，需重新扫码。

## 完整操作路径（已验证可跑通）

### 1. 启动浏览器 & 认证

```python
browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
context = await browser.new_context(storage_state="beacon_auth_state.json")
page = await context.new_page()
```

### 2. 导航到 SQL 页面

```python
await page.goto("https://beacon.woa.com/datatalk/ima/card?mode=sql", wait_until="domcontentloaded")
await page.wait_for_timeout(40000)  # SPA 加载 SQL 编辑器需要 ~30s+
```

### 3. 关闭引导弹窗

- 弹窗文案: "DataTalk——人人可用数据图表对话"
- 关闭按钮: class 含 `close`, `cancel`, `modal-close`; 或文本为 `关闭`/`关 闭`/`知道了` 的 button
- 关闭后截图确认
- **`engine-tpl-overlay` 浮层**（编辑器上方"StarRocks请过来问我"）必须隐藏，否则 Monaco 区域被挡住

### 4. 选择数据源

**两步选择**：

第一步 — 选数据库类型：
- 点击 `.category-prefix-trigger`
- 从下拉菜单选 `StarRocks`

第二步 — 选具体数据连接：
- 点击 `.source-select`（placeholder 为"请输入数据连接名称进行搜索"的 ant-select）
- 输入 "Ima" 搜索
- JS evaluate 遍历 `.ant-select-item-option`，匹配 "Xingpan" + "Ima" 的选项并 click

注意：有两个不同的输入框——
- "请输入数据连接名称进行搜索" → 选 StarRocks 连接
- "请输入表名称进行搜索" → 选具体表（先选连接，再选表）

### 5. 注入 SQL 到 Monaco 编辑器

Monaco 使用虚拟滚动，只有当前可见行在 textarea 中。**唯一可靠的方式**是 dispatch `ClipboardEvent('paste')`：

```javascript
const ta = document.querySelector('.monaco-editor textarea.inputarea');
ta.focus();
const dt = new DataTransfer();
dt.setData('text/plain', sql);
ta.dispatchEvent(new ClipboardEvent('paste', {clipboardData: dt, bubbles: true}));
```

**禁止的方式**（都会被虚拟滚动截断）：
- `keyboard.type()` — 字符丢失
- `editor.setValue()` — 需用 Monaco API 实例，不稳定
- `clipboard.writeText()` + `Ctrl+V` — 浏览器剪贴板权限问题

### 6. 执行查询

- 查询按钮文本: **"查 询"**（中间有空格！匹配时需精确处理）
- 点击方式：JS evaluate 遍历所有 button，`textContent.replace(/\s+/g, '') === '查询'`
- 点击后等待轮询结果状态

### 7. 轮询等待结果

```javascript
// 轮询逻辑 — 只看 table tbody tr 行数（不要数 error class！）
const tables = document.querySelectorAll('table');
let dataRows = 0;
for (const t of tables) {
    dataRows += t.querySelectorAll('tbody tr').length;
}
// 失败检测
const hasFail = document.body.innerText.includes('查询失败');
```

**轮询间隔 3s，最长 120s**。

### 8. 提取数据 & 存 Excel

- 找到行数最大的 `table`
- 提取 `thead th` → headers，`tbody tr td` → rows
- 用 openpyxl 写入 Excel

## 关键陷阱（踩过的坑）

| 陷阱 | 原因 | 解决方案 |
|------|------|----------|
| `networkidle` 永久超时 | DataTalk 有 WebSocket 长连接 | 用 `domcontentloaded` + 固定等待 |
| Modal 没关就操作 | 遮罩挡住页面元素 | 先关弹窗再操作 |
| SQL 注入不完整 | Monaco 虚拟滚动只显示当前可见行 | 必须用 `ClipboardEvent('paste')` dispatch |
| 数据源选不到 | 混淆了"表名搜索"和"数据连接名称搜索"两个 input | 先 `.category-prefix-trigger` 选类型，再 `.source-select` 选连接 |
| 查询按钮找不到 | 文字是"查 询"（含空格） | 匹配时 `replace(/\s+/g, '')` 去空格 |
| 误报查询失败 | `querySelectorAll('[class*="error"]')` 误命中无关 DOM 元素 | 只看 `table tbody tr` 行数 + `bodyText.includes('查询失败')` |
| auth state 过期 | 跳转 iOA 二次认证页 | 重新 QR 扫码 |
| CTE (WITH 子句) 报错 | — | CTE 在 DataTalk SQL 模式下**可以正常执行**，不是问题 |
