---
name: workbuddy-skin-maker
description: WorkBuddy 皮肤制作与安装。将图片素材 + CSS 打包成皮肤文件，安装到 WorkBuddy 客户端。触发词：做皮肤、安装皮肤、换肤、修改皮肤、皮肤制作、皮肤开发、定制主题、make skin、install skin、custom theme。
agent_created: true
---

# WorkBuddy 皮肤制作

你是用户的皮肤制作向导。加载本 skill 后，你需要**一步一步引导用户**完成皮肤制作，而不是一次性输出所有信息。

皮肤 = `theme/skin.css` + `theme/*.png` → `npx asar pack` 打包 → 注入 app.asar → Cmd+Q 重启生效。

## 总流程（按顺序执行）

1. **需求理解** → 2. **配色方案** → 3. **贴图/装饰** → 4. **音效（可选）** → 5. **安装 & 验证**

每一步完成后，展示当前阶段的成果，让用户确认再进入下一步。**绝不跳步。**

---

## 第一步：需求理解

### 1.1 了解 IP/主题
先问用户三个问题（一起问）：
- 你想做什么 IP / 主题风格？（如 Chiikawa、赛博朋克、简约商务…）
- 有没有参考图？可以发角色图、色板、截图，或口头描述想要的感觉
- 你的预期是「轻量换色」还是「大改」（改背景色+贴图+角色装饰）？

### 1.2 如果用户发了图片
- 仔细看图，提取关键视觉元素：主色调、辅助色、角色特征、风格基调
- 如果图里有人物/角色需要抠出来用，标记为「素材候选」
- 用自己的话复述一遍理解，确认无误再进入配色步骤

---

## 第二步：配色方案

### 2.1 确定主色
从参考图中提取或根据用户描述确定：
- **主背景色**：大面积底色。从参考图抽样最浅/最柔和的色调（不要刺眼的纯色）
- **Topbar / sidebar 色**：通常比主背景深或暖一档，形成层次
- **强调色**（可选）：按钮高亮、链接颜色等

如果用户没给参考图，根据 IP 自动推断（如 Chiikawa → 米黄 `#FFF8E7` + 粉色 topbar `#FFB5C2`）。

### 2.2 展示配色（确认点）
把颜色以可视方式展示给用户看（色块 + 十六进制值 + 用途标注），问：
- "这个配色方向对吗？需要调亮/调暗/换色吗？"

等用户确认后才进入下一步。

### 2.3 写出背景色 CSS
确认配色后，先写出背景色规则。**必须同时用 `background-color`（不用简写 `background`）覆盖以下全部容器：**

```css
.main-content, .main-content--chat, .main-content--welcome,
.teams-container [data-view-id], .teams-main-content,
.conversation-list, .wb-home-page, .wb-home-page__main-content {
  background-color: <主背景色> !important;
}

.conversation-list-topbar {
  background-color: <topbar色> !important;
}
```

**不要急着加其他 CSS，先让用户确认：背景色写好了，下一步做贴图。**

---

## 第三步：贴图/装饰

### 3.1 告知图片要求
告诉用户什么样的图片合适：

| 要求 | 说明 |
|------|------|
| 格式 | PNG（需要透明背景） |
| 内容 | 角色/装饰物，背景尽可能干净纯色（白底最佳），方便抠图 |
| 尺寸 | ⚠️ 不要太大也不要太小。贴图用宽度 80-120px 即可，CSS 中用 `background-size: contain` 适配；角色装饰（topbar 小图标）每个 24×24px |
| 数量 | 首页贴图 1 张就够了；topbar 角色装饰 1-3 个小图标（可选） |

### 3.2 抠图（用户提供素材后）

⚠️ **绝不用 PIL flood fill / OpenCV 阈值抠图。** 原因：反走样灰白像素会连通白色主体和白色背景，导致人物白色部分被误删（翻车案例：乌萨奇白脸被抠掉）。

**正确方案：rembg（U2Net AI 扣图）**

```python
from rembg import remove
from PIL import Image
img = Image.open("input.jpg").convert("RGB")
out = remove(img)
bbox = out.getbbox()
cropped = out.crop(bbox)
cropped.resize((w, h), Image.LANCZOS).save("output.png")
```

抠完后**必须把抠图结果给用户看**，确认白脸/白衣服等白色部分完整保留。

### 3.3 贴图定位

#### 3.3.1 选择贴图位置

对话页/首页装饰图挂在 `wb-home-composer__input-slot::after`：

```css
.wb-home-composer__input-slot {
  position: relative !important;
  overflow: visible !important;
}
.wb-home-composer__input-slot::after {
  content: "";
  position: absolute;
  top: -<height>px;     /* ⚠️ 负值 = 高度取反，让底边贴住 slot 上边框 */
  right: 8px;
  width: <w>px;
  height: <h>px;
  background-image: url("./sticker.png");
  background-size: contain;
  background-repeat: no-repeat;
  background-position: bottom right;
  z-index: 50;
  pointer-events: none;
  filter: drop-shadow(0 2px 3px rgba(0, 0, 0, 0.18));
}
```

