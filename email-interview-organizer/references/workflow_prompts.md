# 原始工作流 Prompt 与参数

本文件记录了 Coze 工作流 `email_interview` (ID: 7641193918574739491) 中各节点的原始 Prompt 和模型参数。
Skill 执行时应严格遵循这些 Prompt，确保输出与原工作流一致。

---

## 工作流结构

```
开始(time, auth_code, email, password)
    │
    ▼
密码验证(代码 100002) ── 校验密码，通过则透传凭证
    │ auth_code, email
    ▼
get_email_list(插件 104017) ── QQ邮箱助手, 拉取30封
    │ emails
    ▼
文本处理(LLM 188579) ── 豆包·1.8·深度思考, temp=0.5
    │ output (list<string>)
    ▼
┌──────────────────────────────────────────────────┐
│  循环(191631) ── 最多30次                          │
│  │  input                                         │
│  ▼                                                │
│  意图识别(196326) ── 豆包·2.0·lite, temp=0.3     │
│  │                                                │
│  ├── 日程 ──▶ 变量拆分(191285) ──▶ 代码(123894)  │
│  │             │ 豆包·1.8·深度思考    │ 正则解析   │
│  │             │                     ▼           │
│  │             │              create_event(176979)│
│  │             │              飞书日历             │
│  │                                                │
│  ├── 任务 ──▶ 变量拆分2(142089) ──▶ 代码_1(1445446)│
│  │             │ 豆包·1.8·深度思考    │ 正则解析   │
│  │             │                     ▼           │
│  │             │              create_task(172179) │
│  │             │              飞书任务             │
│  │                                                │
│  └── 信息 ──▶ 跳过                               │
└──────────────────────────────────────────────────┘
    │
    ▼
  结束(900001)
```

---

## 节点 100002：密码验证

- **类型**: code (JavaScript)
- **用途**: 验证调用密码

### 代码

```javascript
async function main({ params }) {
    const password = params.password || "";
    const auth_code = params.auth_code || "";
    const email = params.email || "";
    const CORRECT_PASSWORD = "interview@2024";
    if (password !== CORRECT_PASSWORD) {
        throw new Error("密码错误，无权调用此工作流");
    }
    return { auth_code, email };
}
```

> **Skill 说明**: Skill 由用户直接调用，无需密码保护。此节点在 Skill 中省略。

---

## 节点 104017：get_email_list

- **类型**: plugin
- **插件**: QQ邮箱助手
- **输入**: auth_code, email, count=30
- **输出**: emails (list: subject, from, date, content)

> **Skill 说明**: 用 QQ 邮箱连接器或 `scripts/fetch_emails.py` 替代。

---

## 节点 188579：文本处理

- **类型**: llm
- **模型**: 豆包·1.8·深度思考

### 模型参数

| 参数 | 值 |
|------|-----|
| modelType | 1768187121 |
| modelName | 豆包·1.8·深度思考 |
| generationDiversity | balance |
| temperature | 0.5 |
| topP | 1 |
| frequencyPenalty | 0 |
| maxTokens | 8192 |
| responseFormat | 2 |
| spCurrentTime | false |
| spAntiLeak | false |
| enableChatHistory | false |
| chatHistoryRound | 3 |
| canContinue | false |
| retryTimes | 2 |
| timeoutMs | 180000 |

### 输入变量

| 变量名 | 来源 |
|--------|------|
| `input` | 104017 → emails |
| `time` | 100001 → time |

### System Prompt

```
step1：判断{{input}}中的每封邮件是否和招聘相关，如果是，保留，如果不是，直接删掉。
判断邮件时间是否晚于{{time}}，如果晚，保留，如果早，直接删掉。
step2：将内容分条整理，列出每封邮件的时间、内容。
时间要具体到分钟。
内容尽量保持原文，如果原文语意不通，可以加上一些文字使内容连贯。
内容中如果有链接，必须保留。
step3：精简内容
如果这是一个测试邮件，保留描述和测试链接即可；
如果这是一个邀约面试的邮件，保留描述和选择面试时间的链接；
如果这是一封面试邮件，保留描述和面试链接；
如果这是一封offer邮件，保留描述offer链接。
step4：采用"每封邮件的内容作为一个独立值"的结构输出整理后的面试文本
```

### User Prompt

（空）

---

## 节点 196326：意图识别

- **类型**: intent
- **模式**: all

### 意图定义

| 序号 | 意图名称 |
|------|---------|
| 1 | 日程 |
| 2 | 任务 |
| 3 | 信息 |

### 模型参数

| 参数 | 值 |
|------|-----|
| modelName | 豆包·2.0·lite |
| modelType | 1.772546477e+09 |
| temperature | 0.3 |
| topP | 1 |
| frequencyPenalty | 0 |
| maxTokens | 100 |
| maxOutputTokens | 4096 |
| generationDiversity | default_val |
| responseFormat | 2 |
| reasoning_effort | minimal |
| thinkingType | disabled |
| enableChatHistory | false |
| chatHistoryRound | 3 |
| cachingExpireTime | 259200 |
| store | true |
| retryTimes | 2 |
| timeoutMs | 60000 |

### System Prompt

