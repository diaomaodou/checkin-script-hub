#!/usr/bin/python3
# -*- coding: utf-8 -*-
"""
cron "30 21 * * *" script-path=glados_checkin.py,tag=匹配cron用
new Env('GLaDOS签到')
"""

import hashlib
import math
import os
import random
import re
import sys
import time
from datetime import datetime
from urllib.parse import urlsplit

import requests

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
max_random_delay = int(os.getenv("MAX_RANDOM_DELAY", "600"))
random_signin = os.getenv("RANDOM_SIGNIN", "true").lower() == "true"
privacy_mode = os.getenv("PRIVACY_MODE", "true").lower() == "true"

GLADOS_BASE = "https://glados.cloud"
CHECKIN_CHALLENGE_DELAY = 2.7
NORMAL_CHECKIN_PATTERNS = (
    r"checkin! got \d+(?:\.\d+)? points[.!]?",
    r"checkin repeats! please try tomorrow[.!]?",
    r"today's observation logged(?:[.!].*)?",
)

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
        self.session.headers.update(
            {
                "User-Agent": DEFAULT_UA,
                "Cookie": self.cookie,
                "Accept": "application/json, text/plain, */*",
                "Origin": GLADOS_BASE,
                "Referer": f"{GLADOS_BASE}/console/checkin",
            }
        )

    def _request(self, method, path, data=None):
        """只向固定域名请求，错误信息不包含凭据或原始响应。"""
        try:
            url = f"{GLADOS_BASE}{path}"
            if method == "GET":
                resp = self.session.get(url, timeout=15, allow_redirects=False)
            else:
                resp = self.session.post(
                    url, json=data, timeout=15, allow_redirects=False
                )
            if resp.status_code in (401, 403):
                return {"http_status": resp.status_code, "reason": "http-auth-rejected"}
            if resp.status_code != 200:
                return {
                    "http_status": resp.status_code,
                    "request_failed": True,
                    "retryable": resp.status_code == 429 or resp.status_code >= 500,
                    "message": "HTTP 请求失败，今日签到状态未知",
                }
            result = resp.json()
            if not isinstance(result, dict):
                raise ValueError("invalid API response")
            return result
        except requests.exceptions.InvalidHeader:
            return {
                "request_failed": True,
                "retryable": False,
                "message": "请求头格式错误，请检查 Cookie 和 GLADOS_UA",
            }
        except (requests.RequestException, ValueError):
            # requests 的异常可能包含完整 Cookie，不直接记录异常文本。
            return {
                "request_failed": True,
                "retryable": True,
                "message": "网络或响应格式异常，今日签到状态未知",
            }

    def _get_status(self):
        """获取账号状态（剩余天数、邮箱等）"""
        return self._request("GET", "/api/user/status")

    def _get_points(self):
        """获取签到后的积分余额。"""
        return self._request("GET", "/api/user/points")

    @staticmethod
    def _is_auth_rejected(result):
        message = str(result.get("message") or result.get("msg") or "").lower()
        return (
            result.get("code") in (-2, 4)
            or result.get("http_status") in (401, 403)
            or str(result.get("reason", "")).lower() == "device-mismatch"
            or any(
                marker in message
                for marker in (
                    "没有权限",
                    "permission",
                    "unauthorized",
                    "automated check-in detected",
                )
            )
        )

    @classmethod
    def _is_success(cls, result):
        if cls._is_auth_rejected(result) or result.get("request_failed"):
            return False
        message = str(result.get("message") or result.get("msg") or "").strip().lower()
        return result.get("code") == 0 or any(
            re.fullmatch(pattern, message) for pattern in NORMAL_CHECKIN_PATTERNS
        )

    def _checkin(self):
        """每次提交前获取新验证，等待并在签发验证的同域提交。"""
        challenge = self._request("GET", "/api/user/checkin/challenge")
        if self._is_auth_rejected(challenge) or challenge.get("request_failed"):
            return challenge
        nonce = challenge.get("nonce")
        ttl = challenge.get("ttl", 300000)
        if (
            challenge.get("code") != 0
            or not isinstance(nonce, str)
            or not 0 < len(nonce) <= 4096
            or type(ttl) not in (int, float)
            or not math.isfinite(ttl)
            or ttl <= CHECKIN_CHALLENGE_DELAY * 1000
        ):
            return {
                "request_failed": True,
                "retryable": True,
                "message": "未获取有效签到验证，本次未提交签到",
            }
        received_at = time.monotonic()
        proof = hashlib.sha256(
            (nonce + ".glados-observe-v1").encode("utf-8")
        ).hexdigest()
        time.sleep(CHECKIN_CHALLENGE_DELAY)
        if (time.monotonic() - received_at) * 1000 >= ttl:
            return {
                "request_failed": True,
                "retryable": True,
                "message": "签到验证已过期，本次未提交签到",
            }
        return self._request(
            "POST",
            "/api/user/checkin",
            {
                "token": urlsplit(GLADOS_BASE).hostname,
                "nonce": nonce,
                "proof": proof,
            },
        )

    def _checkin_with_retry(self):
        attempts = max(1, int(os.getenv("GLADOS_MAX_ATTEMPTS", "3")))
        delay = max(0, int(os.getenv("GLADOS_RETRY_DELAY_SECONDS", "60")))
        for attempt in range(1, attempts + 1):
            result = self._checkin()
            if (
                self._is_success(result)
                or self._is_auth_rejected(result)
                or not result.get("retryable")
                or attempt == attempts
            ):
                return result
            print(
                f"⚠️ 账号{self.index}: 第 {attempt}/{attempts} 次请求失败，{delay} 秒后重试"
            )
            time.sleep(delay)

    @staticmethod
    def _as_int(value):
        try:
            return int(float(value))
        except (TypeError, ValueError, OverflowError):
            return None

    @staticmethod
    def _extract_balance(result):
        """从签到返回中提取当前积分余额"""
        entries = result.get("list")
        if isinstance(entries, list):
            for entry in entries:
                if isinstance(entry, dict):
                    balance = Glados._as_int(entry.get("balance"))
                    if balance is not None:
                        return balance
        return None

    def main(self):
        """单账号签到主流程，返回 (result_msg, is_success)"""
        print(f"👤 账号{self.index}: 🎯 开始 GLaDOS 签到")
        lines = ["🌐 GLaDOS 签到结果"]

        result = self._checkin_with_retry()
        is_success = self._is_success(result)
        message = str(result.get("message") or result.get("msg") or "")
        account = f"账号{self.index}"
        left_days = None
        balance = None
        if is_success:
            if "checkin repeats! please try tomorrow" in message.lower():
                status_line = "📅 今日已签到"
            else:
                status_line = f"✅ 签到成功，{message or '签到完成'}"
            balance = self._extract_balance(result)
            status = self._get_status()
            info = status.get("data")
            if status.get("code") == 0 and isinstance(info, dict):
                account = info.get("email") or info.get("phone") or account
                left_days = self._as_int(info.get("leftDays"))
            else:
                lines.append("⚠️ 账号资料未刷新，不影响已确认的签到结果")
            if not self._is_auth_rejected(status):
                points = self._get_points()
                if (
                    not self._is_auth_rejected(points)
                    and not points.get("request_failed")
                    and ("code" not in points or points.get("code") == 0)
                ):
                    current = self._as_int(points.get("points"))
                    if current is not None:
                        balance = current
                    else:
                        lines.append("⚠️ 积分未刷新，若有显示则为签到响应余额")
                else:
                    lines.append("⚠️ 积分未刷新，若有显示则为签到响应余额")
            else:
                lines.append("⚠️ 状态查询认证被拒绝，已停止后续请求")
        elif self._is_auth_rejected(result):
            status_line = (
                "❌ 会话或设备校验被拒绝，请核对完整 Cookie 与 GLADOS_UA；"
                "已停止该账号重试和后续查询"
            )
        elif result.get("request_failed"):
            status_line = f"❌ {message}；本次运行失败，今日签到状态未知"
        else:
            code = result.get("code")
            detail = f"（code={code}）" if type(code) is int else ""
            status_line = f"❌ 签到未确认成功{detail}，请核对官网记录"

        print(f"账号{self.index}: {status_line}")
        lines.append(f"👤 账号: {mask_account(account)}")
        lines.append(f"📊 签到状态: {status_line}")
        if is_success:
            lines.append(f"💰 当前积分: {balance if balance is not None else '未获取'}")
            days_label = f"{left_days} 天" if left_days is not None else "未获取"
            lines.append(f"📅 剩余天数: {days_label}")
        lines.append(f"🕐 时间: {datetime.now():%Y-%m-%d %H:%M:%S}")
        return "\n".join(lines), is_success


