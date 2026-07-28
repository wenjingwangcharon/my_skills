# 原始工作流 Prompt 与参数

本文件记录了 Coze 工作流 `xiaohongshu_recording` (ID: 7617434775414423606) 中两个 LLM 节点的原始 Prompt 和模型参数。
Skill 执行时应严格遵循这些 Prompt，确保输出与原工作流一致。

---

## 节点 168388：OCR 图片文字识别

### 模型参数

| 参数 | 值 |
|------|-----|
| 模型 | 豆包·1.6·lite·251015 |
| modelId | 1761532732 |
| temperature | 0.5 |
| topP | 1 |
| maxTokens | 8192 |
| responseFormat | 2 |
| thinkingType | enabled |
| reasoning_effort | medium |

### Prompt

**systemPrompt:**
```
识别{{input}}中的文字，原文输出，不得修改。
```

**说明：** `{{input}}` 是循环中当前图片的 URL。Agent 执行时应将此 prompt 用于读取每张图片并识别文字。

---

## 节点 120975：内容整合

### 模型参数

| 参数 | 值 |
|------|-----|
| 模型 | 豆包·1.8·深度思考 |
| modelId | 1768187121 |
| temperature | 0.5 |
| topP | 1 |
| maxTokens | 8192 |
| responseFormat | 2 |
| thinkingType | enabled |
| reasoning_effort | medium |

### Prompt

**systemPrompt:**
```
整理这篇帖子的主要内容。标题是{title}，内容是{content}，图片中的文字是{output_list}。
首先将内容整合起来，如果内容和图片中的文字有重合要去重。
其次，要把内容合乎逻辑地整合起来，如果有识别错误、错别字等，进行修改。
最后，如果内容最后有很多用"#"的内容，要把这部分删掉。
尽量保持原文，非必要不得修改。
```

**变量说明：**
- `{title}` — 笔记标题
- `{content}` — 笔记正文
- `{output_list}` — 所有图片 OCR 结果的拼接文本

**userPrompt:**
```
请按照要求整理。
```

---

## 输出格式

最终输出为纯文本 Markdown，包含整合后的完整笔记内容。不添加额外的格式包装。
