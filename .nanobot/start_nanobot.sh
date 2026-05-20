#!/bin/bash
# 启动 MCP 服务 + nanobot

# 杀掉旧的进程
pkill -f "main_mcp.py" 2>/dev/null
pkill -f "nanobot agent" 2>/dev/null
sleep 1

# 启动 MCP 服务
cd /home/pi/python
nohup /home/pi/venv/bin/python -u main_mcp.py > /tmp/mcp.log 2>&1 &

# 等待 MCP 服务启动（最多10秒）
echo "等待 MCP 服务启动..."
for i in {1..10}; do
    if curl -s http://localhost:8000/jsonrpc > /dev/null 2>&1; then
        echo "✅ MCP 服务已启动"
        break
    fi
    sleep 1
done

echo ""
echo "========================================"
echo "🌿 智能阳台监控管家 已启动！"
echo "========================================"
echo ""
echo "你好！我是你的智能阳台监控管家 🌿"
echo ""
echo "我可以帮你："
echo "  📊 查看阳台实时状态"
echo "  💧 控制灌溉系统"
echo "  💡 控制智能灯光"
echo "  🪟 控制窗户开关"
echo "  🌤️ 查看天气预报"
echo ""
echo "请说「查看阳台情况」获取详细信息"
echo "========================================"
echo ""

# 启动 nanobot
exec /home/pi/venv/bin/nanobot agent
