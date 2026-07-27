# 灯塔(Beacon) DataInsight 平台 — 关键页面元素与交互参考

> 此文档记录灯塔平台页面中关键 UI 元素的定位方式和交互行为，供自动化脚本在页面结构变化时参考调试。

## 1. 页面布局概述

灯塔 DataInsight 页面主要由以下区域组成：
- **左侧导航栏**: 项目列表、分析模式入口
- **中央内容区**: 查询条件区 + 数据表格/图表展示区
- **右侧浮动工具栏**: "快捷工具"侧边栏（默认收起）

## 2. 关键 UI 元素

### 2.1 探索分析面板 (修改查询天数)

**位置**: 页面左上角区域，点击后在页面左侧展开设置面板  
**按钮元素**: 包含"探索分析"文字的元素，或 `class` 包含 `show_setting` / `setting_btn` 的元素  
**定位方式**:
```javascript
// 方式一：文字匹配
const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_ELEMENT);
while (walker.nextNode()) {
    const el = walker.currentNode;
    if (el.offsetParent === null && el.tagName !== 'BODY') continue;
    const text = (el.innerText || el.textContent || '').trim().substring(0, 20);
    if (text.includes('探索分析')) {
        const rect = el.getBoundingClientRect();
        // 筛选 y < 200 的小元素（按钮本身而非容器）
    }
}

// 方式二：class 匹配
document.querySelectorAll('[class*="show_setting"],[class*="setting_btn"]');
```
**行为**: 点击后左侧展开面板，显示天数设置区域（`- 30 +` 格式的天数输入框和"确定"按钮）。

#### 天数输入框

**位置**: 探索分析面板内，显示为 `- [数字] +` 格式  
**元素**: `<input type="number">` 或 `input.el-input__inner`，默认值为 `30`  
**定位方式**:
```javascript
document.querySelectorAll('input[type="number"],input.el-input__inner').forEach(el => {
    if (el.offsetParent === null) return;
    const rect = el.getBoundingClientRect();
    // 面板区域内 y < 300 且 val === '30' 的输入框
    if (el.value === '30' && rect.y < 300) { /* 目标输入框 */ }
});
```
**修改值方式**: 使用 `nativeInputValueSetter` 确保框架响应：
```javascript
const nativeSetter = Object.getOwnPropertyDescriptor(
    window.HTMLInputElement.prototype, 'value'
).set;
nativeSetter.call(el, '180');
el.dispatchEvent(new Event('input', { bubbles: true }));
el.dispatchEvent(new Event('change', { bubbles: true }));
el.dispatchEvent(new KeyboardEvent('keyup', { bubbles: true }));
```

#### 确定按钮

**位置**: 探索分析面板内，天数输入框附近  
**元素**: `<button>` 标签，`innerText` 为 `"确定"` 或 `"确 定"`  
**定位方式**:
```javascript
document.querySelectorAll('button').forEach(el => {
    if (el.offsetParent === null) return;
    const text = (el.innerText || '').trim();
    if (text === '确定' || text === '确 定') {
        const rect = el.getBoundingClientRect();
        if (rect.y < 300) { /* 面板内的确定按钮 */ }
    }
});
```
**行为**: 点击后触发异步查询，页面显示"校验查询请求 → 智能解析查询 → 动态资源评估 → 融合引擎查询"进度条。查询通过 `panel_card_result/async_query` API 轮询，`query_state` 从 `RUNNING` 变为 `SUCCESS` 时数据就绪。

### 2.2 导出/下载按钮 (表格工具栏)

**位置**: 数据表格上方的工具栏区域  
**元素**: `<img>` 标签，`src` 中包含 `download.png`  
**定位方式**:
```javascript
const imgs = document.querySelectorAll('img');
for (const img of imgs) {
    if (img.src && img.src.toLowerCase().includes('download')) {
        // img.getBoundingClientRect() 获取坐标
    }
}
```
**行为**: 点击后会触发一个后台导出任务，同时页面顶部出现绿色通知条提示"任务已提交"。注意点击此按钮有时会同时触发"保存到分析列表"对话框，需要关闭。

### 2.3 快捷工具侧边栏切换按钮

**元素**: `class` 包含 `tool_jt` 的元素  
**位置**: 页面最右侧，垂直居中附近  
**定位方式**:
```javascript
const els = document.querySelectorAll('[class*="tool_jt"]');
for (const el of els) {
    const r = el.getBoundingClientRect();
    if (r.width > 0 && r.x > 1000) // 确保在右侧
        return [r.x + r.width/2, r.y + r.height/2];
}
```
**行为**: 点击后展开右侧侧边栏，显示一列工具图标和文字。

### 2.4 下载管理入口

**位置**: 展开后的快捷工具侧边栏中  
**元素**: `innerText` 精确匹配 `'下载管理'` 的元素  
**所属容器**: `class` 包含 `feedback-box` 的区域  
**定位方式**:
```javascript
const els = document.querySelectorAll('*');
for (const el of els) {
    if ((el.innerText || '').trim() === '下载管理') {
        const r = el.getBoundingClientRect();
        if (r.width > 0 && el.offsetParent !== null)
            return [r.x + r.width/2, r.y + r.height/2];
    }
}
```
**行为**: 点击后弹出"下载任务列表"对话框。

### 2.5 下载任务列表对话框

