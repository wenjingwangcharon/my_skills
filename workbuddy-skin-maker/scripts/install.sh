#!/bin/bash
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
THEME_DIR="${1:-$(pwd)}"

if [ ! -f "$THEME_DIR/theme/skin.css" ]; then
  echo "错误: 找不到 $THEME_DIR/theme/skin.css"
  echo "用法: $0 <theme-project-dir>"
  echo "theme-project-dir 应包含 theme/ 子目录，theme/ 下含 skin.css 和图片资源"
  exit 1
fi

SKIN_NAME=$(basename "$THEME_DIR")
BACKUP_DIR="$HOME/.workbuddy/backups/$SKIN_NAME/$(date -u +%Y-%m-%dT%H-%M-%S.%3NZ)"
ASAR_PATH="/Applications/WorkBuddy.app/Contents/Resources/app.asar"
THEME_ASAR="$THEME_DIR/theme.asar"

echo "=== 打包 theme.asar ==="
cd "$THEME_DIR"
npx asar pack theme/ "$THEME_ASAR"
echo "theme.asar 已生成: $(wc -c < "$THEME_ASAR" | tr -d ' ') bytes"

echo "=== 备份原 app.asar ==="
mkdir -p "$BACKUP_DIR"
cp "$ASAR_PATH" "$BACKUP_DIR/app.asar"
echo "备份到: $BACKUP_DIR/app.asar"

echo "=== 应用皮肤 ==="
node -e "
const fs = require('fs');
const path = require('path');
const src = path.resolve('$ASAR_PATH');
const theme = path.resolve('$THEME_ASAR');

const appJson = JSON.parse(fs.readFileSync(src, 'utf8'));
appJson.files['theme.asar'] = {
  offset: '0',
  size: fs.statSync(theme).size
};
fs.writeFileSync(src, JSON.stringify(appJson));
console.log('app.asar JSON 已更新');
"

echo ""
echo "=== 安装完成 ==="
echo "请用 Command + Q 完全退出 WorkBuddy，再重新打开。"
