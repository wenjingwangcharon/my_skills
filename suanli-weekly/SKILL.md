---
name: suanli-weekly
description: |
  Weekly compute-power（算力）workflows: (A) 算力底表 processing + pie charts,
  (B) 算力券周报 — 仪表盘 API 拉券数 + SQL 算人数 → 格式化 xlsx,
  (C) 活动算力周报 SQL（活动发放/消耗/过期算力 + 人数 + 累计付费用户）。
  This skill should be used when the user asks to process a 算力底表 Excel file,
  mentions "算力饼图", "每周算力", "算力分析", "算力底表处理",
  or when the user mentions "算力券周报", "算力券每周", "算力券SQL", "算力券xlsx",
  "coupon weekly report", "coupon 周报",
  or when the user mentions "活动算力", "活动算力周报", "活动算力SQL", "copilot算力",
  "copilot活动报表", "copilot point report", "算力活动周报".
  Also trigger on: "跑一下这周的算力券", "算力券底表", "活动算力数据".
agent_created: true
---

# 算力周处理 — 三个子任务

## 整体工作流

三个 Task 的依赖关系：

```
Task B（算力券周报） — 仪表盘 API 拉数 → SQL 计算人数 → generate_coupon_weekly_from_xlsx.py
Task C（活动算力周报） → SQL → activity_report.xlsx → 作为 Task A 的输入
Task A（算力底表 & 饼图） — 输入 = Task C 的产出 xlsx
```

**全量周报执行顺序**：先并行跑 B + C，B 的仪表盘拉数可以和 C 的 SQL 同时跑；C 完成后自动衔接到 A，A 完成后输出 Insights。

---

## Beacon 自动执行（共用基础设施）

两个 SQL Task（B 和 C）都通过 `scripts/beacon_sql_runner.py` 自动在 Beacon DataTalk 上执行。

完整操作路径、选择器、陷阱详见 `references/beacon_automation.md`。

### ⚠️ 第零步：先登录（每次必做）

**在任何操作之前（无论是仪表盘 API 还是 SQL），必须先确保 Beacon 认证有效。**

1. 检查 `beacon_auth_state.json` 是否存在于以下任一位置：
   - 环境变量 `BEACON_AUTH_STATE` 指向的路径
   - `<skill_dir>/beacon_auth_state.json`
   - `~/.workbuddy/skills/beacon-data-fetcher/runtime/beacon_auth_state.json`
   - `<cwd>/beacon_auth_state.json`
2. 如果文件不存在，**立即启动 QR 登录**：
   ```
   python3 scripts/beacon_qr_server.py --start \
     --auth <skill_dir>/beacon_auth_state.json \
     --url "https://beacon.woa.com/datatalk/ima/card?mode=sql" \
     --port 18888
   ```
   然后用 `present_files` 打开 `http://localhost:18888`，等待用户扫码。确认 `.scan_status` 变为 `scanned` 后再继续。
3. 如果文件存在，**仍建议先跑一次快速验证**：启动浏览器用 `storage_state` 加载 auth → 导航到 Beacon → 截图检查是否出现 iOA 二次认证页面。如果过期，走步骤 2 重新扫码。
4. 认证就绪后，用 `export BEACON_AUTH_STATE=<auth_file_path>` 设置环境变量，然后进入 Task B/C 执行。

### 前置条件

1. **Python 环境**：Playwright 已安装（`pip install playwright && playwright install chromium`）
2. **认证**：已完成第零步，`beacon_auth_state.json` 有效。
3. **仪表盘 API 脚本**（Task B 的 sniff/fetch/coupon_api_to_xlsx）和 **beacon_sql_runner.py**（Task C + Task B 的 SQL 人数）共享同一套 auth。

### SQL 执行命令（Task C / Task B 人数 SQL）

```
BEACON_AUTH_STATE=<auth_file_path> python3 scripts/beacon_sql_runner.py <sql_file_path>
```

可选环境变量：
- `BEACON_AUTH_STATE` — 指定认证文件路径（必传，第零步确定）
- `BEACON_OUTPUT_DIR` — 指定输出目录（默认 `<cwd>/beacon_output`）

