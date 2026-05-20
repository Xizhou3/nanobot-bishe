#!/usr/bin/env python3
"""阳台设备状态变化通知脚本"""
import time
import re
import sys

LOG_FILE = "/tmp/mcp.log"
NOTIFY_FILE = "/tmp/balcony_notify.txt"
LAST_POS = 0
LAST_NOTIFY_POS = 0

# 设备变化匹配模式
PATTERNS = [
    r"💡 智能灯控：.*",
    r"🌙 智能灯控：.*", 
    r"🪟 智能控窗：.*",
    r"💦 智能灌溉：.*",
    r"🌱 土壤干燥.*",
    r"🌧️.*关窗",
    r"☀️.*开窗",
]

def send_message(content):
    """发送消息到用户 - 写入通知文件"""
    try:
        with open(NOTIFY_FILE, "a") as f:
            f.write(content + "\n")
        print(f"已记录通知: {content}")
    except Exception as e:
        print(f"记录消息失败: {e}")

def check_log():
    """检查日志文件变化"""
    global LAST_POS
    try:
        with open(LOG_FILE, "r") as f:
            f.seek(LAST_POS)
            new_lines = f.readlines()
            LAST_POS = f.tell()
            
            for line in new_lines:
                for pattern in PATTERNS:
                    if re.search(pattern, line):
                        msg = line.strip()
                        if msg:
                            send_message(msg)
                            break
    except Exception as e:
        print(f"检查日志失败: {e}")

def read_new_notifications():
    """读取新的通知（用于用户查询时显示）"""
    global LAST_NOTIFY_POS
    try:
        with open(NOTIFY_FILE, "r") as f:
            f.seek(0, 2)
            file_size = f.tell()
            
            if file_size > LAST_NOTIFY_POS:
                f.seek(LAST_NOTIFY_POS)
                new_notifications = f.readlines()
                LAST_NOTIFY_POS = file_size
                return [n.strip() for n in new_notifications if n.strip()]
            return []
    except:
        return []

def check_and_show_notifications():
    """检查并显示新通知"""
    new_notifs = read_new_notifications()
    if new_notifs:
        print("\n" + "="*40)
        print("📢 设备状态变化通知:")
        for n in new_notifs:
            print(f"  {n}")
        print("="*40 + "\n")

if __name__ == "__main__":
    # 如果带参数 --check，表示检查新通知
    if len(sys.argv) > 1 and sys.argv[1] == "--check":
        check_and_show_notifications()
    else:
        print("🌿 阳台设备状态通知已启动...")
        
        try:
            with open(LOG_FILE, "r") as f:
                f.seek(0, 2)
                LAST_POS = f.tell()
        except:
            pass
        
        while True:
            check_log()
            time.sleep(2)