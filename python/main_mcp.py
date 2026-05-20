import time
import board
import busio
from PIL import Image, ImageDraw, ImageFont
import adafruit_ssd1306
import RPi.GPIO as GPIO
import adafruit_dht
import threading
import json
from http.server import HTTPServer, BaseHTTPRequestHandler
import os
import urllib.request
import ssl
import urllib.parse

# --- 设备状态变化通知函数 ---
def notify_device_change(device: str, status: str, reason: str):
    """发送设备状态变化通知到通知服务"""
    try:
        data = json.dumps({
            "device": device,
            "status": status,
            "reason": reason
        }).encode()
        req = urllib.request.Request(
            "http://127.0.0.1:8081/notify",
            data=data,
            headers={'Content-Type': 'application/json'}
        )
        urllib.request.urlopen(req, timeout=5)
    except Exception as e:
        print(f"通知发送失败: {e}")

# --- GPIO 设置 ---
GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)

# --- 引脚定义 ---
servo_pin = 18      # 舵机 - 控制灯光开关
pir_pin = 13        # 人体红外传感器 - 检测人体
light_pin = 22      # 光敏传感器 - 检测环境亮度
relay_pin = 7       # 继电器 - 控制水泵灌溉
soil_do_pin = 25    # 土壤湿度传感器 - 检测土壤干湿
window_motor_ia = 23 # 电机INA - 正转打开窗户
window_motor_ib = 24 # 电机INB - 关闭打开窗户

# --- 传感器初始化 ---
dht_sensor = adafruit_dht.DHT11(board.D17, use_pulseio=False)

