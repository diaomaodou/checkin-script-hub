#!/usr/bin/python3
# -*- coding: utf-8 -*-
"""
cron "20 0 * * *" script-path=genshin_checkin.py,tag=匹配cron用
new Env('原神签到')
"""

import os
import re
import time
import uuid
import random
import hashlib
import requests
from datetime import datetime
from string import ascii_lowercase, digits

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

# 共享代理工具：境外 VPS 无法连通米哈游服务时自动切换国内免费代理
try:
    from freeproxy_helper import ProxiedRequestSession
    _has_proxy_helper = True
except ImportError:
    _has_proxy_helper = False
    print("⚠️  未加载 freeproxy_helper 模块，境外 VPS 上可能无法连接米哈游服务（境内直连不受影响）")

# 代理模式：auto(默认，先直连遇网络错误/WAF再回退) / always(境外VPS推荐，直接走代理) / off
proxy_mode = os.getenv("USE_CN_PROXY", "auto").lower()

# 随机延迟配置
max_random_delay = int(os.getenv("MAX_RANDOM_DELAY", "3600"))
random_signin = os.getenv("RANDOM_SIGNIN", "true").lower() == "true"
privacy_mode = os.getenv("PRIVACY_MODE", "true").lower() == "true"

# 打码狗验证码识别（可选，触发极验时启用）
damagou_userkey = os.getenv("DAMAGOU_USERKEY", "").strip()


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
    """脱敏账号/UID（保留前3后4）"""
    if not value or not privacy_mode:
        return value or "未知"
    value = str(value)
    if len(value) >= 7:
        return f"{value[:3]}****{value[-4:]}"
    return value


def mask_nickname(name):
    """脱敏昵称（保留首字符）"""
    name = str(name or "").strip()
    if not name:
        return "旅行者"
    if not privacy_mode:
        return name
    return name[0] + "**"


# ---------------- 米哈游常量 ----------------
GAME_BIZ = "hk4e_cn"
ACT_ID = "e202311201442471"
ACCOUNT_ROLES_URL = "https://api-takumi.mihoyo.com/binding/api/getUserGameRolesByCookie"
HOME_URL = "https://api-takumi.mihoyo.com/event/luna/home?lang=zh-cn"
INFO_URL = "https://api-takumi.mihoyo.com/event/luna/info?lang=zh-cn"
SIGN_URL = "https://api-takumi.mihoyo.com/event/luna/sign"
COOKIE_TOKEN_REFRESH_URL = "https://api-takumi.mihoyo.com/auth/api/getCookieAccountInfoBySToken"
BBS_VERSION = "2.106.2"
UA = (
    "Mozilla/5.0 (Linux; Android 12; Unspecified Device) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Version/4.0 Chrome/103.0.5060.129 Mobile Safari/537.36 "
    "miHoYoBBS/2.106.2"
)
WEB_SALT = "G1ktdwFL4IyGkHuuWSmz0wUe9Db9scyK"
DAMAGOU_URL = "http://api.damagou.top/apiv1/jiyanRecognize.html"
CAPTCHA_MAX_RETRIES = 3


def generate_ds():
    """生成米哈游 web DS 签名参数"""
    t = str(int(time.time()))
    r = "".join(random.choice(ascii_lowercase + digits) for _ in range(6))
    sign = hashlib.md5(f"salt={WEB_SALT}&t={t}&r={r}".encode()).hexdigest()
    return f"{t},{r},{sign}"


def describe_award(awards, index):
    """描述签到奖励（越界时收敛到边界）"""
    if not awards:
        return "未知"
    index = min(max(index, 0), len(awards) - 1)
    award = awards[index]
    return f"「{award.get('name', '未知')}」x{award.get('cnt', '?')}"


def get_accounts():
    """解析 GENSHIN_COOKIE 多账号（&& 或换行分隔）"""
    raw = os.getenv("GENSHIN_COOKIE", "")
    return [x.strip() for x in re.split(r"\n|&&", raw) if x.strip()]


def get_stokens():
    """解析 GENSHIN_STOKEN（与账号同分隔符）"""
    raw = os.getenv("GENSHIN_STOKEN", "")
    return [x.strip() for x in re.split(r"\n|&&", raw) if x.strip()]


