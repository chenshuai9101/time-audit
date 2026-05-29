#!/bin/bash
# 时间审计 v2 — 一键安装脚本

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
echo "📦 时间审计 v2 安装中..."
echo "   位置: $SCRIPT_DIR"

if ! command -v python3 &> /dev/null; then
    echo "❌ 需要 Python 3.8+"
    exit 1
fi

echo ""
echo "📚 安装 Python 依赖..."
pip3 install -e "$SCRIPT_DIR" --quiet 2>/dev/null || pip3 install -e "$SCRIPT_DIR" --quiet --user

mkdir -p "$SCRIPT_DIR/reports"

echo ""
echo "🔍 检查本地 Ollama..."
if command -v ollama &> /dev/null; then
    echo "   ✅ ollama 已安装"
    if curl -fs http://localhost:11434/api/tags > /dev/null 2>&1; then
        echo "   ✅ ollama 正在运行"
    else
        echo "   ⚠️  ollama 未启动，运行：ollama serve"
    fi
else
    echo "   ⚠️  未安装 ollama。建议："
    echo "      brew install ollama"
    echo "      ollama serve &"
    echo "      ollama pull qwen2.5:14b"
fi

echo ""
echo "🧪 跑一次 dry-run（不调用 LLM，使用模拟数据）..."
cd "$SCRIPT_DIR"
python3 -m time_audit --dryrun --days 3 || true

echo ""
echo "✅ 安装完成！"
echo ""
echo "常用命令："
echo "  python3 -m time_audit             # 完整分析（需要 Ollama）"
echo "  python3 -m time_audit --dryrun    # 跳过 LLM，仅做事件压缩"
echo "  python3 -m time_audit --check-llm # 探活 Ollama"
echo "  python3 -m time_audit --report    # 查看最新一份报告"
echo "  python3 -m time_audit --days 7    # 指定分析天数"