# --- GPIO 初始化 ---
GPIO.setup(pir_pin, GPIO.IN)
GPIO.setup(light_pin, GPIO.IN)
GPIO.setup(servo_pin, GPIO.OUT)
GPIO.setup(soil_do_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(relay_pin, GPIO.OUT, initial=GPIO.HIGH) 
# 初始化电机引脚
GPIO.setup(window_motor_ia, GPIO.OUT, initial=GPIO.LOW)
GPIO.setup(window_motor_ib, GPIO.OUT, initial=GPIO.LOW)

# --- 舵机设置 ---
servo_pwm = GPIO.PWM(servo_pin, 50)
servo_pwm.start(0)

# === 🎯 角度配置 ===
init_angle = 47    # 舵机初始位置角度
open_angle = 5     # 舵机开灯位置角度  
close_angle = 90   # 舵机关灯位置角度

def set_angle(angle):
    """
    控制舵机转动到指定角度
    :param angle: 目标角度 (0-180度)
    """
    angle = max(0, min(180, angle))  # 限制角度在0-180范围内
    duty = 2.5 + (angle / 18.0)      # 将角度转换为占空比
    servo_pwm.ChangeDutyCycle(duty)  # 设置PWM占空比
    time.sleep(0.12)                 # 等待舵机到达目标位置
    servo_pwm.ChangeDutyCycle(0)     # 停止PWM信号保持位置

# 初始归位
set_angle(init_angle)

# --- OLED 初始化 ---
i2c = busio.I2C(board.SCL, board.SDA)
oled = adafruit_ssd1306.SSD1306_I2C(128, 64, i2c, addr=0x3C)
oled.fill(0)
oled.show()

image = Image.new("1", (128, 64))
draw = ImageDraw.Draw(image)

try:
    large_font = ImageFont.truetype("/usr/share/fonts/truetype/wqy/wqy-microhei.ttc", 12)
    small_font = ImageFont.truetype("/usr/share/fonts/truetype/wqy/wqy-microhei.ttc", 10)
except:
    # 如果找不到中文字体，使用默认字体
    large_font = ImageFont.load_default()
    small_font = ImageFont.load_default()

# === 💡 变量状态 ===
lamp_state = False                        # 记录灯光开关状态
window_actual_state = "closed"           # 记录窗户实际开关状态
last_window_action_time = 0              # 记录上次窗户操作时间，防抖
window_action_in_progress = False        # 标记窗户操作是否正在进行

# === 电机动作函数===
def move_window(action):
    """
    控制窗户电机开关窗户
    :param action: "open" 或 "close"
    """
    global window_actual_state, window_action_in_progress
    if window_action_in_progress:
        return  # 如果正在操作中，则不执行新的操作
    
    window_action_in_progress = True
    
    if action == "open":
        # 电机正转 - 开窗
        GPIO.output(window_motor_ia, GPIO.HIGH)  # IA引脚高电平
        GPIO.output(window_motor_ib, GPIO.LOW)   # IB引脚低电平
        time.sleep(3)                            # 开窗需要3秒
        window_actual_state = "opened"           # 更新窗户状态
        print("◪  智能控窗：开窗")
    elif action == "close":
        # 电机反转 - 关窗
        GPIO.output(window_motor_ia, GPIO.LOW)   # IA引脚低电平
        GPIO.output(window_motor_ib, GPIO.HIGH)  # IB引脚高电平
        time.sleep(3)                            # 关窗需要3秒
        window_actual_state = "closed"           # 更新窗户状态
        print("■  智能控窗：关窗")
    
    # 停止电机 - 将两个引脚都设为低电平
    GPIO.output(window_motor_ia, GPIO.LOW)
    GPIO.output(window_motor_ib, GPIO.LOW)
    window_action_in_progress = False

def press_open():
    """控制舵机开灯"""
    global lamp_state
    set_angle(open_angle)      # 转动舵机到开灯位置
    time.sleep(0.1)            # 短暂延时确保动作完成
    set_angle(init_angle)      # 回到初始位置
    lamp_state = True          # 更新灯光状态
    print("💡 智能灯控：开灯")

def press_close():
    """控制舵机关灯"""
    global lamp_state
    set_angle(close_angle)     # 转动舵机到关灯位置
    time.sleep(0.1)            # 短暂延时确保动作完成
    set_angle(init_angle)      # 回到初始位置
    lamp_state = False         # 更新灯光状态
    print("🌙 智能灯控：关灯")

# === 状态记忆 ===
last_light_state = None      # 记录上次光敏传感器状态
last_pir_time = 0            # 记录上次检测到人体的时间
last_action_time = 0         # 记录上次灯控动作时间

def is_person():
    """
    检测是否有人
    :return: True/False
    """
    global last_pir_time
    if GPIO.input(pir_pin) == 1:  # 如果检测到人体
        last_pir_time = time.time()  # 更新检测时间
    return (time.time() - last_pir_time) < 3.0  # 3秒内检测到人为有人

def is_dark():
    """
    检测环境是否昏暗
    :return: True/False
    """
    return GPIO.input(light_pin) == 1  # 光敏传感器检测到昏暗返回True

# === 温湿度缓存 ===
temp_val, hum_val = "--", "--"  # 温湿度显示值
last_dht_read = 0               # 上次读取DHT传感器时间

def update_dht(force_update=False): # 添加 force_update 参数
    """
    更新温湿度数据，带缓存机制防止频繁读取
    :param force_update: 如果为 True，则强制更新，忽略缓存时间间隔
    """
    global temp_val, hum_val, last_dht_read
    current_time = time.time()
    # 如果强制更新，或者距离上次读取已超过2秒，则执行更新
    if force_update or (current_time - last_dht_read > 2.0):
        try:
            t = dht_sensor.temperature  # 读取温度
            h = dht_sensor.humidity     # 读取湿度
            if t is not None and h is not None:
                # 温度修正：减去11度 (传感器校准)
                corrected_t = t - 5
                # 湿度修正：加上20度 (传感器校准)
                corrected_h = h + 2
                temp_val, hum_val = f"{corrected_t:.1f}", f"{corrected_h:.1f}"  # 保留一位小数
                last_dht_read = current_time # 只有在成功更新后才更新时间戳
            else:
                # 读取失败时不更新 temp_val, hum_val，保持原值
                pass
        except RuntimeError:
            # 读取失败时不更新 temp_val, hum_val，保持原值
            pass

def calculate_health_index(air_temp, air_humidity, soil_moisture_digital):
    """
    计算盆栽健康指数
    :param air_temp: 空气温度 (原始值)
    :param air_humidity: 空气湿度 (原始值) 
    :param soil_moisture_digital: 土壤湿度数字值 (HIGH/LOW)
    :return: 健康指数百分比 (0-100)
    """
    # 实际温度
    corrected_air_temp = air_temp - 8  # 应用温度修正，这是真正代表实际环境的温度
    
    # 湿度值
    corrected_air_humidity = air_humidity  # 应用湿度修正
    
    # 理想范围（基于实际温度和湿度）
    ideal_air_temp_min, ideal_air_temp_max = 15, 25  # 理想温度范围15-25°C
    ideal_air_humid_min, ideal_air_humid_max = 40, 70  # 理想湿度范围40-70%
    
    # 温度得分计算（基于实际温度）
    avg_ideal_temp = (ideal_air_temp_min + ideal_air_temp_max) / 2  # 平均理想温度20°C
    temp_score = max(0, 100 - abs(corrected_air_temp - avg_ideal_temp) * 8)  # 距离理想温度越远得分越低
    
    # 湿度得分计算（基于实际湿度）
    avg_ideal_humid = (ideal_air_humid_min + ideal_air_humid_max) / 2  # 平均理想湿度55%
    humid_score = max(0, 100 - abs(corrected_air_humidity - avg_ideal_humid) * 1.5)  # 距离理想湿度越远得分越低
    
    # 土壤湿度得分
    if soil_moisture_digital == GPIO.LOW:  # 土壤湿润
        soil_score = 85  # 湿润状态得分较高
    else:  # 土壤干燥
        soil_score = 20  # 干燥状态得分较低
    
    # 加权平均计算健康指数 - 调整土壤湿度权重为0.6
    health_index = (temp_score * 0.2 + humid_score * 0.2 + soil_score * 0.6)
    return min(100, int(health_index))

def read_soil_moisture():
    """
    读取土壤湿度传感器状态
    :return: GPIO.HIGH/LOW
    """
    return GPIO.input(soil_do_pin)

def control_irrigation(soil_dry, current_time):
    """
    控制智能灌溉系统
    :param soil_dry: 土壤是否干燥 (True/False)
    :param current_time: 当前时间
    :return: (状态消息, 是否在灌溉中)
    """
    global last_irrigation_start_time, irrigation_in_progress
    if soil_dry and not irrigation_in_progress:
        # 土壤干燥且未在灌溉中，开始灌溉
        GPIO.output(relay_pin, GPIO.LOW)  # 打开水泵
        irrigation_in_progress = True
        last_irrigation_start_time = current_time
        print("💧 智能灌溉：水泵开启")
        notify_device_change("💧 智能灌溉", "水泵开启", "土壤干燥")
        return "已开始浇水", True
    elif irrigation_in_progress:
        # 正在灌溉中，检查是否需要停止
        elapsed_time = current_time - last_irrigation_start_time
        if not soil_dry or elapsed_time >= 30:  # 土壤不再干燥或灌溉超过30秒
            GPIO.output(relay_pin, GPIO.HIGH)  # 关闭水泵
            irrigation_in_progress = False
            print("🌱 智能灌溉：水泵关闭")
            notify_device_change("🌱 智能灌溉", "水泵关闭", "土壤已湿润或灌溉完成")
            return "已浇过水", False
        else:
            # 继续灌溉，返回剩余时间
            remaining_time = int(30 - elapsed_time)
            return f"浇水...({remaining_time}s)", True
    else:
        # 不需要灌溉
        return "无需浇水", False

irrigation_in_progress = False
last_irrigation_start_time = 0
irrigation_status_message = "系统启动"

# === 厦门4月天气模拟逻辑 ===
def simulate_rain_condition(temperature, humidity):
    """
    根据温度和湿度模拟厦门4月的雨天情况
    :param temperature: 温度值 (原始)
    :param humidity: 湿度值 (原始)
    :return: (天气类型, 是否应关窗)
    """
    # 使用修正后的温度和湿度值
    corrected_temperature = temperature - 8  # 应用温度修正
    corrected_humidity = humidity      # 应用湿度修正
    
    # 厦门4月平均温度约20-28°C，湿度较高
    # 当湿度超过75%且温度在22-26°C之间时，认为可能是雨天
    if corrected_humidity > 75 and 22 <= corrected_temperature <= 26:
        return "雨天", True  # 返回天气类型和是否应关窗
    elif corrected_humidity > 80:
        return "高湿", True  # 湿度过高也应关窗防潮
    elif corrected_temperature > 28:  # 温度过高时开窗通风
        return "热天", False
    elif corrected_temperature < 20:  # 温度过低时关窗保温
        return "冷天", True
    else:
        return "正常", False

# 缓存天气预报数据（5分钟更新一次）
_weather_cache = {"data": None, "timestamp": 0}
WEATHER_CACHE_DURATION = 300  # 5分钟

def get_weather_forecast():
    """
    获取厦门天气预报
    :return: 天气预报字典
    """
    global _weather_cache

    # 检查缓存
    if _weather_cache["data"] and (time.time() - _weather_cache["timestamp"] < WEATHER_CACHE_DURATION):
        return _weather_cache["data"]

    try:
        # 绕过SSL验证
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        url = "https://wttr.in/Xiamen?format=j1"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})

        with urllib.request.urlopen(req, context=ctx, timeout=10) as response:
            data = json.loads(response.read().decode())

            # 解析今天和明天的天气
            today = data['weather'][0]
            tomorrow = data['weather'][1] if len(data['weather']) > 1 else today

            # 处理湿度（可能是字符串或列表）
            def parse_humidity(h):
                if isinstance(h, list):
                    return int(h[0]['value'])
                return int(h)

            weather_info = {
                "today": {
                    "condition": today['hourly'][0]['weatherDesc'][0]['value'],
                    "temp_min": int(today['mintempC']),
                    "temp_max": int(today['maxtempC']),
                    "humidity": parse_humidity(today['hourly'][0]['humidity']),
                },
                "tomorrow": {
                    "condition": tomorrow['hourly'][0]['weatherDesc'][0]['value'],
                    "temp_min": int(tomorrow['mintempC']),
                    "temp_max": int(tomorrow['maxtempC']),
                    "humidity": parse_humidity(tomorrow['hourly'][0]['humidity']),
                },
                "current": {
                    "temp": int(data['current_condition'][0]['temp_C']),
                    "humidity": int(data['current_condition'][0]['humidity']),
                    "condition": data['current_condition'][0]['weatherDesc'][0]['value'],
                }
            }

            # 缓存结果
            _weather_cache["data"] = weather_info
            _weather_cache["timestamp"] = time.time()

            print(f"📡 天气预报已更新: {weather_info['today']['condition']} {weather_info['today']['temp_min']}-{weather_info['today']['temp_max']}°C")
            return weather_info

    except Exception as e:
        print(f"❌ 获取天气预报失败: {e}")
        # 返回默认天气（晴朗）
        return {
            "today": {"condition": "Clear", "temp_min": 20, "temp_max": 25, "humidity": 60},
            "tomorrow": {"condition": "Clear", "temp_min": 20, "temp_max": 25, "humidity": 60},
            "current": {"condition": "Clear", "temp": 22, "humidity": 60}
        }

