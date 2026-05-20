# 🌿 智能阳台 MCP 部署说明

## 文件结构

```
/home/pi/python/
├── main.py              # 原主程序（保留）
├── mcp_server.py        # MCP 服务器（新增）
├── cmd_controller.py    # 命令控制器（新增）
├── start.sh             # 启动脚本（新增）
└── README.md            # 本说明文档
```

## MCP 工具列表

| 工具名 | 功能 | 参数 |
|--------|------|------|
| `get_environment_data` | 获取环境数据 | 无 |
| `turn_on_light` | 开灯 | 无 |
| `turn_off_light` | 关灯 | 无 |
| `water_plant` | 浇水 | duration: int (秒) |
| `open_window` | 开窗 | 无 |
| `close_window` | 关窗 | 无 |
| `get_health_index` | 获取健康指数 | 无 |
| `get_system_status` | 获取系统状态 | 无 |

## 启动方式

### 方式 1: 一键启动（推荐）
```bash
cd /home/pi/python
./start.sh
```

### 方式 2: 手动启动
```bash
# 启动 MCP 服务
cd /home/pi/python
python3 mcp_server.py &

# 启动主程序（如需）
python3 main.py &
```

## 状态同步

- 状态文件: `/tmp/balcony_status.json`
- 命令文件: `/tmp/balcony_cmd.txt`
- MCP 服务和 main.py 通过这两个文件同步状态

## nanobot 配置

MCP 服务器已配置在 `~/.nanobot/config.json`:
```json
{
  "tools": {
    "mcp_servers": {
      "balcony": {
        "url": "http://127.0.0.1:8000/mcp/jsonrpc"
      }
    }
  }
}
```

## 使用示例

### 通过自然语言控制
- "开灯" → 调用 turn_on_light
- "关灯" → 调用 turn_off_light
- "浇水" → 调用 water_plant(5)
- "开窗" → 调用 open_window
- "关窗" → 调用 close_window
- "查看阳台情况" → 返回 OLED 风格三栏布局

### 通过命令控制
```bash
# 测试 MCP 服务
curl -X POST http://127.0.0.1:8000/mcp/jsonrpc \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"tools/call","tool":"get_system_status","id":1}'
```

## 日志文件

- MCP 服务: `/tmp/mcp.log`
- 主程序: `/tmp/balcony_main.log`