def parse_stoken(raw):
    """解析 stoken 配置项。

    支持两种格式：
    - 纯 stoken 值（stuid 从 cookie 的 account_id/ltuid 解析）
    - k=v 形式：stuid=xxx&mid=yyy&stoken=zzz（v2_ stoken 必须带 mid）
    """
    raw = (raw or "").strip()
    if not raw:
        return None
    if "stoken=" in raw or ("=" in raw and "&" in raw):
        info = {}
        for part in raw.split("&"):
            k, _, v = part.strip().partition("=")
            if k:
                info[k] = v
        if not info.get("stoken"):
            return None
        return {
            "stoken": info["stoken"],
            "stuid": info.get("stuid", ""),
            "mid": info.get("mid", ""),
        }
    return {"stoken": raw, "stuid": "", "mid": ""}


def parse_cookie_value(cookie, key):
    """从 cookie 字符串中提取指定 key 的值"""
    for part in (cookie or "").split(";"):
        k, _, v = part.strip().partition("=")
        if k == key:
            return v.strip()
    return ""


def parse_account_id(cookie):
    """从 cookie 中解析账号 UID（兼容 v1/v2 各字段）"""
    return (parse_cookie_value(cookie, "account_id")
            or parse_cookie_value(cookie, "account_id_v2")
            or parse_cookie_value(cookie, "ltuid")
            or parse_cookie_value(cookie, "ltuid_v2")
            or parse_cookie_value(cookie, "stuid"))


def has_cookie_token(cookie):
    """Cookie 是否包含签到必需的 cookie_token（v1 或 v2 均可）。

    miHoYo 新版登录已改为下发 cookie_token_v2（旧 cookie_token 不再生成），
    两者均为签到 API 兼容的 Cookie Token 形式。
    """
    return bool(parse_cookie_value(cookie, "cookie_token")
                or parse_cookie_value(cookie, "cookie_token_v2"))


def _retcode_is_valid(resp):
    """代理探针可用性判定：米哈游接口返回含 retcode 的 JSON 即为可达。

    （freeproxy_helper 默认判定要求响应含 code 字段，与米哈游 retcode 格式不符）
    """
    try:
        data = resp.json()
        return isinstance(data, dict) and "retcode" in data
    except Exception:
        return False


_proxied_session = None


def _get_shared_session():
    """跨账号共享的 ProxiedRequestSession（懒初始化）。"""
    global _proxied_session
    if _proxied_session is None and _has_proxy_helper:
        _proxied_session = ProxiedRequestSession(
            base_url="https://api-takumi.mihoyo.com",
            test_path="/binding/api/getUserGameRolesByCookie",
            probe_headers={"User-Agent": UA},
            probe_method="GET",
            proxy_mode=proxy_mode,
            is_valid=_retcode_is_valid,
        )
    return _proxied_session