def should_open_window_by_weather(weather_info):
    """
    根据天气预报判断是否应该开窗
    :param weather_info: 天气预报字典
    :return: (should_open: bool, reason: str)
    """
    today = weather_info["today"]
    condition = today["condition"].lower()
    temp_min = today["temp_min"]
    temp_max = today["temp_max"]
    humidity = today["humidity"]

    # 判断天气类型
    rain_keywords = ["rain", "drizzle", "shower", "thunderstorm", "mist", "fog"]
    cloud_keywords = ["cloudy", "overcast", "partly"]
    clear_keywords = ["sunny", "clear"]

    is_rainy = any(kw in condition for kw in rain_keywords)
    is_cloudy = any(kw in condition for kw in cloud_keywords)
    is_clear = any(kw in condition for kw in clear_keywords)

    # 智能决策逻辑
    if is_rainy:
        return False, f"天气有雨({today['condition']})，建议关窗"
    elif humidity > 80:
        return False, f"湿度过高({humidity}%)，建议关窗"
    elif is_clear or is_cloudy:
        # 晴朗或多云时，根据温度判断
        if temp_max > 30:
            return True, f"天气晴好，温度较高({temp_min}-{temp_max}°C)，开窗通风"
        elif temp_min < 15:
            return False, f"温度较低({temp_min}-{temp_max}°C)，建议关窗保暖"
        else:
            return True, f"天气宜人({temp_min}-{temp_max}°C)，适合开窗通风"
    else:
        # 默认根据温度范围判断
        if 15 <= temp_max <= 30:
            return True, f"温度适宜({temp_min}-{temp_max}°C)，开窗通风"
        else:
            return False, f"温度异常({temp_min}-{temp_max}°C)，保持关窗"