**容器**: `.el-dialog__wrapper` 中可见的 `.el-dialog`  
**标题**: `el-dialog__title` 元素，文本为"下载任务列表"  
**内容**: 包含表格 `<tbody>` 的任务列表，每行有：
  - 任务 ID
  - 任务名称
  - 创建人
  - 状态（"完成" / "进行中" / "失败"）
  - "下载" 按钮

**下载按钮定位**:
```javascript
// 在对话框内查找 innerText === '下载' 的叶子元素
const btns = [];
const allEls = dialog.querySelectorAll('*');
for (const el of allEls) {
    if ((el.innerText || '').trim() === '下载' && el.children.length === 0) {
        btns.push(el);
    }
}
```

## 2.6 敏捷分析模式 — 时间设置区域 (Analytics_Mode)

敏捷分析模式的 URL 格式: `.../Analytics_Mode/{project_id}/New_Event_Card_Modify/{card_id}`

### 时间设置 UI 布局

```
时间设置  [相对时间 v]  过去  [-] [120] [+]  [天 v]   □ 对比 ?
[立即分析] [后台分析] [查看SQL]
```

- **时间设置标签**: 文字精确匹配 `"时间设置"`，位于该行最左侧
- **天数输入框**: 与"时间设置"同行 (y坐标差 < 30px)，`<input>` 类型，值为纯数字 (如 30, 120, 180)
- **"立即分析"按钮**: `<button>` 标签，`innerText` 包含 `"立即分析"`，class 含 `el-button--primary el-button--mini`

### 时间设置标签定位

```javascript
const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_ELEMENT);
while (walker.nextNode()) {
    const el = walker.currentNode;
    if (el.offsetParent === null && el.tagName !== 'BODY') continue;
    const text = (el.innerText || el.textContent || '').trim();
    if (text === '时间设置' || text.startsWith('时间设置')) {
        const rect = el.getBoundingClientRect();
        if (rect.width > 0 && rect.width < 200) {
            // 记录 y 坐标，用于查找同行的天数输入框
        }
    }
}
```

### 天数输入框定位

```javascript
// 在"时间设置"同行 (y坐标接近) 找纯数字输入框
const labelY = /* 时间设置标签的 y 坐标 */;
document.querySelectorAll('input[type="number"],input.el-input__inner').forEach(el => {
    if (el.offsetParent === null) return;
    const rect = el.getBoundingClientRect();
    if (Math.abs(rect.y - labelY) < 30) {  // 同行
        const val = el.value;
        if (/^\d+$/.test(val) && parseInt(val) >= 1 && parseInt(val) <= 999) {
            // 目标天数输入框
        }
    }
});
```

### "立即分析"按钮定位

```javascript
document.querySelectorAll('button').forEach(el => {
    if (el.offsetParent === null) return;
    const text = (el.innerText || '').trim();
    if (text.includes('立即分析')) {
        // el.classList.contains('el-button--primary') 确认是主按钮
        const rect = el.getBoundingClientRect();
    }
});
```

**对应 HTML**:
```html
<button data-v-260ce768="" type="button" 
  class="el-button el-button--primary el-button--mini" 
  data-v-0d660d00="" style="margin-left: 80px;">
  <span> 立即分析 </span>
</button>
```

**行为**: 点击后触发异步查询，与 TV 模式类似，查询通过 API 轮询，`query_state` 从 `RUNNING` 变为 `SUCCESS` 时数据就绪。

### TV 模式 vs 敏捷分析模式对比

| 特性 | TV 模式 (PanelMax) | 敏捷分析模式 (Analytics_Mode) |
|------|-------------------|------------------------------|
| URL 特征 | `/PanelMax/` | `/Analytics_Mode/` |
| 时间修改入口 | "探索分析"按钮 → 展开面板 | 页面顶部"时间设置"区域 |
| 天数输入 | 面板内 `- [30] +` | 行内 `- [120] +` |
| 确认按钮 | "确定" | "立即分析" |
| 按钮特征 | `button` innerText=`"确定"` | `button.el-button--primary.el-button--mini` innerText含`"立即分析"` |

## 3. 常见问题

### 3.1 页面加载未完成就交互
灯塔事件分析页面在打开后会自动执行查询，页面左上角会显示进度百分比。需要等待表格数据完全加载后再操作。建议检查 `.el-table__body tr` 的行数是否 > 5。

### 3.2 idle timeout 导致脚本被杀
在长时间 `time.sleep()` 时，如果没有标准输出，执行环境可能会因为 idle timeout 杀掉进程。解决方法：用带 `flush=True` 的 print 或 `sys.stdout.write() + flush()` 保持输出活跃。

### 3.3 CSV 文件 BOM 头
灯塔导出的 CSV 文件使用 UTF-8 with BOM 编码，文件头部有 `\ufeff`。读取时使用 `encoding='utf-8-sig'` 可自动处理。

### 3.4 "保存到分析列表"干扰弹窗
点击导出按钮后有时会同时弹出"保存到分析列表"对话框。通过查找所有可见的 `.el-dialog__headerbtn` 并关闭即可。

## 4. API 参考

### 下载任务列表 API
- **URL**: `https://beacon.woa.com/api/datainsight/webserver/download/list`
- **方法**: GET/POST
- **说明**: 返回当前用户的下载任务列表，包含任务 ID、名称、状态、下载链接等信息