class GenshinCheckin:
    def __init__(self, cookie, stoken_raw, index):
        self.cookie = cookie.strip()
        self.stoken_info = parse_stoken(stoken_raw)
        self.index = index
        # 基于cookie生成稳定设备ID（同一cookie刷新token后设备不变）
        self.device_id = str(uuid.uuid3(uuid.NAMESPACE_URL, self.cookie)).upper()
        self.session = requests.Session()

    def _headers(self):
        """构造米哈游请求头（DS 每次现算，含时间戳不能复用）"""
        return {
            "Accept": "application/json, text/plain, */*",
            "DS": generate_ds(),
            "x-rpc-channel": "miyousheluodi",
            "Origin": "https://act.mihoyo.com",
            "x-rpc-app_version": BBS_VERSION,
            "User-Agent": UA,
            "x-rpc-client_type": "5",
            "Referer": "https://act.mihoyo.com/",
            "Accept-Language": "zh-CN,en-US;q=0.8",
            "X-Requested-With": "com.mihoyo.hyperion",
            "Cookie": self.cookie,
            "x-rpc-device_id": self.device_id,
            "x-rpc-signgame": "hk4e",
        }

    def _request(self, method, url, params=None, json_body=None, extra_headers=None):
        """统一请求入口：支持国内代理自动回退；返回解析后的 JSON dict。

        有 freeproxy_helper 时走 ProxiedRequestSession（多域名用完整 URL，
        其不支持 params 参数故手工拼 query string），网络错误/代理全失效时
        抛 ConnectionError 交给上层处理；否则回退裸 requests 直连。
        """
        hdrs = self._headers()
        hdrs.update(extra_headers or {})
        if params:
            sep = "&" if "?" in url else "?"
            url = url + sep + "&".join(f"{k}={v}" for k, v in params.items())
        session = _get_shared_session()
        if session is not None:
            result = session.request(method, url, body=json_body, headers=hdrs)
            # 仅当返回 helper 内部网络错误标记(code=-1 且带 result:null)时转 ConnectionError，
            # 避免把业务真实返回误判为网络错误
            if isinstance(result, dict) and result.get("code") == -1 and "result" in result:
                raise requests.exceptions.ConnectionError(result.get("msg", "网络连接错误"))
            return result
        resp = self.session.request(method, url, headers=hdrs, json=json_body, timeout=15)
        resp.raise_for_status()
        return resp.json()

    # ---------------- 接口封装 ----------------

    def _get_roles(self, retried=False):
        """获取账号绑定的原神角色列表"""
        data = self._request("GET", ACCOUNT_ROLES_URL, params={"game_biz": GAME_BIZ})
        if data.get("retcode") == -100 and not retried:
            if self._refresh_cookie_token():
                return self._get_roles(retried=True)
        if data.get("retcode") != 0:
            print(f"❌ 账号{self.index}: 获取角色失败: {data.get('message')}({data.get('retcode')})")
            return []
        roles = data.get("data", {}).get("list", [])
        return roles if isinstance(roles, list) else []

    def _refresh_cookie_token(self):
        """Cookie 失效时用 stoken 刷新 cookie_token（需配置 GENSHIN_STOKEN）"""
        if not self.stoken_info or not self.stoken_info.get("stoken"):
            print(f"❌ 账号{self.index}: Cookie失效且未配置 GENSHIN_STOKEN，无法自动刷新")
            return False
        stoken = self.stoken_info["stoken"]
        mid = self.stoken_info.get("mid", "")
        if stoken.startswith("v2_") and not mid:
            print(f"❌ 账号{self.index}: v2_ 开头的 stoken 必须提供 mid"
                  f"（GENSHIN_STOKEN 用 stuid=..&mid=..&stoken=.. 格式）")
            return False
        stuid = (self.stoken_info.get("stuid")
                 or parse_account_id(self.cookie))
        if not stuid:
            print(f"❌ 账号{self.index}: 无法解析 stuid（cookie 缺少 account_id/ltuid）")
            return False
        cookie_hdr = f"stuid={stuid};stoken={stoken}"
        if mid:
            cookie_hdr += f";mid={mid}"
        print(f"🔄 账号{self.index}: 尝试用 stoken 刷新 cookie_token")
        try:
            data = self._request("GET", COOKIE_TOKEN_REFRESH_URL, extra_headers={"Cookie": cookie_hdr})
        except requests.exceptions.ConnectionError as e:
            print(f"❌ 账号{self.index}: 刷新 cookie_token 网络错误: {e}")
            return False
        refresh_data = data.get("data") or {}
        token = refresh_data.get("cookie_token") or refresh_data.get("cookie_token_v2")
        if data.get("retcode") != 0 or not token:
            print(f"❌ 账号{self.index}: 刷新 cookie_token 失败: "
                  f"{data.get('message')}({data.get('retcode')})")
            return False
        account_id = refresh_data.get("account_id") or refresh_data.get("account_id_v2") or stuid
        if "cookie_token=" in self.cookie:
            self.cookie = re.sub(r"cookie_token=[^;]*", f"cookie_token={token}", self.cookie)
        else:
            self.cookie = f"{self.cookie};cookie_token={token}"
        if "account_id=" in self.cookie:
            self.cookie = re.sub(r"account_id=[^;]*", f"account_id={account_id}", self.cookie)
        else:
            self.cookie = f"{self.cookie};account_id={account_id}"
        print(f"✅ 账号{self.index}: cookie_token 刷新成功")
        return True

    def _ensure_cookie_token(self):
        """确保 Cookie 包含签到必需的 cookie_token（v1 或 v2 均可）。

        event/luna 接口（查询/签到）要求 Cookie 含 account_id+cookie_token；
        miHoYo 新版登录签发的是 cookie_token_v2（旧 cookie_token 不再下发），
        两者均为签到 API 兼容形式。仅当缺少全部 token 时，才尝试用
        GENSHIN_STOKEN 自动补齐。
        """
        if has_cookie_token(self.cookie):
            return True
        if not self.stoken_info or not self.stoken_info.get("stoken"):
            print(f"❌ 账号{self.index}: Cookie 缺少 cookie_token/cookie_token_v2（签到必需），"
                  f"且未配置 GENSHIN_STOKEN，无法自动补齐")
            return False
        print(f"⚠️ 账号{self.index}: Cookie 缺少 cookie_token/cookie_token_v2，尝试用 stoken 自动补齐")
        return self._refresh_cookie_token()

    def _get_awards(self):
        """获取当月签到奖励列表"""
        data = self._request("GET", HOME_URL, params={"act_id": ACT_ID})
        if data.get("retcode") != 0:
            return []
        awards = data.get("data", {}).get("awards", [])
        return awards if isinstance(awards, list) else []

    def _get_info(self, role, retried=False):
        """查询角色签到状态（遇 -100 先用 stoken 刷新 cookie_token 后重试一次）"""
        data = self._request("GET", INFO_URL, params={
            "act_id": ACT_ID,
            "region": role.get("region"),
            "uid": role.get("game_uid"),
        })
        if data.get("retcode") == -100 and not retried:
            if self._refresh_cookie_token():
                return self._get_info(role, retried=True)
        return data.get("data", {}) if data.get("retcode") == 0 else {}

    def _sign(self, role, solution=None, retried=False):
        """执行签到；solution 为验证码识别结果时附带极验三头

        遇 -100 时先用 stoken 刷新 cookie_token 后重试一次。
        """
        headers = {}
        if solution:
            headers = {
                "x-rpc-challenge": solution["challenge"],
                "x-rpc-validate": solution["validate"],
                "x-rpc-seccode": f"{solution['validate']}|jordan",
            }
        result = self._request("POST", SIGN_URL, json_body={
            "act_id": ACT_ID,
            "region": role.get("region"),
            "uid": role.get("game_uid"),
        }, extra_headers=headers)
        if result.get("retcode") == -100 and not retried:
            if self._refresh_cookie_token():
                return self._sign(role, solution=solution, retried=True)
        return result

    # ---------------- 验证码（打码狗） ----------------

    def _solve_captcha_damagou(self, gt, challenge):
        """调用打码狗识别极验验证码，返回 {validate, challenge} 或 None"""
        if not (gt and challenge) or not damagou_userkey:
            return None
        try:
            resp = self.session.get(
                DAMAGOU_URL,
                params={
                    "userkey": damagou_userkey,
                    "gt": gt,
                    "challenge": challenge,
                    "isJson": "2",
                },
                timeout=60,
            )
            data = resp.json()
        except Exception as e:
            print(f"❌ 账号{self.index}: 打码狗请求失败: {e}")
            return None
        if str(data.get("status")) == "0" and data.get("data") and "|" in str(data["data"]):
            # 打码狗返回格式为 "challenge|validate"（注意顺序，challenge 在前）
            new_challenge, validate = str(data["data"]).split("|", 1)
            return {"validate": validate.strip(), "challenge": new_challenge.strip()}
        print(f"❌ 账号{self.index}: 打码狗识别失败: {data}")
        return None

    def _retry_captcha_sign(self, role, result):
        """触发验证码后的重签循环（最多 CAPTCHA_MAX_RETRIES 轮）"""
        current = result
        for attempt in range(1, CAPTCHA_MAX_RETRIES + 1):
            sign_data = current.get("data") or {}
            gt = str(sign_data.get("gt") or "")
            challenge = str(sign_data.get("challenge") or "")
            solution = self._solve_captcha_damagou(gt, challenge)
            if not solution:
                print(f"💤 账号{self.index}: 验证码识别失败({attempt}/{CAPTCHA_MAX_RETRIES})，"
                      f"重新签到获取新验证码")
                current = self._sign(role)
                continue
            print(f"🔄 账号{self.index}: 验证码已识别({attempt}/{CAPTCHA_MAX_RETRIES})，重试签到")
            current = self._sign(role, solution)
            if current.get("retcode") == -5003:
                return current
            if current.get("retcode") == 0 and (current.get("data") or {}).get("success") != 1:
                return current
            if attempt < CAPTCHA_MAX_RETRIES:
                print(f"💤 账号{self.index}: 验证码提交失败，重新获取验证码")
                current = self._sign(role)
        return current

    # ---------------- 主流程 ----------------

    def _judge_sign_result(self, result, awards, total, role, label):
        """判定签到接口返回，输出日志并返回（结果行, 是否成功）"""
        retcode = result.get("retcode")
        if retcode == -5003:
            reward = describe_award(awards, max(total - 1, 0))
            print(f"📅 账号{self.index}: {label} 今日已签到，奖励 {reward}")
            return f"📊 原神 {label}: 📅 今日已签到，奖励 {reward}", True
        if retcode == 0:
            sign_data = result.get("data") or {}
            if sign_data.get("success") == 1:
                # 触发极验验证码
                if not damagou_userkey:
                    print(f"⚠️ 账号{self.index}: {label} 触发验证码，未配置 DAMAGOU_USERKEY，本次跳过")
                    return f"📊 原神 {label}: ⚠️ 触发验证码，未配置打码狗，本次跳过", False
                print(f"🔄 账号{self.index}: {label} 触发验证码，调用打码狗识别")
                result = self._retry_captcha_sign(role, result)
                retcode = result.get("retcode")
                sign_data = result.get("data") or {}
                if retcode == -5003:
                    reward = describe_award(awards, max(total - 1, 0))
                    print(f"📅 账号{self.index}: {label} 今日已签到，奖励 {reward}")
                    return f"📊 原神 {label}: 📅 今日已签到，奖励 {reward}", True
                if retcode == 0 and sign_data.get("success") != 1:
                    reward = describe_award(awards, total)
                    print(f"✅ 账号{self.index}: {label} 签到成功，奖励 {reward}")
                    return f"📊 原神 {label}: ✅ 签到成功，奖励 {reward}", True
                reason = f"{result.get('message') or result.get('msg')}({retcode})"
                print(f"❌ 账号{self.index}: {label} 验证码处理后仍失败: {reason}")
                return f"📊 原神 {label}: ❌ 验证码处理后仍失败 {reason}", False
            reward = describe_award(awards, total)
            print(f"✅ 账号{self.index}: {label} 签到成功，奖励 {reward}")
            return f"📊 原神 {label}: ✅ 签到成功，奖励 {reward}", True
        reason = f"{result.get('message') or result.get('msg')}({retcode})"
        print(f"❌ 账号{self.index}: {label} 签到失败: {reason}")
        return f"📊 原神 {label}: ❌ 签到失败 {reason}", False

    def main(self):
        """单账号签到主流程，返回 (result_msg, is_success)"""
        print(f"👤 账号{self.index}: 🎯 开始原神签到")
        lines = ["🎮 原神签到结果"]
        account_uid = parse_account_id(self.cookie)
        lines.append(f"👤 账号: {mask_account(account_uid)}")

        if not self._ensure_cookie_token():
            msg = ("Cookie 缺少 cookie_token/cookie_token_v2（签到必需）且未配置 GENSHIN_STOKEN，"
                   "无法签到。请重新登录 act.mihoyo.com 复制完整 Cookie（须包含 account_id 和 "
                   "cookie_token/cookie_token_v2），或在 GENSHIN_STOKEN 中配置 stoken"
                   "（v2_ 开头需附 mid）让脚本自动补齐")
            print(f"❌ 账号{self.index}: {msg}")
            lines.append(f"📊 状态: ❌ {msg}")
            lines.append(f"🕐 时间: {datetime.now():%Y-%m-%d %H:%M:%S}")
            return "\n".join(lines), False

        roles = self._get_roles()
        if not roles:
            msg = "未获取到原神角色（Cookie 失效或该账号无原神角色）"
            print(f"❌ 账号{self.index}: {msg}")
            lines.append(f"📊 状态: ❌ {msg}")
            lines.append(f"🕐 时间: {datetime.now():%Y-%m-%d %H:%M:%S}")
            return "\n".join(lines), False
        print(f"👤 账号{self.index}: 📝 获取到 {len(roles)} 个原神角色")

        awards = self._get_awards()
        all_ok = True
        for idx, role in enumerate(roles):
            if idx > 0:
                time.sleep(random.uniform(1, 3))
            uid = str(role.get("game_uid") or "")
            nickname = str(role.get("nickname") or uid or "旅行者")
            label = f"{mask_nickname(nickname)}({mask_account(uid)})"

            print(f"👤 账号{self.index}: 正在查询{label}签到状态")
            info = self._get_info(role)
            if info.get("first_bind"):
                print(f"⚠️ 账号{self.index}: {label} 首次绑定，请先在米游社手动签到一次")
                lines.append(f"📊 原神 {label}: ⚠️ 首次绑定，请先手动签到一次")
                all_ok = False
                continue

            total = int(info.get("total_sign_day") or 0)
            if info.get("is_sign"):
                reward = describe_award(awards, max(total - 1, 0))
                print(f"📅 账号{self.index}: {label} 今日已签到，奖励 {reward}")
                lines.append(f"📊 原神 {label}: 📅 今日已签到，奖励 {reward}")
                continue

            print(f"🎯 账号{self.index}: 正在为{label}签到")
            result = self._sign(role)
            status_line, ok = self._judge_sign_result(result, awards, total, role, label)
            lines.append(status_line)
            all_ok = all_ok and ok

        lines.append(f"🕐 时间: {datetime.now():%Y-%m-%d %H:%M:%S}")
        return "\n".join(lines), all_ok