def get_window_control_status(air_temp, air_humidity):
    """
    获取窗户控制状态并执行相应操作（基于天气预报智能决策）
    :param air_temp: 空气温度
    :param air_humidity: 空气湿度
    :return: 窗户控制状态字符串
    """
    global window_actual_state, last_window_action_time

    # 获取天气预报
    weather_info = get_weather_forecast()

    # 根据天气预报智能决策
    should_open, reason = should_open_window_by_weather(weather_info)

    # 防抖：至少间隔10秒才能再次操作窗户
    current_time = time.time()
    if current_time - last_window_action_time < 10:
        return f"{weather_info['today']['condition']}: {reason}"

    if window_action_in_progress:
        return f"{weather_info['today']['condition']}: 操作中..."

    # 执行控制
    if should_open:
        if window_actual_state == "closed":
            move_window("open")
            last_window_action_time = current_time
            print(f" 智能控窗: {reason}")
            notify_device_change(" 智能控窗", "已开窗", reason)
        return f"{weather_info['today']['condition']}(开) - {reason}"
    else:
        if window_actual_state == "opened":
            move_window("close")
            last_window_action_time = current_time
            print(f" 智能控窗: {reason}")
            notify_device_change(" 智能控窗", "已关窗", reason)
        return f"{weather_info['today']['condition']}(关) - {reason}"