脚本自动完成：认证恢复 → 页面加载 → 关弹窗 → 选数据源 → 注入 SQL → 执行 → 抓结果 → 存 Excel。

---

## Task A — 算力底表处理 & 饼图

Trigger: "处理算力底表", "画算力饼图", "算力底表", etc.

### Workflow

1. **输入来源**：Task C 的产出 xlsx（`beacon_output/copilot_point_report_*_result.xlsx`），不需要用户手动提供。
   - 如果 Task C 刚跑完，直接用其结果。
   - 如果单独触发了 Task A 但没有现成的 Task C 输出，先跑 Task C 再跑 Task A。
2. Run `scripts/process.py <task_c_output.xlsx> <output.xlsx>`（默认输出 `<workspace>/算力底表_已处理.xlsx`）。
3. Generate 3 **纯 SVG 饼图**（禁止用 Chart.js CDN——CDN 异步加载导致 canvas 留白已确认不可靠）via `show_widget`:
   - 本周下发算力
   - 本周会话消耗算力
   - 本周过期消耗算力
4. **渲染方式**：纯 SVG `<svg viewBox="0 0 680 H">` 内联，计算 doughnut 路径用 `M...A...L...A...Z`。不依赖任何外部 CDN 资源。
5. Colors: `#4472C4` / `#ED7D31` / `#A5A5A5` / then extend (`#5B9BD5` / `#70AD47` / `#FFC000`). "其他" always gray.
6. Values in 万, labels: `1,983.13万(37.85%)`.
7. Call `present_files` with the cleaned xlsx + Task C 底表 + Task B 格式化 xlsx。
8. **在同一条回复中输出本周 Insights**（见下方「周报 Insights」节），不需要用户额外要求。

### 饼图布局规范（已踩过 viewBox 切字坑 + 重复调用坑 — 严格遵守）

**`viewBox` 固定 `0 0 680 380`**（Visualizer 工具硬约束 680 宽，高度 380 留足底部安全边）。

**饼图位置**（缩小一圈，给图例让出空间）：
- center `cx=160 cy=200`，外径 `R=95`，内径 `r=50`
- 饼图底边 y=295，viewBox 高 380 → 留 **85px 底部安全边**，绝不被卡片切
- **不要**用 cx=190 R=145（旧版底部被切）
- **不要**用 cx=160 cy=230 R=120（旧版 viewBox=440 整图过小显示也被切过）

**图例位置**（右侧起点 `x=335`，第一行 y=100 避开饼图顶）：
- 颜色块 `rect` at `x=335 y=100, 13×13, rx=2`
- 活动名 `text` at `x=356`（21px 间距）, `font-size=13`, left-aligned
- 数值 `text` at `x=665`, `text-anchor="end"`, `font-weight=500`, `font-size=13`
- **行高 = 35px**（13px 字体 + 22px 间距）
- 最长图例文本（如"下载双端领算力 116.41万(1.35%)"）从 x=356 到 x=665 约 309px 空间，13px 字号下完全装得下
- 最后一行的 `y` 不得超过 360（=380-20）
- "其他" 行用灰字 `fill=#999`
- **不要在饼图扇区内放数字标注**——所有数字统一在右侧图例

**调用规则（防重复出 6 张）**：
- 3 张饼图用**单条消息连续 3 次 `show_widget` 并行调用**（一次发出），不要分开发
- 中途发现尺寸不对要重画：先把当前消息里已经画的全部重画，不要追加 3 张，否则 UI 会堆成 6 张

---

## Task B — 算力券周报

Trigger: "算力券周报", "算力券每周", "跑算力券", "coupon周报", etc.

**统一路径**：仪表盘 API 拉券数 + SQL 算人数 → 生成格式化 xlsx。

### Step 1 — Determine date range

The report covers **last Friday 00:00 to this Thursday 24:00**. Calculate from current date:

```python
from datetime import date, timedelta
today = date.today()
thursday = today + timedelta(days=(3 - today.weekday()))
friday = thursday - timedelta(days=6)
start_str = friday.strftime('%Y%m%d')
end_str = thursday.strftime('%Y%m%d')
```

If the user provides an explicit date range, use that instead.

### Step 2 — 仪表盘 API 拉券数（券张数 + 每日分桶）