#### 3.3.2 贴图尺寸规则

- 先看原始图宽高比，算出等比缩放后的 CSS `width` 和 `height`
- `top: -height` 让底边对齐 slot 上边框（即图片底部"坐"在输入框上沿）
- 如果图片太宽/太高，调小 `width`；`height` 按比例跟随
- 示例：1200×1600 原图 → width: 90px, height: 120px, top: -120px

#### 3.3.3 ⚠️ overflow 级联裁剪（高频翻车点）

`wb-home-page` 有 `overflow-x: hidden`，会隐含 `overflow-y: auto`。贴图用负 top 探出容器时，**所有祖先必须加：**

```css
.wb-home-composer,
.wb-home-page,
.wb-home-page__main-content,
.wb-home-page__content,
.wb-home-composer__input-slot {
  overflow: visible !important;
}
```

**不写这段 = 贴图不可见。这是#1翻车点。**

### 3.4 角色装饰（可选）

如果用户想在 topbar 放角色小图标：

```css
.conversation-list-topbar::after {
  content: "";
  display: block;
  margin-left: auto;
  width: <N*24>px;     /* 3个角色 = 72px；2个 = 48px */
  height: 24px;
  background-image: url("./char1.png"), url("./char2.png"), url("./char3.png");
  background-size: 24px 24px;
  background-repeat: no-repeat;
  background-position: 0 center, 24px center, 48px center;
  pointer-events: none;
}
```

#### ⚠️ 角色装饰翻车点

**绝对禁止**在以下容器上使用 `::after`：
- `workbuddy-topbar` — `justify-content: space-between`，::after 会创建第3个 flex 子元素，把 icon 挤走
- `claw-agent-chat-topbar` — 同上

**只能**挂在 `conversation-list-topbar::after`（sidebar 内部，不影响主布局）。

用 `margin-left: auto` 推到最右，不挤占原有 button 的位置。

---

## 第四步：音效（可选，主动提示跳过）

⚠️ 告诉用户：音效不是必须的，这一步可以跳过。除非用户明确想要自定义音效。

如果需要音效：
- 格式：.wav / .mp3
- 路径：与 skin.css 同目录，CSS 中用 `url()` 引用
- 需确认消息提示音、发送音等具体场景

**在提示用户可跳过之后，直接问："要跳过音效这一步吗？还是想加？"**

---

## 第五步：安装 & 验证

### 5.1 目录结构

确保用户的项目目录如下：
```
my-skin/
└── theme/
    ├── skin.css
    ├── sticker.png       （贴图）
    ├── char1.png         （可选）
    ├── char2.png         （可选）
    └── char3.png         （可选）
```

### 5.2 安装

```bash
bash ~/.workbuddy/skills/workbuddy-skin-maker/scripts/install.sh <theme-project-dir>
```

安装后告诉用户：**Cmd+Q 完全退出 WorkBuddy，再重新打开**才能看到皮肤。

### 5.3 验证清单

用户启动后，引导检查以下几点：
1. 背景色是否均匀（没有白边/色差）
2. 贴图是否完整显示（没有裁切/消失）
3. topbar 图标位置是否正常（没有被挤跑）
4. 角色装饰是否在侧边栏顶栏右侧

### 5.4 调试（出问题时对照）

| 症状 | 原因 | 修复 |
|------|------|------|
| 贴图完全看不到 | overflow 级联裁剪 | 补 `overflow: visible !important` 到所有祖先 |
| 贴图被裁掉一半 | top 负值不够或图片太高 | 检查 `top: -height` 是否等于图片 CSS 高度 |
| topbar 图标跑到右边去了 | ::after 破坏了 space-between | 检查是否误在 workbuddy-topbar / claw-agent-chat-topbar 用了 ::after |
| 贴图被输入框压住 | z-index 不够或用了 topRightSlotStandalone（z-index:0） | 换成 `::after` + `z-index: 50` |
| 人物白色部分被抠掉了（脸/衣服消失） | 用了 PIL flood fill | 换 rembg 重新抠图 |
| 图片位置偏移 | 原始尺寸和 CSS width/height 不匹配 | 按原图比例重新计算 width/height，top = -height |

---

## 交互原则

- **每步确认**：配色 → 用户确认 → 贴图 → 用户确认 → 安装 → 验证
- **展示抠图结果**：抠完图必须让用户看到再继续
- **不跳步**：即使用户说"直接做完"，也要最少确认配色和贴图位置
- **翻车预防**：在写入 overflow 保护、::after 位置等关键操作前，向用户说明为什么需要这样写