# ==================== MCP 工具类 ====================
class MCPTools:
    """MCP 工具集合 - 调用 main.py 中已有的函数"""
    
    @staticmethod
    def get_environment_data():
        """获取环境数据"""
        update_dht(force_update=True) # 强制更新
        soil_moisture_digital = read_soil_moisture()
        return {
            "status": "ok",
            "data": {
                "temperature": temp_val,
                "humidity": hum_val,
                "light": "明亮" if not is_dark() else "昏暗",
                "pir": "有人" if is_person() else "无人",
                "soil": "湿润" if soil_moisture_digital == GPIO.LOW else "干燥"
            }
        }
    
    @staticmethod
    def turn_on_light():
        """开灯 - 调用 main.py 的 press_open"""
        press_open()
        update_status_file()
        return {"status": "ok", "message": "灯已打开", "lamp_state": True}
    
    @staticmethod
    def turn_off_light():
        """关灯 - 调用 main.py 的 press_close"""
        press_close()
        update_status_file()
        return {"status": "ok", "message": "灯已关闭", "lamp_state": False}
    
    @staticmethod
    def water_plant(duration: int = 5):
        """浇水"""
        global irrigation_in_progress
        GPIO.output(relay_pin, GPIO.LOW)
        irrigation_in_progress = True
        time.sleep(duration)
        GPIO.output(relay_pin, GPIO.HIGH)
        irrigation_in_progress = False
        update_status_file()
        return {"status": "ok", "message": f"浇水 {duration} 秒完成", "irrigation": "已完成"}
    
    @staticmethod
    def open_window():
        """开窗 - 调用 main.py 的 move_window"""
        move_window("open")
        update_status_file()
        return {"status": "ok", "message": "窗户已打开", "window": "opened"}
    
    @staticmethod
    def close_window():
        """关窗 - 调用 main.py 的 move_window"""
        move_window("close")
        update_status_file()
        return {"status": "ok", "message": "窗户已关闭", "window": "closed"}
    
    @staticmethod
    def get_health_index():
        """获取健康指数"""
        update_dht(force_update=True) # 强制更新
        soil_moisture_digital = read_soil_moisture()
        air_temp_float = float(temp_val) if temp_val != "--" else 25
        air_humid_float = float(hum_val) if hum_val != "--" else 50
        health = calculate_health_index(air_temp_float, air_humid_float, soil_moisture_digital)
        return {"status": "ok", "health_index": health}

    @staticmethod
    def toggle_auto_control(enable: bool):
        """切换自动/手动控制模式"""
        global auto_control_running
        auto_control_running = enable
        mode = "自动" if enable else "手动"
        return {"status": "ok", "mode": mode, "message": f"已切换到{mode}控制模式"}

    @staticmethod
    def get_system_status():
        """获取系统状态"""
        update_dht(force_update=True) # 强制更新
        soil_moisture_digital = read_soil_moisture()
        air_temp_float = float(temp_val) if temp_val != "--" else 25
        air_humid_float = float(hum_val) if hum_val != "--" else 50
        health = calculate_health_index(air_temp_float, air_humid_float, soil_moisture_digital)

        # 获取天气预报
        weather = get_weather()

        # 生成智能建议
        suggestions = []
        if soil_moisture_digital == GPIO.LOW:
            suggestions.append("土壤湿润，暂时不需要浇水")
        else:
            suggestions.append("土壤干燥，建议浇水")

        if weather:
            # 温度建议
            if air_temp_float > 28:
                suggestions.append("温度过高，建议开窗通风")
            elif air_temp_float < 10:
                suggestions.append("温度过低，建议关窗保暖")
            else:
                suggestions.append("温度适宜")

            # 天气建议
            weather_cond = weather.get("condition", "")
            rain = weather.get("rain", "0.0mm")
            if "🌧" in weather_cond or "🌦" in weather_cond or "🌧" in weather_cond or float(rain.replace("mm", "")) > 0:
                suggestions.append("⚠️ 有降雨天气，建议保持窗户关闭")
            elif "☀️" in weather_cond or "⛅" in weather_cond:
                suggestions.append("天气晴好，适合开窗通风")
        else:
            suggestions.append("温度适宜")

        return {
            "status": "ok",
            "sensors": {
                "temperature": temp_val,
                "humidity": hum_val,
                "light": "明亮" if not is_dark() else "昏暗",
                "light_raw": GPIO.input(light_pin),
                "pir": "有人" if is_person() else "无人",
                "pir_raw": GPIO.input(pir_pin),
                "soil": "湿润" if soil_moisture_digital == GPIO.LOW else "干燥",
                "soil_raw": soil_moisture_digital
            },
            "devices": {
                "lamp": "开" if lamp_state else "关",
                "window": window_actual_state,
                "irrigation": "工作中" if irrigation_in_progress else "关闭"
            },
            "health_index": health,
            "weather": weather,
            "suggestions": suggestions
        }

    def get_weather():
        """获取天气预报"""
        weather = get_weather()
        if weather:
            return {"status": "ok", "weather": weather}
        return {"status": "error", "message": "无法获取天气"}

