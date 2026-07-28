# 信源清单（sources）

本 skill 默认采集以下硬核科技 / 商业媒体。脚本 `scripts/fetch_feeds.py` 已内置同样的列表，
可直接运行；如需增删信源，改脚本里的 `DEFAULT_SOURCES`，或运行时用 `--sources <json>` 传入自定义列表。

> 注：所有信源均经实测可达性验证。其中 `微信公众号镜像` 源（decemberpei.cyou 桥接）只能拿到
> 标题、且微信会拦截正文抓取，**仅作为无官方 feed 时的兜底**（如机器之心）。新智元 / APPSO 已改走
> 各自官方站点（WordPress API / 爱范儿作者过滤），详见下表。
>
> 容错：每个信源可配 `fallback` 候选地址；主地址失败（网络错误 / 返回网页而非 feed / 无条目）自动尝试下一个。
> 网络类错误仅对「真正的超时」重试 1 次，连接被拒/不可达等确定性错误立即失败，避免对死信源长时间空等。
> 单信源彻底失败不影响其他信源，失败原因分类汇总到输出 JSON 的 `errors` 字段。

## 默认信源

| 媒体 | 分类 | 类型 | 地址 / 说明 |
|------|------|------|------------|
| 新智元 | AI | WordPress API | `https://aiera.com.cn/wp-json/wp/v2/posts?per_page=20`（官网 REST 接口，直接返回完整正文） |
| 36氪 | 商业/创投 | 官网 RSS | `https://36kr.com/feed` |
| 量子位 | AI | 官网 RSS | `https://www.qbitai.com/feed` |
| APPSO | 消费科技 | 官网 RSS（作者过滤） | `https://www.ifanr.com/feed`，附加 `author: "APPSO"`（APPSO 是爱范儿旗下栏目，从主 feed 按 `dc:creator` 筛出） |
| 机器之心 | AI | 微信公众号镜像 | `https://decemberpei.cyou/rssbox/wechat-jiqizhixin.xml`（官方 `/rss` 已退化为 SPA 空壳页，故用微信镜像，**仅标题、无正文**，链接为 mp.weixin 需手动点开）；`fallback` 为 Synced 英文站 `https://syncedreview.com/feed/` |
| 爱范儿 | 消费科技 | 官网 RSS（作者排除） | `https://www.ifanr.com/feed`，附加 `author_exclude: ["APPSO"]`（避免与上方 APPSO 重复） |
| 少数派 | 效率/工具 | 官网 RSS | `https://sspai.com/feed` |
| 极客公园 | 科技 | 官网 RSS | `https://www.geekpark.net/rss`（本环境常连接超时/不可达，`fallback` 为 RSSHub 路由） |
| 虎嗅 | 商业 | 官网 RSS | `https://www.huxiu.com/rss/0.xml`（官方 RSS 常超时/被 WAF 拦截，`fallback` 为 RSSHub 路由） |

> ⚠️ **极客公园 / 虎嗅当前在默认运行环境（WorkBuddy 沙箱）不可达**：官网 RSS 连接超时或被阿里云 WAF
> 拦截、RSSHub 公共实例亦连不通。脚本会优雅降级（记录原因、不中断、不丢其他源数据）。若你在本机/其他网络
> 运行，这两家大概率可正常获取；如需在沙箱内也覆盖，可改用同类的**钛媒体 / 雷锋网**（见下方扩展表，已实测可达）。

> 爱范儿与 APPSO 共用 `https://www.ifanr.com/feed` 同一个 feed：爱范儿用 `author_exclude`
> 排除 APPSO，APPSO 用 `author` 只收 APPSO，二者分工互不重叠。

## 可扩展的同类信源（按需加入）

| 媒体 | 分类 | 地址 |
|------|------|------|
| 晚点 LatePost | 商业深度 | `https://decemberpei.cyou/rssbox/wechat-wandian.xml` |
| 甲子光年 | 科技产业 | `https://decemberpei.cyou/rssbox/wechat-jiaziguangnian.xml` |
| InfoQ（AI 前线） | 技术 | `https://decemberpei.cyou/rssbox/wechat-aiqianxian.xml` |
| 钛媒体 | 商业科技 | `https://www.tmtpost.com/rss.xml` |
| 雷锋网 | AI/硬件 | `https://www.leiphone.com/rss` |
| The Verge | 科技（英文） | `https://www.theverge.com/rss/index.xml` |
| TechCrunch | 创投（英文） | `https://techcrunch.com/feed` |

## 自定义信源 JSON 格式

传给 `--sources` 的文件应为对象数组，字段与 `DEFAULT_SOURCES` 一致：

```json
[
  {"name": "新智元", "url": "https://aiera.com.cn/wp-json/wp/v2/posts?per_page=20", "category": "AI", "type": "WordPress API"},
  {"name": "APPSO",  "url": "https://www.ifanr.com/feed", "category": "消费科技", "type": "官网RSS", "author": "APPSO"},
  {"name": "爱范儿", "url": "https://www.ifanr.com/feed", "category": "消费科技", "type": "官网RSS", "author_exclude": ["APPSO"]},
  {"name": "36氪",   "url": "https://36kr.com/feed", "category": "商业/创投", "type": "官网RSS"}
]
```

### 字段说明
- `type`：`官网RSS`（标准 RSS/Atom）、`WordPress API`（WP REST 接口，自动带 `content` 正文）、`微信公众号镜像`（仅标题，不推荐）。
- `author`：（仅 `官网RSS`）只保留 `dc:creator`/`<author>` 命中该字符串的文章，用于同一 feed 内按栏目拆分。
- `author_exclude`：（仅 `官网RSS`）排除以上的作者，避免重复。
- `fallback`：（可选）候选地址数组，主地址失败时依次尝试（用于信源抽风/被墙时自动切换）。
- `local`：离线测试时指向本地 xml/json 文件，脚本优先读本地。

离线测试时可为某条加 `"local": "C:/path/to/local.xml"`，脚本会优先读取本地文件而非联网。

## 新增信源步骤

1. 确认该媒体的 RSS/Atom 地址可访问（浏览器或 `curl` 打开应返回 XML）。
2. 将其加入脚本 `DEFAULT_SOURCES`（或独立 JSON 文件）。
3. 补上 `category`（用于周报分组）与 `type`（备注）。
4. 跑一次 `fetch_feeds.py --sources <json> --output test.json` 验证条目正常解析。