def main():
    """主程序入口"""
    print(f"==== GLaDOS 签到开始 - {datetime.now():%Y-%m-%d %H:%M:%S} ====")

    accounts = get_accounts()
    if not accounts:
        error_msg = """❌ 未配置 GLADOS_COOKIE 环境变量

🔧 Cookie 获取方式:
1. 浏览器登录 https://glados.cloud 并进入签到页面
2. 按 F12 打开开发者工具 → Network 标签页
3. 刷新页面，找到成功的 /api/user/status 请求
4. 复制完整 Cookie（含 gld:sess 与 gld:sess.sig）填入 GLADOS_COOKIE
5. 多账号用 && 或换行分隔

💡 若签到提示设备校验失败，请把 GLADOS_UA 配置为与登录浏览器一致的 User-Agent"""
        print(error_msg)
        notify_user("GLaDOS签到", error_msg)
        return 1

    # 随机延迟不能替代获取 challenge 后的必要等待。
    if random_signin:
        delay = random.randint(1, max(max_random_delay, 1))
        print(f"🎲 随机延迟 {format_time_remaining(delay)} 后开始签到")
        wait_with_countdown(delay, "GLaDOS签到")

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
        except Exception as e:
            detail = type(e).__name__
            msg = f"🌐 GLaDOS 签到结果\n👤 账号: 账号{index}\n📊 状态: ❌ 执行异常: {detail}；今日签到状态未知"
            ok = False
            print(f"❌ 账号{index}: 执行异常: {detail}")
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

    print(
        f"==== GLaDOS 签到完成 - 成功{success_count}/{len(accounts)} - "
        f"{datetime.now():%Y-%m-%d %H:%M:%S} ===="
    )
    return 0 if success_count == len(accounts) else 1


if __name__ == "__main__":
    sys.exit(main())