```
分析{{query}}，
如果是面试邮件，告诉我什么时候面试，则为"日程"。
如果是邀请选择面试时间、邀请测评，则为"任务"。
如果是其他，则为"信息"。
```

### User Prompt

```
{{query}}
```

---

## 节点 191285：变量拆分（日程分支）

- **类型**: llm
- **模型**: 豆包·1.8·深度思考

### 模型参数

| 参数 | 值 |
|------|-----|
| modelType | 1768187121 |
| modelName | 豆包·1.8·深度思考 |
| generationDiversity | balance |
| temperature | 0.5 |
| topP | 1 |
| frequencyPenalty | 0 |
| maxTokens | 8192 |
| responseFormat | 2 |
| spCurrentTime | false |
| spAntiLeak | false |
| enableChatHistory | false |
| chatHistoryRound | 3 |
| canContinue | false |
| retryTimes | 2 |
| timeoutMs | 180000 |

### 输入变量

| 变量名 | 来源 |
|--------|------|
| `input` | 191631 (循环) → input |

### System Prompt

```
提取{{input}}中的内容，输出为
summary：提取公司、部门、岗位名称，例如美团核心本地商业AI产品经理面试
start_time：开始时间，参考格式：2006-01-02 15:04:05
end_time：结束时间，参考格式：2006-01-02 15:04:05。如果没有表明，设置为开始时间后一小时
description：其他内容
```

### User Prompt

（空）

---

## 节点 123894：代码（日程分支）

- **类型**: code (JavaScript)
- **用途**: 正则解析 LLM 输出为四个字段

### 代码

```javascript
async function main({ params }) {
    const input = params.input || "";
    let summary = null;
    let start_time = null;
    let end_time = null;
    let description = null;

    const summaryMatch = input.match(/summary\s*[：:]\s*(.+?)(?=\nstart_time|start_time|$)/is);
    const startMatch = input.match(/start_time\s*[：:]\s*(.+?)(?=\nend_time|end_time|$)/is);
    const endMatch = input.match(/end_time\s*[：:]\s*(.+?)(?=\ndescription|description|$)/is);
    const descMatch = input.match(/description\s*[：:]\s*(.+)/is);

    if (summaryMatch) summary = summaryMatch[1].trim().replace(/\\n|\n|\r/g, '');
    if (startMatch) start_time = startMatch[1].trim().replace(/\\n|\n|\r/g, '');
    if (endMatch) end_time = endMatch[1].trim().replace(/\\n|\n|\r/g, '');
    if (descMatch) description = descMatch[1].trim().replace(/\\n|\n|\r/g, '');

    return { summary, start_time, end_time, description };
}
```

> **Skill 说明**: Agent 直接输出结构化字段格式，无需正则解析。

---

## 节点 142089：变量拆分2（任务分支）

- **类型**: llm
- **模型**: 豆包·1.8·深度思考

### 模型参数

与节点 191285 相同（豆包·1.8·深度思考, temp=0.5, maxTokens=8192）。

### System Prompt

```
提取{{input}}中的内容，输出为
summary：先判断是邀请测试还是邀请面试，前方分别标【测评邀请】【面试邀请】。然后提取公司、部门、岗位名称，例如美团、核心本地商业、AI产品经理。最后撰写标题：【面试邀请】美团-核心本地商业-AI产品经理
start_time：开始时间，参考格式：2006-01-02 15:04:05。没有可以不写
end_time：结束时间，参考格式：2006-01-02 15:04:05。有可能会出现"三天内""五个工作日内"等描述，请根据邮件内容中提到的时间为基准推算具体截止日期。注意"工作日"不包含周末（周六、周日）。如果无法确定具体日期，请保留原文描述，不要猜测。
description：其他内容
```

### User Prompt

（空）

---

## 节点 1445446：代码_1（任务分支）

- **类型**: code (JavaScript)
- **用途**: 正则解析 LLM 输出为四个字段

### 代码

与节点 123894 完全相同。

> **Skill 说明**: Agent 直接输出结构化字段格式，无需正则解析。

---

## 节点 176979：create_event

- **类型**: plugin
- **插件**: 飞书日历
- **输入**: summary, start_time, end_time, description, need_notification=true

> **Skill 说明**: 用 `lark-calendar` skill 替代。

---

## 节点 172179：create_task

- **类型**: plugin
- **插件**: 飞书任务
- **输入**: summary, description, end_time, start_time

> **Skill 说明**: 用 `lark-task` skill 替代。

---

## 模型对比汇总

| 节点 | 模型 | temperature | maxTokens | 特殊配置 |
|------|------|-------------|-----------|---------|
| 188579 文本处理 | 豆包·1.8·深度思考 | 0.5 | 8192 | — |
| 196326 意图识别 | 豆包·2.0·lite | 0.3 | 100 | thinkingType=disabled, reasoning_effort=minimal |
| 191285 变量拆分 | 豆包·1.8·深度思考 | 0.5 | 8192 | — |
| 142089 变量拆分2 | 豆包·1.8·深度思考 | 0.5 | 8192 | — |

> **Skill 说明**: 所有 LLM 步骤由 Agent 自身完成，不再依赖特定模型。Prompt 保持原文一致。
