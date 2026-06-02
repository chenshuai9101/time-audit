#!/bin/bash
# 把 Screenpipe 装成 macOS 开机自启 LaunchAgent
# 用法：./install.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLIST_SRC="$SCRIPT_DIR/com.screenpipe.recorder.plist"
PLIST_DST="$HOME/Library/LaunchAgents/com.screenpipe.recorder.plist"
BIN_PATH="/opt/homebrew/bin/screenpipe"

echo "📦 Screenpipe LaunchAgent 安装"
echo ""

# 1. 前置检查
if [ ! -f "$BIN_PATH" ]; then
    echo "❌ 找不到 screenpipe 二进制：$BIN_PATH"
    echo "   先安装："
    echo "   npm i -g @screenpipe/cli-darwin-arm64@0.3.282"
    echo "   （注意：直接装 \`screenpipe\` 主包会因 npm optionalDependencies 版本不同步而失败）"
    exit 1
fi

if [ ! -f "$PLIST_SRC" ]; then
    echo "❌ 模板缺失：$PLIST_SRC"
    exit 1
fi

mkdir -p "$HOME/Library/LaunchAgents" "$HOME/Library/Logs"

# 2. 替换占位符
echo "📝 写入 plist：$PLIST_DST"
sed "s|__USER_HOME__|$HOME|g" "$PLIST_SRC" > "$PLIST_DST"
plutil -lint "$PLIST_DST" > /dev/null

# 3. 卸掉旧 job（如有）
if launchctl list | grep -q "com.screenpipe.recorder"; then
    echo "🔄 卸载旧 LaunchAgent..."
    launchctl bootout "gui/$(id -u)/com.screenpipe.recorder" 2>/dev/null || true
fi

# 4. 加载
echo "🚀 加载 LaunchAgent..."
launchctl bootstrap "gui/$(id -u)" "$PLIST_DST"

# 5. 验证
sleep 5
if launchctl list | grep -q "com.screenpipe.recorder"; then
    echo "✅ 已加载并运行"
else
    echo "⚠️  加载后未在 launchctl list 找到 — 检查日志"
fi

# 6. TCC 权限提示
REAL_BIN="$(readlink -f "$BIN_PATH")"
echo ""
echo "─────────────────────────────────────────────────────"
echo "⚠️  Screen Recording 权限需要手动授权"
echo ""
echo "macOS TCC 不会自动从 Terminal 继承权限给 launchd 进程。"
echo "你需要："
echo ""
echo "  1. 打开 系统设置 → 隐私与安全性 → 屏幕录制"
echo "  2. 点 + 加入这个二进制（按 ⌘⇧G 粘贴目录）："
echo ""
echo "     $REAL_BIN"
echo ""
echo "  3. 打开它对应的开关"
echo "  4. 重启 LaunchAgent："
echo ""
echo "     launchctl kickstart -k gui/\$(id -u)/com.screenpipe.recorder"
echo ""
echo "─────────────────────────────────────────────────────"
echo ""
echo "管理命令："
echo "  launchctl list | grep screenpipe                            # 看运行状态"
echo "  launchctl kickstart -k gui/\$(id -u)/com.screenpipe.recorder # 重启"
echo "  launchctl bootout gui/\$(id -u)/com.screenpipe.recorder      # 停止"
echo "  tail -f $HOME/Library/Logs/screenpipe.err.log               # 跟日志"
echo ""