def main():
    print(f"==== 原神签到开始 - {datetime.now():%Y-%m-%d %H:%M:%S} ====")

    if random_signin:
        delay = random.randint(1, max(max_random_delay, 1))
        print(f"🎲 随机延迟 {format_time_remaining(delay)} 后开始签到")
        wait_with_countdown(delay, "原神签到")

    accounts = get_accounts()
    if not accounts:
        print("❌ 未配置 GENSHIN_COOKIE 环境变量")
        print("Cookie 获取方式：")
        print("1. 浏览器登录米游社 https://bbs.mihoyo.com 或活动页 https://act.mihoyo.com（需先手动签到过一次）")
        print("2. 按 F12 打开开发者工具 → Network 标签页 → 刷新页面")
        print("3. 找到任意发往 mihoyo.com 的请求，复制请求头中的完整 Cookie")
        print("4. 确认 Cookie 中包含 account_id 和 cookie_token/cookie_token_v2 两个键")
        print("5. 填入环境变量 GENSHIN_COOKIE（多账号用 && 或换行分隔）")
        notify_user("原神签到", "❌ 未配置 GENSHIN_COOKIE，请参考 README 配置")
        return

    stokens = get_stokens()
    if stokens and len(stokens) != len(accounts):
        print(f"⚠️ GENSHIN_STOKEN 数量({len(stokens)})与账号数量({len(accounts)})不一致，"
              f"忽略 stoken 配置")
        stokens = []
    if len(stokens) < len(accounts):
        stokens = stokens + [""] * (len(accounts) - len(stokens))

    print(f"📝 共发现 {len(accounts)} 个账号")

    success_count = 0
    for i, account in enumerate(accounts):
        index = i + 1
        if i > 0:
            wait = random.uniform(10, 30)
            print(f"💤 等待 {wait:.0f} 秒后开始账号{index}")
            time.sleep(wait)
        checkin = GenshinCheckin(account, stokens[i], index)
        try:
            msg, ok = checkin.main()
        except requests.exceptions.ConnectionError as e:
            msg = (f"🎮 原神签到结果\n👤 账号: {mask_account(parse_account_id(account))}\n"
                   f"📊 状态: ❌ 网络错误（国内代理不可用）: {e}")
            ok = False
            print(f"❌ 账号{index}: 网络错误: {e}")
        except Exception as e:
            msg = (f"🎮 原神签到结果\n👤 账号: {mask_account(parse_account_id(account))}\n"
                   f"📊 状态: ❌ 执行异常: {e}")
            ok = False
            print(f"❌ 账号{index}: 执行异常: {e}")
        if ok:
            success_count += 1
        notify_user(f"原神签到-账号{index}", msg)

    if len(accounts) > 1:
        summary = [
            "🎮 原神签到汇总",
            f"📝 账号总数: {len(accounts)}",
            f"✅ 成功: {success_count}",
            f"❌ 失败: {len(accounts) - success_count}",
            f"🕐 时间: {datetime.now():%Y-%m-%d %H:%M:%S}",
        ]
        notify_user("原神签到汇总", "\n".join(summary))

    print(f"==== 原神签到完成 - {datetime.now():%Y-%m-%d %H:%M:%S} ====")


if __name__ == "__main__":
    main()
