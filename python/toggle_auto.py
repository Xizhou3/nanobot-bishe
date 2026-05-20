#!/usr/bin/env python3
"""切换自动/手动控制模式"""
import sys

FLAG_FILE = "/tmp/auto_control.flag"

if len(sys.argv) < 2:
    print("用法: toggle_auto.py on|off|status")
    sys.exit(1)

cmd = sys.argv[1].lower()

if cmd == "on":
    with open(FLAG_FILE, "w") as f:
        f.write("auto")
    print("✅ 已切换到自动控制模式")
elif cmd == "off":
    with open(FLAG_FILE, "w") as f:
        f.write("manual")
    print("✅ 已切换到手动控制模式")
elif cmd == "status":
    try:
        with open(FLAG_FILE, "r") as f:
            mode = f.read().strip()
        print(f"当前模式: {mode}")
    except FileNotFoundError:
        print("auto")
else:
    print("未知命令")