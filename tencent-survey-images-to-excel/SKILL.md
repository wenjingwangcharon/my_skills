---
name: tencent-survey-images-to-excel
description: Turn Tencent Survey (腾讯问卷/wj.qq.com) raw exported data into a clean, review-ready Excel where uploaded images are embedded as visible thumbnails, useless columns are removed, and (optionally) each submission's published content is fetched from its link and scored. Use when a user gives survey-exported CSV/data and wants a tidy table like 运营活动-投稿数据(含图片).xlsx. Two stages: (1) clean fields + embed images, (2) visit each content link and append content-quality / case-representativeness scoring columns. Key insight: CSV image download links (=Hyperlink to wj.qq.com/api/files/download) require login; use the tencent-survey MCP list_answers tool to get signed COS direct URLs that download without auth.
description_zh: 问卷原始数据整理成含图片+评分的Excel
description_en: Survey raw data to images+scoring Excel
disable: false
agent_created: true
---

# tencent-survey-images-to-excel

把腾讯问卷导出的**原始数据**整理成一张**方便核查的成品表**（含内嵌图片，可选附内容评分）。典型成品：`运营活动-投稿数据(含图片).xlsx`。

## When to use
- 用户给问卷(wj.qq.com)导出的 CSV/数据，想要一张整理好的表：删无用字段、图片以**图片形式**内嵌、字段顺序清晰。
- 进一步（运营评审场景）：需要**访问每条投稿的内容链接，按规则打分**，并把评分列追加到含图片的数据表后面，方便对照图片核查。

## 整体流程（两阶段）

### 阶段一：清洗字段 + 嵌入图片 → 成品表
1. **读 CSV 确认结构**：用 Read 看表头与列含义。问卷导出常见无用列：开始答题时间、答题时长、语言、清洗数据结果、智能清洗数据无效概率、地理位置国家地区、用户类型、用户标识、自定义字段、IP、UA、Referrer、末尾空列。和用户确认保留/删除哪些（尤其时间列——常只保留"结束答题时间"用于参与奖排序）。
2. **不要直接下载 CSV 里的 download 链接**：`wj.qq.com/api/files/download?...` 需登录鉴权，匿名 GET 返回登录页 HTML（典型特征：固定大小约16654字节、`<title>登录 - 腾讯问卷</title>`）。
3. **改用 MCP 取签名直链**：从 download 链接里取 `survey_id=`。调用 `mcp__tencent-survey__list_answers(survey_id, per_page=1000)`。返回的每条答卷 `answer[].questions[].files[].url` 是带签名的腾讯云 COS 直链（`...myqcloud.com/...?q-sign-algorithm=sha1&q-ak=...&q-sign-time=...&q-signature=...`），**可免登录直接下载，签名约7天有效**。upload 题型 type=="upload"。把 MCP 数据整理成 `final_records.json`（见脚本约定格式）。
4. **下载图片**：urllib 直接 GET COS url，下载后校验头部不是 HTML（`<!doctype`/`<html`/`<title>`）。保存到临时目录。
5. **压缩图片**（强烈建议）：原始截图分辨率高，直接嵌入会让 xlsx 达 20MB+。用 Pillow 缩放到最大边 ~800px、JPEG quality~78，可降到 1-2MB。
6. **生成 Excel**：用 openpyxl，按确认后的精简字段建表头。图片用 `openpyxl.drawing.image.Image` + `OneCellAnchor`(AnchorMarker + XDRPositiveSize2D + pixels_to_EMU) 精确定位，**同一格多张图用 rowOff 纵向堆叠**。按图片总高度设置 `row_dimensions[r].height`（px×0.75 转 points）。
7. 保存到工作区根目录，用 present_files 展示。参考脚本：@scripts/build_and_excel.py。

### 阶段二（可选）：访问内容链接 + 评分 → 追加到同一张表
当用户提供评分标准（如内容质量、案例代表性维度），对每条投稿打分：
1. **逐条访问内容链接**取正文：
   - 微信公众号 `mp.weixin.qq.com/s/...`：用 **WebFetch**（curl 拿不到正文，标题常为空）。
   - 知乎、豆瓣 topic：WebFetch 一般可取到。
   - 小红书 `xhslink.com` 短链：curl 多 404，浏览器(agent-browser)访问常被风控（`error_code=300012 IP存在风险`），多数**不可访问**。
   - 临时链接（`mp.weixin.qq.com/s?__biz=...` 不带 `/s/<id>`）：常返回"参数错误"，**不可访问**。
   - ima知识库/纯文字描述：无有效 URL，**不可访问**。
2. **打分规则**：按用户给的细则逐项打分（如完整度/清晰度/实操性 → 内容质量综合分；场景创新性/示范价值/共鸣度 → 案例代表性综合分；综合分=三项均值，保留2位小数）。**链接不可访问的不打分**，状态列标注原因，评分单元格留空并标浅红底色(`FFE0E0`)。
3. **追加列到含图片的表**（用户偏好：不要单独出评分文件）：
   - 用 `openpyxl.load_workbook` 打开阶段一成品表（图片会保留），从 `ws.max_column+1` 起追加评分列。
   - 按 A 列"编号"逐行匹配评分字典，写入。表头用与原表一致的样式（深色填充+白字+边框+居中换行）。
   - 参考脚本：@scripts/append_scores.py。
4. 保存（覆盖原表），present_files 展示。**删除任何单独的评分临时表**。

## Pitfalls
- MCP 返回的 list_answers 可能比 CSV 多/少记录（CSV 可能是旧导出）。以 MCP 数据为准更完整（曾出现 MCP 12条 vs CSV 11条）。
- 每次调用 list_answers 的签名 q-sign-time 会变，URL 不可长期缓存；用完即下。
- file_name_dst 可重复（同名上传），用 `编号_home/content_序号` 命名避免覆盖。
- UID 字段常含整段设备串(QIMEI/uid/iua)，按需提炼出 `UID:xxx` 主体。
- venv 安装：`~/.workbuddy/binaries/python/envs/default/bin/pip install openpyxl Pillow`。
- 追加评分列时务必用 load_workbook 打开**已含图片的成品表**再追加，不要新建工作簿，否则丢图片。
- 公众号正文必须用 WebFetch；curl/agent-browser 拿不到（反爬，title 为空）。
- 小红书短链在服务器环境基本拿不到内容，直接判"不可访问"并请运营让投稿者补发，别耗时重试。
- **链接清洗不要用 `re.sub(r'^.*?\n', '', val)`**：XLSX 导出中链接常与中文广告语混在同一行（如 `Ima 的copilot真好用 http://xhslink.com/o/xxx \n复制后打开...`），此正则会整行删除。正确做法：只删除明确的"这是我本人\n"前缀，其余原样保留。URL 可由审核员从混合文本中自行提取。若确实需要提取纯 URL，用 `re.findall(r'https?://\S+', val)` 取所有链接，但仍建议保留原始文本做辅助参考。

## Verification
- `unzip -l xxx.xlsx | grep media | wc -l` 应等于成功下载的图片数。
- 抽样 `file` 检查下载文件确为 PNG/JPEG 而非 HTML。
- 追加评分后 `len(ws._images)` 应仍等于原图片数（确认没丢图）。
- 打开 xlsx 确认图片在对应单元格内可见、行高足够；评分列在图片列之后。