Step 2a — 抓/更新 API 请求体（首次 or 超过 7 天未更新）：

目标卡片 `line_0hj7sgin` / `table_xaw0lw80` / `table_ueub7onq` 在 menu layout y=74/93/112，位于 dashboard canvas **内部滚动容器** `.lite-publish-canvas-scroll` 的最下方。

```bash
python3 scripts/sniff_dashboard_cards.py
```

输出：`<cwd>/beacon_output/target_card_posts.json`。如果已有且未过期（< 7 天 old），可跳过此步。

Step 2b — 拉 49 天原始数据：

```bash
python3 scripts/fetch_coupon_dashboard.py
```

从 `target_card_posts.json` 读请求体 → 改 `queryDate` 为 `relative_time` + `dateRange=49` → 请求 3 个 API → 保存到 `missing_weeks_complete.json`。

Step 2c — API 响应转 xlsx：

```bash
python3 scripts/coupon_api_to_xlsx.py
```

产出 3 张 xlsx：
- `charoniwang_copilot算力报表_算力券发放-分发放类型_49d.xlsx`
- `charoniwang_copilot算力报表_算力券发放-运营知识库激励_49d.xlsx`
- `charoniwang_copilot算力报表_算力券发放-运营skill激励_49d.xlsx`

### Step 3 — SQL 计算整周唯一人数

仪表盘 API 给的人数 = 每日去重，跨天求和会重复计数同一用户。**总计行的运营知识库人数、运营skill人数、总计人数必须用 SQL `COUNT(DISTINCT uid)` 计算**。

SQL 模板（`scripts/weekly_people.sql`），替换 `{START}` 和 `{END}` 后执行：

```sql
WITH weekly_uid AS (
  SELECT COUNT(DISTINCT uid) AS total_uid
  FROM dwd_ima_activity_coupon_uid_aggr_di
  WHERE imp_date >= {START} AND imp_date <= {END}
    AND coupon_cnt > 0
),
user_weekly AS (
  SELECT
    uid,
    SUM(coupon_cnt_management) AS wk_mgmt,
    SUM(coupon_cnt_skill) AS wk_skill
  FROM dwd_ima_activity_coupon_uid_aggr_di
  WHERE imp_date >= {START} AND imp_date <= {END}
  GROUP BY uid
)
SELECT
  COUNT(DISTINCT CASE WHEN u.wk_mgmt > 0 THEN u.uid END) AS kb_people,
  COUNT(DISTINCT CASE WHEN u.wk_skill > 0 THEN u.uid END) AS sk_people,
  MAX(w.total_uid) AS total_people
FROM user_weekly u
CROSS JOIN weekly_uid w
```

执行方式：复用 `scripts/beacon_sql_runner.py`，或手动在 Beacon SQL 页面跑。拿到的 3 个数字（kb_people / sk_people / total_people）传给 Step 4 的 `--sql-people`。

**CRITICAL**: `imp_date` is INTEGER yyyyMMdd — no quotes, no hyphens. SQL 文件无注释。

除此之外，**每日总计人数**（G 列）也需要通过 SQL 计算——仪表盘 API 给的每日人数是 `max(三类人数)`，不是真正的 `COUNT(DISTINCT uid)`：

```sql
SELECT imp_date, COUNT(DISTINCT uid) AS daily_people
FROM dwd_ima_activity_coupon_uid_aggr_di
WHERE imp_date >= {START} AND imp_date <= {END} AND coupon_cnt > 0
GROUP BY imp_date ORDER BY imp_date
```

结果格式：`date=N,date=N,...`，传给 Step 4 的 `--daily-people`。

### Step 4 — 生成格式化周报

```bash
python3 scripts/generate_coupon_weekly_from_xlsx.py \
  --weeks "20260717-20260723" \
  --sql-people "kb=1161,skill=405,total=3010" \
  --daily-people "20260717=1034,20260718=970,..."
```