# ==================== MCP HTTP 处理 ====================
class MCPHandler(BaseHTTPRequestHandler):
    """MCP 请求处理器"""
    
    def log_message(self, format, *args):
        print(f"[MCP] {args[0]}")
    
    def do_GET(self):
        if self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok"}).encode())
        else:
            self.send_error(404)
    
    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)
        
        try:
            request = json.loads(body.decode())
            tool_name = request.get("tool", "")
            params = request.get("params", {})
            req_id = request.get("id", 1)
            
            tools = {
                "get_environment_data": MCPTools.get_environment_data,
                "get_weather": MCPTools.get_weather,
                "turn_on_light": MCPTools.turn_on_light,
                "turn_off_light": MCPTools.turn_off_light,
                "water_plant": lambda: MCPTools.water_plant(params.get("duration", 5)),
                "open_window": MCPTools.open_window,
                "close_window": MCPTools.close_window,
                "get_health_index": MCPTools.get_health_index,
                "get_system_status": MCPTools.get_system_status,
            }
            
            if tool_name in tools:
                result = tools[tool_name]()
                response = {"jsonrpc": "2.0", "result": result, "id": req_id}
            else:
                response = {"jsonrpc": "2.0", "error": {"code": "-32601", "message": f"Method not found: {tool_name}"}, "id": req_id}
            
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(response).encode())
            
        except Exception as e:
            error_response = {"jsonrpc": "2.0", "error": {"code": "-32603", "message": str(e)}, "id": 1}
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(error_response).encode())

# ==================== 状态文件管理 ====================
STATUS_FILE = "/tmp/balcony_status.json"
WEATHER_CACHE = {"data": None, "time": 0}
WEATHER_CACHE_DURATION = 300  # 5分钟缓存

