#!/usr/bin/python3
# -*- coding: utf-8 -*-
"""
cron "30 9 * * *" script-path=glados_checkin.py,tag=匹配cron用
new Env('GLaDOS签到')
"""

import os
import re
import time
import random
import requests
from datetime import datetime, timedelta

try:
    import urllib3
    urllib3.disable_warnings()
except Exception:
    pass

# ---------------- 统一通知模块加载 ----------------
hadsend = False
send = None
try:
    from notify import send
    hadsend = True
    print("✅ 已加载notify.py通知模块")
except ImportError:
    print("⚠️  未加载通知模块，跳过通知功能")

# 随机延迟配置
max_random_delay = int(os.getenv("MAX_RANDOM_DELAY", "3600"))
random_signin = os.getenv("RANDOM_SIGNIN", "true").lower() == "true"
privacy_mode = os.getenv("PRIVACY_MODE", "true").lower() == "true"

GLADOS_BASE = "https://glados.rocks"

# GLaDOS 会校验 User-Agent 与登录设备是否一致，不一致时返回 device-mismatch。
# 默认使用 Windows Chrome UA；若签到提示设备校验失败，用 GLADOS_UA 覆盖为与登录浏览器一致的 UA。
DEFAULT_UA = os.getenv("GLADOS_UA", "").strip() or (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)


def format_time_remaining(seconds):
    """格式化时间显示"""
    if seconds <= 0:
        return "立即执行"

    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60

    if hours > 0:
        return f"{hours}小时{minutes}分{secs}秒"
    elif minutes > 0:
        return f"{minutes}分{secs}秒"
    else:
        return f"{secs}秒"


def wait_with_countdown(delay_seconds, task_name):
    """带倒计时的随机延迟等待"""
    if delay_seconds <= 0:
        return

    print(f"{task_name} 需要等待 {format_time_remaining(delay_seconds)}")

    remaining = delay_seconds
    while remaining > 0:
        if remaining <= 10 or remaining % 10 == 0:
            print(f"{task_name} 倒计时: {format_time_remaining(remaining)}")

        sleep_time = 1 if remaining <= 10 else min(10, remaining)
        time.sleep(sleep_time)
        remaining -= sleep_time


def notify_user(title, content):
    """统一通知函数"""
    if hadsend:
        try:
            send(title, content)
            print(f"✅ 通知发送完成: {title}")
        except Exception as e:
            print(f"❌ 通知发送失败: {e}")
    else:
        print(f"📢 {title}")
        print(f"📄 {content}")


def mask_account(value):
    """脱敏账号（邮箱保留前2位，其他保留前3后4）"""
    if not value or not privacy_mode:
        return value or "未知"
    value = str(value)
    if "@" in value:
        name, _, domain = value.partition("@")
        if len(name) > 2:
            return f"{name[:2]}***@{domain}"
        return f"{name[:1]}***@{domain}" if name else f"***@{domain}"
    if len(value) >= 7:
        return f"{value[:3]}****{value[-4:]}"
    return value


def get_accounts():
    """读取 GLADOS_COOKIE，多账号用 && 或换行分隔"""
    raw = os.getenv("GLADOS_COOKIE", "")
    if not raw.strip():
        return []
    return [c.strip() for c in re.split(r"\n|&&", raw) if c.strip()]


