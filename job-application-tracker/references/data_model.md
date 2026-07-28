# 数据模型定义

## 完整数据结构

```json
{
  "version": 1,
  "last_updated": "2026-07-12T14:08:00",
  "status_types": [
    "投递",
    "笔试",
    "AI面试",
    "一面",
    "二面",
    "三面",
    "四面",
    "HR面",
    "Offer"
  ],
  "applications": [
    {
      "id": "001",
      "company": "腾讯",
      "department": "CSIG",
      "position": "IMA产品经理",
      "job_detail": "负责 IMA 产品规划与设计...",
      "channel": "官网",
      "apply_date": "2026-07-12",
      "current_status": "二面",
      "status_history": [
        {
          "status": "投递",
          "date": "2026-07-12",
          "note": "通过官网投递"
        },
        {
          "status": "笔试",
          "date": "2026-07-15",
          "note": ""
        },
        {
          "status": "一面",
          "date": "2026-07-18",
          "note": "技术面，问了项目经验"
        },
        {
          "status": "二面",
          "date": "2026-07-20",
          "note": ""
        }
      ],
      "is_active": true,
      "end_result": null,
      "notes": ""
    }
  ]
}
```

## 字段说明

### 顶层字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `version` | number | 数据结构版本号，当前为 1 |
| `last_updated` | string | 最后更新时间（ISO 8601 格式） |
| `status_types` | string[] | 所有已使用的状态类型列表，动态扩展 |
| `applications` | object[] | 投递记录数组 |

### application 对象字段

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | string | 是 | 递增序号，三位数补零（001, 002, ...） |
| `company` | string | 是 | 公司名称 |
| `department` | string | 否 | 部门或业务线 |
| `position` | string | 是 | 岗位名称 |
| `job_detail` | string | 否 | 岗位详情/JD |
| `channel` | string | 否 | 投递渠道（官网/Boss直聘/内推/猎头等） |
| `apply_date` | string | 是 | 投递日期（YYYY-MM-DD） |
| `current_status` | string | 是 | 当前状态（取自 status_types） |
| `status_history` | object[] | 是 | 状态变更历史 |
| `is_active` | boolean | 是 | 是否仍在进行中 |
| `end_result` | string/null | 是 | 终态：null / "通过" / "终止" |
| `notes` | string | 否 | 其他备注 |

### status_history 对象字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `status` | string | 状态名称 |
| `date` | string | 日期（YYYY-MM-DD） |
| `note` | string | 备注（如面试内容、结果反馈等） |

## 模糊匹配示例

### 示例 1：单一匹配

```
记录：
  001 腾讯 CSIG IMA产品经理 [活跃]
  002 字节跳动 抖音 后端开发 [活跃]

用户说："腾讯那个二面了"
匹配过程：
  1. 提取线索：公司=腾讯
  2. 筛选活跃记录中 company 包含"腾讯" → 匹配到 001
  3. 恰好 1 条 → 直接操作
结果：更新 001 的状态为"二面"
```

### 示例 2：多条匹配需反问

```
记录：
  001 腾讯 CSIG IMA产品经理 [活跃]
  002 腾讯 WXG 后端开发 [活跃]

用户说："腾讯那个二面了"
匹配过程：
  1. 提取线索：公司=腾讯
  2. 筛选活跃记录中 company 包含"腾讯" → 匹配到 001 和 002
  3. 多条匹配 → 反问
结果："你有腾讯的以下投递，请问是哪个？1. CSIG-IMA产品经理 2. WXG-后端开发"
```

### 示例 3：关键词匹配

```
记录：
  001 腾讯 CSIG IMA产品经理 [活跃]
  002 腾讯 WXG 后端开发 [活跃]

用户说："ima那个收到offer了"
匹配过程：
  1. 提取线索：关键词=ima
  2. 在所有字段中搜索"ima"（不区分大小写）
     - 001 的 position="IMA产品经理" → 匹配
     - 002 无匹配
  3. 恰好 1 条 → 直接操作
结果：更新 001，标记终态"通过"
```

### 示例 4：无匹配

```
记录：
  001 腾讯 CSIG IMA产品经理 [活跃]

用户说："百度那个笔试了"
匹配过程：
  1. 提取线索：公司=百度
  2. 筛选活跃记录 → 无匹配
  3. 0 条匹配 → 询问
结果："没找到百度的投递记录，是否需要新建？"
```

## 动态状态扩展示例

```
当前 status_types: ["投递", "笔试", "AI面试", "一面", "二面", "三面", "四面", "HR面", "Offer"]

用户说："腾讯那个要做个性格测试"
处理：
  1. "性格测试" 不在 status_types 中
  2. 将 "性格测试" 添加到 status_types
  3. status_types 变为: [..., "Offer", "性格测试"]
  4. 在匹配到的记录的 status_history 中追加 { status: "性格测试", date: "今天", note: "" }
  5. 更新 current_status 为 "性格测试"
```

## 终态处理示例

### 通过

```
用户说："腾讯那个发offer了"
处理：
  1. 匹配到记录
  2. end_result = "通过"
  3. is_active = false
  4. current_status 保持不变（如"HR面"）
  5. status_history 追加: { status: "Offer", date: "今天", note: "收到offer" }
  6. 表格中"终态"列显示"通过"
```

### 终止

```
用户说："腾讯那个二面没过"
处理：
  1. 匹配到记录
  2. end_result = "终止"
  3. is_active = false
  4. current_status 保持"二面"
  5. status_history 追加: { status: "二面", date: "今天", note: "二面未通过" }
  6. 表格中"终态"列显示"终止"
```
