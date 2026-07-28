---
name: xiaohongshu-note-organizer
description: >-
  小红书笔记整理工具。当用户提供小红书笔记链接（xhslink 短链接或 xiaohongshu.com 完整 URL），
  需要提取笔记内容并整理为结构化 Markdown 文档时使用此 Skill。
  典型触发场景：用户发送小红书链接并说"整理一下"、"提取内容"、"总结这篇笔记"、
  "帮我看下这个小红书链接"等。该 Skill 自动获取笔记数据（标题、正文、图片、标签），
  识别所有图片中的文字，整合为连贯的 Markdown 文档，去重、修错别字、删除 # 标签。
  无需任何 API Key，完全依赖 Agent 自身的多模态能力。
agent_created: true
---

## 用户偏好（重要）

- **输出格式**：纯文字 Markdown，**不引用图片、不保存图片文件、不输出图片路径**
- **图片处理**：所有图片通过 OCR（Read 工具读取图片）识别文字后整合进 Markdown 正文，图片本身不保留
- 每次只输出一个 .md 文件

# 小红书笔记整理

## 概述

将小红书图文笔记的链接转化为结构化的 Markdown 文档。提取笔记标题、正文、图片中的文字，整合去重后输出完整内容。

**零成本架构**：不需要任何外部 API Key。笔记数据通过 Python 脚本获取（利用小红书页面的 `__INITIAL_STATE__` 内嵌数据），图片 OCR 和内容整合由 Agent 自身的多模态能力完成。

对应 Coze 工作流 `xiaohongshu_recording` (ID: 7617434775414423606)。

## 工作流程

### 第 1 步：获取笔记数据

运行 `scripts/fetch_note.py` 获取笔记的标题、正文、图片 URL 和标签：

```bash
python <skill_dir>/scripts/fetch_note.py "<小红书链接>" --download-images <临时图片目录> --output <输出JSON路径>
```

- `<小红书链接>`：用户提供的 xhslink 短链接或 xiaohongshu.com 完整 URL
- `--download-images`：指定图片下载目录（建议用系统临时目录，如 `/tmp/xhs_images`）
- `--output`：指定 JSON 输出路径（建议用系统临时目录）

脚本输出 JSON 格式数据，包含字段：`noteId`、`title`、`content`、`images`、`localImages`（本地路径）、`tags`、`type`、`url`。

**依赖**：仅需 `requests` 库（`pip install requests`）。

### 第 2 步：识别图片文字（OCR）

对每张下载的图片执行 OCR 识别。使用 Agent 的多模态能力（Read 工具读取图片文件）替代外部视觉 API。

**逐张处理**：用 Read 工具读取每张图片，然后使用以下 Prompt 识别文字：

```
识别图片中的文字，原文输出，不得修改。
```

**严格要求**：
- 原文输出，不得修改、不得添加解释
- 表格内容保持表格格式（Markdown 表格）
- 如果图片中无文字（如纯图片/封面），返回空字符串
- 将每张图片的识别结果记录下来，按顺序编号

### 第 3 步：整合内容

将标题、正文、所有图片 OCR 结果整合为一份连贯的 Markdown 文档。

使用以下 Prompt（将变量替换为实际内容）：

```
整理这篇帖子的主要内容。标题是{title}，内容是{content}，图片中的文字是{output_list}。
首先将内容整合起来，如果内容和图片中的文字有重合要去重。
其次，要把内容合乎逻辑地整合起来，如果有识别错误、错别字等，进行修改。
最后，如果内容最后有很多用"#"的内容，要把这部分删掉。
尽量保持原文，非必要不得修改。
```

**变量替换**：
- `{title}` — 笔记标题
- `{content}` — 笔记正文
- `{output_list}` — 所有图片 OCR 结果拼接（用 `--- 图片N ---` 分隔）

**整合要求**：
- 内容和图片文字有重合时去重
- 修正 OCR 识别错误和错别字
- 删除末尾的 # 标签内容
- 尽量保持原文，非必要不修改
- 表格保持 Markdown 表格格式

### 第 4 步：输出结果

将整合后的内容保存为 Markdown 文件。文件头部包含元信息：

```markdown
# {标题}

> 来源：{原始链接}
> 整理时间：{当前时间}
> 工具：xiaohongshu-note-organizer (Skill)

---

{整合后的内容}
```

将文件保存到用户工作目录或用户指定的路径，并通过 present_files 展示给用户。

## 特殊情况处理

### 视频笔记

如果 `type` 字段为 `video`，`images` 数组中存的是视频 URL 而非图片。此时：
- 跳过 OCR 步骤（第 2 步）
- 仅整合标题和正文
- 在输出中注明"该笔记为视频类型，未识别视频内容"

### 无图片笔记

如果 `images` 数组为空，跳过 OCR 步骤，仅整合标题和正文。

### 获取失败

如果 `fetch_note.py` 返回空数据或报错：
1. 检查 URL 是否有效
2. 尝试用 WebFetch 工具直接获取页面内容
3. 如果仍失败，告知用户链接可能已失效或被删除

## 原始工作流参数

完整的原始工作流 Prompt 和模型参数记录在 `references/workflow_prompts.md` 中。
如需查看原 Coze 工作流的精确配置（模型、temperature、maxTokens 等），参考该文件。