class Glados:
    def __init__(self, cookie, index):
        self.cookie = cookie.strip()
        self.index = index
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": DEFAULT_UA,
            "Cookie": self.cookie,
            "Accept": "application/json, text/plain, */*",
            "Origin": GLADOS_BASE,
            "Referer": f"{GLADOS_BASE}/console/checkin",
        })

    def _get_status(self):
        """获取账号状态（剩余天数、邮箱等）"""
        try:
            resp = self.session.get(f"{GLADOS_BASE}/api/user/status", timeout=15)
            return resp.json()
        except Exception as e:
            return {"code": -1, "message": f"请求异常: {e}"}

    def _checkin(self):
        """执行签到"""
        try:
            resp = self.session.post(
                f"{GLADOS_BASE}/api/user/checkin",
                json={"token": "glados.one"},
                timeout=15,
            )
            return resp.json()
        except Exception as e:
            return {"code": -1, "message": f"请求异常: {e}"}

    def main(self):
        """单账号签到主流程，返回 (result_msg, is_success)"""
        print(f"👤 账号{self.index}: 🎯 开始 GLaDOS 签到")
        lines = ["🌐 GLaDOS 签到结果"]

        status = self._get_status()
        if status.get("code") != 0:
            msg = status.get("message") or status
            print(f"❌ 账号{self.index}: 获取账号状态失败 - {msg}")
            lines.append(f"📊 状态: ❌ 获取账号状态失败 - {msg}")
            lines.append(f"🕐 时间: {datetime.now():%Y-%m-%d %H:%M:%S}")
            return "\n".join(lines), False

        info = status.get("data") or {}
        account = info.get("email") or info.get("phone") or f"账号{self.index}"
        left_days = info.get("leftDays")
        try:
            left_days = int(float(left_days))
        except (TypeError, ValueError):
            left_days = None
        lines.append(f"👤 账号: {mask_account(account)}")

        result = self._checkin()
        code = result.get("code")
        message = result.get("message") or result.get("msg") or ""
        reason = result.get("reason") or ""

        if code == 0:
            points = result.get("points")
            detail = f"获得 {points} 积分" if points else (message or "签到成功")
            print(f"✅ 账号{self.index}: 签到成功，{detail}")
            status_line = f"✅ 签到成功，{detail}"
            is_success = True
        elif code == 1:
            detail = message or "今日已签到，请明天再来"
            print(f"📅 账号{self.index}: {detail}")
            status_line = f"📅 今日已签到"
            is_success = True
        elif code == 4 or reason == "device-mismatch":
            msg = ("⚠️ 设备校验失败（User-Agent 与登录设备不一致）。请在环境变量 "
                   "GLADOS_UA 中配置与登录浏览器一致的 User-Agent 后重试")
            print(f"❌ 账号{self.index}: {msg}")
            status_line = f"❌ {msg}"
            is_success = False
        else:
            msg = f"{message}(code={code})"
            print(f"❌ 账号{self.index}: 签到失败 - {msg}")
            status_line = f"❌ 签到失败 - {msg}"
            is_success = False

        lines.append(f"📊 签到状态: {status_line}")
        if left_days is not None:
            lines.append(f"📅 剩余天数: {left_days} 天")
        lines.append(f"🕐 时间: {datetime.now():%Y-%m-%d %H:%M:%S}")
        return "\n".join(lines), is_success


def main():
    """主程序入口"""
    print(f"==== GLaDOS 签到开始 - {datetime.now():%Y-%m-%d %H:%M:%S} ====")

    # 随机延迟
    if random_signin:
        delay = random.randint(1, max(max_random_delay, 1))
        print(f"🎲 随机延迟 {format_time_remaining(delay)} 后开始签到")
        wait_with_countdown(delay, "GLaDOS签到")

    accounts = get_accounts()
    if not accounts:
        error_msg = """❌ 未配置 GLADOS_COOKIE 环境变量

🔧 Cookie 获取方式:
1. 浏览器登录 https://glados.rocks 并进入签到页面
2. 按 F12 打开开发者工具 → Network 标签页
3. 点击签到，找到 checkin 请求
4. 复制请求头中的完整 Cookie 填入 GLADOS_COOKIE
5. 多账号用 && 或换行分隔

💡 若签到提示设备校验失败，请把 GLADOS_UA 配置为与登录浏览器一致的 User-Agent"""
        print(error_msg)
        notify_user("GLaDOS签到", error_msg)
        return

    print(f"📝 共发现 {len(accounts)} 个账号")

    success_count = 0
    for i, cookie in enumerate(accounts):
        index = i + 1
        if i > 0:
            wait = random.uniform(10, 30)
            print(f"💤 等待 {wait:.0f} 秒后开始账号{index}")
            time.sleep(wait)
        try:
            msg, ok = Glados(cookie, index).main()
        except requests.exceptions.ConnectionError as e:
            msg = (f"🌐 GLaDOS 签到结果\n👤 账号: 账号{index}\n"
                   f"📊 状态: ❌ 网络错误: {e}")
            ok = False
            print(f"❌ 账号{index}: 网络错误: {e}")
        except Exception as e:
            msg = (f"🌐 GLaDOS 签到结果\n👤 账号: 账号{index}\n"
                   f"📊 状态: ❌ 执行异常: {e}")
            ok = False
            print(f"❌ 账号{index}: 执行异常: {e}")
        if ok:
            success_count += 1
        notify_user(f"GLaDOS签到-账号{index}", msg)

    if len(accounts) > 1:
        summary = [
            "🌐 GLaDOS 签到汇总",
            f"📝 账号总数: {len(accounts)}",
            f"✅ 成功: {success_count}",
            f"❌ 失败: {len(accounts) - success_count}",
            f"🕐 时间: {datetime.now():%Y-%m-%d %H:%M:%S}",
        ]
        notify_user("GLaDOS签到汇总", "\n".join(summary))

    print(f"==== GLaDOS 签到完成 - 成功{success_count}/{len(accounts)} - "
          f"{datetime.now():%Y-%m-%d %H:%M:%S} ====")


if __name__ == "__main__":
    main()