参数：
- `--weeks`：逗号分隔的周范围
- `--sql-people`：**必传**，SQL 计算的整周唯一人数（格式 `kb=N,skill=M,total=P`）。多周用竖线分隔：`"20260717:kb=100,skill=50|20260724:kb=120,skill=60"`
- `--daily-people`：SQL 计算的每日唯一人数（格式 `date=N,date=N,...`），替换每日 G 列
- `--input-dir` / `--output-dir`：xlsx 目录（默认 `<cwd>/beacon_output/`）

产出：`<out_dir>/ima_算力券周报_<START>_<END>.xlsx`。

**人数逻辑**：
- **每日行 D/F 列**（运营知识库人数/运营skill人数）：仪表盘 API 每日去重值不变
- **每日行 G 列**（总计人数）：用 SQL `COUNT(DISTINCT uid)` 每日值替换，不再用 `max(三类人数)`
- **总计行 D/F/G 列**：用 SQL 的整周唯一人数替换
- `--sql-people` 为必传参数，不再支持 fallback；`--daily-people` 也建议传入

格式：20-column single-row header，蓝白配色（#4472C4 / #2F5496 / #D6E4F0），总计行 + 日均行，冻结首行。

### API 格式关键坑

| 坑 | 错误做法 | 正确做法 |
|---|---|---|
| `queryDate.dateFormat` | `absolute_time` → "系统错误" | `relative_time` + `dateRange=49` |
| `queryDate.dateFormat` | `natural_time` → 返回 0 行 | 同上 |
| `line_0hj7sgin` 时间字段名 | `imp_date` | `ds` |
| `line_0hj7sgin` dataset type | `VIRTUAL` | `DOMAIN`, ids: `["ima_a4e"]` |
| dimList/indexList 构造 | 手工拼 JSON, fieldKey=null | 从真实请求体 clone |
| 页面加载 | `networkidle` → 永不触发 | `domcontentloaded` + 固定 wait |
| 卡片不在可视区 | `window.scrollTo` | `.lite-publish-canvas-scroll` 的 `scrollTop = scrollHeight` |

### Step 5 — Present result

Call `present_files` with the formatted xlsx. 输出校验结果：每日行 ∑分项 = 总计券数 OK，SQL 人数来源已确认。

---

## Task C — 活动算力周报（SQL）

Trigger: "活动算力", "活动算力周报", "活动算力SQL", "copilot活动报表", "copilot point report", "活动算力数据", "算力活动周报", etc.

Load `references/activity_point_report.md` for the full SQL template, field mappings, and conventions.

### Step 1 — Determine date range

Same rule as Task B: **last Friday 00:00 to this Thursday 24:00**. Calculate from current date:

```python
from datetime import date, timedelta
today = date.today()
thursday = today + timedelta(days=(3 - today.weekday()))
friday = thursday - timedelta(days=6)
prev_friday = friday - timedelta(days=7)
prev_thursday = thursday - timedelta(days=7)
week_start = friday.strftime('%Y%m%d')
week_end = thursday.strftime('%Y%m%d')
cum_end = week_end
prev_start = prev_friday.strftime('%Y%m%d')
prev_end = prev_thursday.strftime('%Y%m%d')
```

If the user provides an explicit date range, use that instead.

### Step 2 — Write SQL

Replace `{week_start}` `{week_end}` `{cum_end}` `{prev_start}` `{prev_end}` in the template from `references/activity_point_report.md`, then write the SQL file.

Save SQL to `<workspace>/copilot_point_report_{week_start}_{week_end}.sql`. Do NOT include comments in the SQL file.

### Step 3 — Auto-execute SQL on Beacon & chain to Task A

Run via `scripts/beacon_sql_runner.py`:

```
python3 scripts/beacon_sql_runner.py <sql_file_path>
```

This auto-executes the SQL on Beacon DataTalk and saves the result to `<cwd>/beacon_output/<sql_basename>_result.xlsx`.

**该 xlsx 本身也是交付物**，在 `present_files` 中一并展示。

**完成后自动衔接到 Task A**：该 xlsx 即为 Task A 的输入，直接跑 `scripts/process.py` + 生成 3 张饼图。不需要用户手动下载和提供文件。

### Key rules

