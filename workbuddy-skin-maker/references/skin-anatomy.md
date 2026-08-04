# WorkBuddy 皮肤 CSS 结构详解

> ⚠️ 本文是技术参考手册，供 Agent 在引导用户制作皮肤时查阅。
> 实际执行流程请遵循 SKILL.md 的 5 步交互引导，不要跳过用户确认环节。

## 背景色容器（8 容器全覆盖）

WorkBuddy 主界面由以下几个独立滚动的区域组成，皮肤 CSS 必须覆盖全部以消除白边/色差：

```css
.main-content,
.main-content--chat,
.main-content--welcome,
.teams-container [data-view-id],
.teams-main-content,
.conversation-list,
.wb-home-page,
.wb-home-page__main-content {
  background-color: <主背景色> !important;
}
```

**规则**：用 `background-color` 不用 `background` 简写（避免覆盖其他 background 属性如图片/渐变）。

## Topbar 结构

主页加载时有两种 topbar 并排显示：

### 1. conversation-list-topbar（左侧侧边栏顶栏）
- 默认 `justify-content: flex-end`（所有动作靠右）
- 含 3 个 button：SidebarCollapseButton、SearchButton、TaskFilterButton
- **安全插入点**：`conversation-list-topbar::after` — 不影响 flex 布局，内容靠最右

### 2. workbuddy-topbar（主内容区顶栏）
- `display: flex; justify-content: space-between;` — **2 子元素**
- 子元素 1：`workbuddy-topbar-title`（SidebarExpandButton + ClawWorkspaceTitle）
- 子元素 2：`workbuddy-topbar-options`（内部 left + actions）
- **红线**：绝对禁止在 `workbuddy-topbar` 上使用 `::after` — 会创建第 3 个 flex 子元素，破坏 space-between 布局

### 3. claw-agent-chat-topbar（对话状态顶栏）
- `display: flex; justify-content: space-between;`
- 子元素：`__left`（expand + title） + `__actions`（编辑/设置/面板按钮）
- **红线**：同样禁止在此容器上使用 `::after`

## 对话框 / Input Slot 结构

### wb-home-composer（首页输入框容器）
- 内部 `<div class="wb-home-composer__input-slot">` 是输入框本身的 slot
- input-slot 内有 `<topRightSlotStandalone>` 容器（position: absolute, top: -80px, z-index: 0）
- **贴图推荐位置**：`wb-home-composer__input-slot::after` — position: absolute 在 slot 内部，可控

### 贴图容器的 overflow 级联问题
`wb-home-page` 有 `overflow-x: hidden` → CSS 规范会隐含设置 `overflow-y: auto`。
贴图用 `top: -Npx` 探出容器时，所有祖先必须加：
```css
.wb-home-composer,
.wb-home-page,
.wb-home-page__main-content,
.wb-home-page__content,
.wb-home-composer__input-slot {
  overflow: visible !important;
}
```

## 贴图方案对比

| 方案 | 适用场景 | 问题 |
|------|----------|------|
| `::after` + `background-image` 挂在 input-slot | 首页对话框贴图 | ✅ 最可控，top/right/width/height 完全自由 |
| `topRightSlotStandalone` + `content: url()` | 系统预留的贴图位 | ❌ z-index:0 被内容覆盖；top:-80px 固定不可调；overflow 套娃 |
| `::after` 挂在 page 级容器 | 全局装饰 | ❌ 位置难以精确对准具体组件 |

## Topbar 角色装饰

角色图标（如 Chiikawa 三只角色）应放在 sidebar topbar：
```css
.conversation-list-topbar::after {
  content: "";
  display: block;
  margin-left: auto;
  width: 72px;
  height: 24px;
  background-image: url("./kuri-manju.png"), url("./momonga.png"), url("./chiichi.png");
  background-size: 24px 24px;
  background-repeat: no-repeat;
  background-position: 0 center, 24px center, 48px center;
  pointer-events: none;
}
```
`margin-left: auto` 将 `::after` 推到最右，不影响已有的 button 图标。

## 暗色模式

```css
body.dark {
  --vscode-editor-background: <暗底色> !important;
  --vscode-sideBar-background: <暗侧栏色> !important;
  --vscode-editor-foreground: <暗前景色> !important;
}
```
