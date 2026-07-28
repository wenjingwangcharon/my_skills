# 目录结构说明（STRUCTURE）

本仓库 `my_skills` 是个人原创 WorkBuddy skills 的集合，每个 skill 是独立子目录。

## 顶层布局

```
my_skills/
├── README.md            # 仓库概览 + 全部 skills 速查表
├── SKILLS.md            # 对外分享清单（功能点 + 下载链接）
├── STRUCTURE.md         # 本文件：目录结构说明
├── .gitignore           # 忽略 OS / Python / Node 缓存与密钥等
├── <skill-a>/           # 每个 skill 一个目录
├── <skill-b>/
└── ...
```

## 单个 skill 目录的典型结构

并非每个 skill 都包含下面全部子目录，按需存在：

```
<skill-name>/
├── SKILL.md             # 必需：skill 的元数据与触发说明（name / description / agent_created 等）
├── scripts/             # 可选：可执行脚本（Python / Node）
├── references/          # 可选：提示词、工作流、数据源等参考文档
├── assets/              # 可选：模板、图片、示例资源
└── _meta.json / _skillhub_meta.json  # 可选：市场元数据
```

- `SKILL.md` 是**必需**文件，WorkBuddy 据此识别并加载 skill。
- `description` 字段决定 skill 的触发条件（用户说什么话会唤醒它）。
- `agent_created: true` 表示由本工作区原创生成。
- `disable: true` 表示该 skill 暂时停用，导入后不自动生效。

## 如何使用 / 安装某个 skill

1. 克隆或下载本仓库：
   ```bash
   git clone https://github.com/wenjingwangcharon/my_skills.git
   ```
2. 把目标 skill 文件夹整体复制到本机 skills 目录：
   - macOS / Linux：`~/.workbuddy/skills/<skill-name>`
   - Windows：`C:\Users\<用户名>\.workbuddy\skills\<skill-name>`
3. 重启或新建对话，按 skill 的触发词即可使用。

## 注意事项

- 单个 skill 没有独立 zip 下载，需整仓 clone 后取对应文件夹。
- 部分 skill 运行时依赖外部账号 / API（QQ 邮箱、飞书、小红书 cookie、腾讯灯塔、腾讯问卷等），首次使用需自行配置凭据；仓库内只保留 `*.example.*` 示例配置，不会提交真实密钥（见 `.gitignore`）。
- 停用的 skill（`disable: true`）如需启用，把 `SKILL.md` 中的 `disable: true` 改为 `false` 即可。