- `imp_date` is INTEGER, format yyyyMMdd — no quotes, no hyphens
- 算力 ÷100 保留 2 位小数；人数 `COUNT(DISTINCT uid)` 整体去重
- 10 个固定活动 + TOTAL 行（UNION ALL）
- `act_list` 用底表 `SELECT DISTINCT` 生成（平台不接受无 FROM 常量 SELECT）
- 累计付费用户 = 全平台有过 `copilot_pay` 付费记录的 uid，与活动累计参与者取交集

---

## 周报 Insights（全量跑完后必出）

三个 Task 全部完成后，**必须在 `present_files` 的同一条回复里输出本周数据洞察**。不从 xlsx 重新读数据——直接用跑数据过程中已获取的数值。

### ⚠️ 核心原则：关注本周新情况

周报不是述职报告。**由活动本质决定的、每周都一样的结论不要重复**（如"过期总量始终大于消耗"这种结构性事实）。Insights 的价值在于指出**本周发生了哪些变化**：

- 新活动上线、某个活动量级突变（暴涨/暴跌）
- 趋势转折（过周率持续恶化 or 开始好转）
- 结构性问题（下发和消耗的活动排名倒挂、某个活动占过期比例畸高）
- 本期特有的异常数据点

如果本周一切和上周差不多，就说"本周整体平稳，无显著异常"，不要硬凑结论。

### Insight 必须覆盖的维度

**1. 过期率趋势（核心预警指标 — 必须带历史对比）**

这是每周最关键的指标。必须展示本周 + 上周 + 上上周的过期数据，形成趋势判断：
- 本周过期总量（万）、过期 / 下发 = 过期率（%）
- 相比上周的变化方向和幅度
- 过期主要来源活动 TOP 2 及其占比（如"新人福利过期占 73%"）
- 趋势判断：持续恶化 / 开始收敛 / 保持稳定

**2. 消耗效率结构（关注下发端 vs 消耗端的倒挂）**

不只报整体消耗率，更要对比**下发 TOP 活动和消耗 TOP 活动是否对应**：
- 下发端 TOP 3 活动及其占比
- 消耗端 TOP 3 活动及其占比
- 如果下发端和消耗端排名不一致（如"新人福利下发占 76% 但消耗只占 43%，每日登录消耗反超至 50%"），这是结构性问题的信号，必须展开说明

**3. 下发总览**
- 本周总下发算力（万）、对比上周的变化
- 如果有量级突变（±50%）的活动，单独标出
- 新增活动首次有数据时标注"🆕 新活动"

**4. 券分发（Task B）**
- 本周总计券数、总计人数、人均券数
- 知识库激励 vs skills 激励的发放分布（各档位人数占比）
- 创建知识号券数占比
- 仅在有显著变化时展开（如某个档位比例大幅变动）

**5. 一句话总结**
- 用一句话概括本周最值得关注的现象。模板：
  - "过期率连续 X 周恶化，本周达到历史最高的 XX%"
  - "新人福利发放占比持续上升（XX% → XX%），但消耗效率仍在下降"
  - "本周整体平稳，无显著异常"

### 输出格式

用简洁的表格 + 要点呈现，突出变化和对比。

```
## 📊 本周算力周报 Insights（{start}-{end}）

### 过期趋势
| 周期 | 过期总量 | 过期率 | 相比消耗的倍数 |
|------|----------|--------|----------------|
| 上上周 | X,XXX万 | XX% | X.X 倍 |
| 上周 | X,XXX万 | XX% | X.X 倍 |
| 本周 | X,XXX万 | XX% | X.X 倍 |

- 趋势判断：{持续恶化 / 开始收敛 / 保持稳定}
- 主要来源：新人福利占 XX%，{第二个活动}占 XX%

### 消耗结构
- 下发 TOP 3：活动A(XX%) / 活动B(XX%) / 活动C(XX%)
- 消耗 TOP 3：活动D(XX%) / 活动E(XX%) / 活动F(XX%)
- {如果倒挂，说明具体数据，如："新人福利下发占 76% 但消耗仅占 43%，每日登录消耗反超至 50%"}

### 下发总览
| 指标 | 本周 | 上周 | 变化 |
|------|------|------|------|
| 总下发 | X,XXX万 | X,XXX万 | +X% |

- {如有突变活动或新活动，在此标注}

### 一句话
{本周核心变化或"整体平稳"}
```