def get_weather():
    """获取天气信息（带缓存）"""
    import subprocess
    current_time = time.time()

    # 检查缓存
    if WEATHER_CACHE["data"] and (current_time - WEATHER_CACHE["time"] < WEATHER_CACHE_DURATION):
        return WEATHER_CACHE["data"]

    try:
        result = subprocess.run(
            ["curl", "-s", "wttr.in/xiamen?format=%l|%c|%t|%h|%p|%P"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0 and result.stdout.strip():
            parts = result.stdout.strip().split("|")
            if len(parts) >= 6:
                weather = {
                    "location": parts[0],
                    "condition": parts[1].strip(),
                    "temp": parts[2].strip(),
                    "humidity": parts[3].strip(),
                    "rain": parts[4].strip(),
                    "pressure": parts[5].strip()
                }
                WEATHER_CACHE["data"] = weather
                WEATHER_CACHE["time"] = current_time
                return weather
    except:
        pass
    return None

def update_status_file():
    """更新状态文件"""
    try:
        update_dht(force_update=True) # 强制更新以获取最新数据
        soil_moisture_digital = read_soil_moisture()
        air_temp_float = float(temp_val) if temp_val != "--" else 25
        air_humid_float = float(hum_val) if hum_val != "--" else 50
        health_index = calculate_health_index(air_temp_float, air_humid_float, soil_moisture_digital)
        
        status = {
            "sensors": {
                "temperature": temp_val,
                "humidity": hum_val,
                "light": "明亮" if not is_dark() else "昏暗",
                "light_raw": GPIO.input(light_pin),
                "pir": "有人" if is_person() else "无人",
                "pir_raw": GPIO.input(pir_pin),
                "soil": "湿润" if soil_moisture_digital == GPIO.LOW else "干燥",
                "soil_raw": soil_moisture_digital
            },
            "devices": {
                "lamp": "开" if lamp_state else "关",
                "window": window_actual_state,
                "irrigation": "工作中" if irrigation_in_progress else "关闭"
            },
            "health_index": health_index
        }
        
        with open(STATUS_FILE, 'w') as f:
            json.dump(status, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"更新状态文件错误: {e}")

# ==================== 自动控制逻辑 ====================
def run_auto_control():
    """执行自动控制逻辑"""
    global last_action_time, last_light_state

    current_time = time.time()

    # --- 1. 智能灯控核心逻辑 ---
    current_dark = is_dark()      # 检测环境是否昏暗
    person_now = is_person()      # 检测是否有人
    update_dht()                  # 更新温湿度数据 (使用缓存)

    action_ready = (current_time - last_action_time > 1.5)  # 灯控动作准备就绪

    if current_dark != last_light_state and action_ready:
        if current_dark:  # 环境变暗
            if person_now:  # 且有人
                press_open()  # 开灯
                print("💡 智能灯控：有人且环境昏暗，已开灯")
                notify_device_change("💡 智能灯控", "已开灯", "有人且环境昏暗")
                last_action_time = current_time
        else:  # 环境变亮
            press_close()  # 关灯
            print("🌙 智能灯控：环境明亮，已关灯")
            notify_device_change("🌙 智能灯控", "已关灯", "环境明亮")
            last_action_time = current_time

        last_light_state = current_dark

    # --- 2. 盆栽健康分核心逻辑 ---
    soil_moisture_digital = read_soil_moisture()  # 读取土壤湿度
    air_temp_float = float(temp_val) if temp_val != "--" else 25  # 获取温度值
    air_humid_float = float(hum_val) if hum_val != "--" else 50   # 获取湿度值
    
    health_index = calculate_health_index(air_temp_float, air_humid_float, soil_moisture_digital)

    # --- 3. 智能灌溉控制 ---
    soil_dry_flag = (soil_moisture_digital == GPIO.HIGH)  # 判断土壤是否干燥
    global irrigation_status_message, irrigation_in_progress
    irrigation_status_message, irrigation_in_progress = control_irrigation(soil_dry_flag, current_time)

    # --- 4. 智能控窗逻辑 (结合厦门4月天气) ---
    window_status = get_window_control_status(air_temp_float, air_humid_float)

# ==================== 主程序 ====================

# OLED 锁
oled_lock = threading.Lock()

def safe_oled_show():
    """
    安全显示OLED内容（线程安全）
    :return: 显示成功返回True，否则返回False
    """
    try:
        with oled_lock:
            oled.image(image)
            oled.show()
        return True
    except OSError as e:
        print(f"OLED显示错误: {e}")
        return False

print("✅ 智能阳台监控系统已启动")

# ==================== MCP 服务器启动 ====================
FLAG_FILE = "/tmp/auto_control.flag"

def is_auto_mode():
    """检查是否为自动控制模式"""
    try:
        with open(FLAG_FILE, "r") as f:
            return f.read().strip() == "auto"
    except FileNotFoundError:
        return True  # 默认自动

def auto_control_thread():
    """自动控制后台线程"""
    print("✅ 自动控制逻辑已启动")

    while True:
        try:
            if is_auto_mode():
                run_auto_control()
            time.sleep(0.5)
        except Exception as e:
            print(f"自动控制循环错误: {e}")
            time.sleep(1)

def start_mcp_server():
    """启动 MCP 服务器"""
    global auto_control_running

    print("=" * 50)
    print("🌿 智能阳台 MCP 服务器")
    print("=" * 50)

    # 初始归位
    set_angle(init_angle)
    print("✅ 舵机归位")

    # 启动自动控制线程
    auto_thread = threading.Thread(target=auto_control_thread, daemon=True)
    auto_thread.start()
    print("✅ 自动控制线程已启动")

    # 初始化状态文件
    update_status_file()
    print("✅ 状态文件已创建")

    # 启动 HTTP 服务器
    port = 8000
    server = HTTPServer(("", port), MCPHandler)
    print(f"✅ MCP 服务运行在 http://0.0.0.0:{port}")
    print("=" * 50)
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n🛑 MCP 服务已停止")
        auto_control_running = False
    finally:
        # 清理资源
        GPIO.output(window_motor_ia, GPIO.LOW)
        GPIO.output(window_motor_ib, GPIO.LOW)
        GPIO.output(relay_pin, GPIO.HIGH)
        set_angle(init_angle)
        servo_pwm.stop()
        draw.rectangle((0, 0, 128, 64), outline=0, fill=0)
        oled.image(image)
        oled.show()
        GPIO.cleanup()
        server.shutdown()

# 启动 MCP 服务器（它会包含自动控制线程）
if __name__ == "__main__":
    # 启动 MCP 服务器和自动控制线程
    mcp_thread = threading.Thread(target=start_mcp_server, daemon=True)
    mcp_thread.start()
    
    # 主显示循环 (与 MCP 服务器在不同线程中运行)
    try:
        while True:
            current_time = time.time()
            
            # --- 5. OLED 显示 ---
            # 只有在没有电机操作且不在灌溉时才更新显示，避免冲突
            if not window_action_in_progress and not irrigation_in_progress:
                draw.rectangle((0, 0, 128, 64), outline=0, fill=0)
                col_left_x, col_mid_x, col_right_x = 0, 43, 86  # 三列X坐标
                line_1_y, line_2_y, line_3_y = 0, 14, 28       # 三行Y坐标

                # 左栏：灯控
                draw.text((col_left_x, line_1_y), "智能灯控", font=small_font, fill=1)
                draw.text((col_left_x, line_1_y + 12), f"   {('昏暗', '明亮')[int(not is_dark())]}", font=small_font, fill=1)
                draw.text((col_left_x, line_2_y + 12), f"   {('无人', '有人')[int(is_person())]}", font=small_font, fill=1)
                draw.text((col_left_x, line_3_y + 12), f"   {('灯关', '灯开')[int(lamp_state)]}", font=small_font, fill=1)

                # 中栏：灌溉
                draw.text((col_mid_x, line_1_y), "智能灌溉", font=small_font, fill=1)
                draw.text((col_mid_x, line_1_y + 12), f"  S:{'湿润' if read_soil_moisture() == GPIO.LOW else '干燥'}", font=small_font, fill=1)
                # 获取健康指数用于显示 (这里直接计算，也可以缓存)
                soil_moisture_digital = read_soil_moisture()
                air_temp_float = float(temp_val) if temp_val != "--" else 25
                air_humid_float = float(hum_val) if hum_val != "--" else 50
                health_index = calculate_health_index(air_temp_float, air_humid_float, soil_moisture_digital)
                draw.text((col_mid_x, line_2_y + 12), f"  H:{health_index}%", font=small_font, fill=1)
                if irrigation_in_progress:
                    draw.text((col_mid_x, line_3_y + 12), "  浇水中", font=small_font, fill=1)
                else:
                    if not (read_soil_moisture() == GPIO.HIGH): # soil not dry
                        draw.text((col_mid_x, line_3_y + 12), "无需浇水", font=small_font, fill=1)
                    else:
                        draw.text((col_mid_x, line_3_y + 12), irrigation_status_message, font=small_font, fill=1)

                # 右栏：控窗
                draw.text((col_right_x, line_1_y), "智能控窗", font=small_font, fill=1)
                draw.text((col_right_x, line_1_y + 12), f"温:{temp_val}°C", font=small_font, fill=1)
                draw.text((col_right_x, line_2_y + 12), f"湿:{hum_val}%", font=small_font, fill=1)
                window_display = "开窗" if window_actual_state == "opened" else "关窗"
                draw.text((col_right_x, line_3_y + 12), f"    {window_display}", font=small_font, fill=1)

                safe_oled_show()
            
            time.sleep(0.1)

    except KeyboardInterrupt:
        print("\n🛑 用户中断")
    finally:
        # 确保电机停止
        GPIO.output(window_motor_ia, GPIO.LOW)
        GPIO.output(window_motor_ib, GPIO.LOW)
        
        # 关闭继电器（停止灌溉）
        GPIO.output(relay_pin, GPIO.HIGH)
        if irrigation_in_progress:
            print("🌱 智能灌溉：水泵关闭")
        
        # 归位舵机
        set_angle(init_angle)
        servo_pwm.stop()
        
        # 清空OLED屏幕并关闭显示
        draw.rectangle((0, 0, 128, 64), outline=0, fill=0)
        oled.image(image)
        oled.show()
        oled.fill(0)
        oled.show()
        
        # 清理GPIO
        GPIO.cleanup()
        print("🧹 资源清理完成")
