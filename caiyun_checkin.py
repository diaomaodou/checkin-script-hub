#!/usr/bin/python3
# -*- coding: utf-8 -*-
"""
cron "10 0 * * *" script-path=caiyun_checkin.py,tag=匹配cron用
new Env('移动云盘签到')
"""

import os
import time
import base64
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

# 共享代理工具：境外 VPS 无法连通 139 服务时自动切换国内免费代理
try:
    from freeproxy_helper import ProxiedRequestSession
    _has_proxy_helper = True
except ImportError:
    _has_proxy_helper = False
    print("⚠️  未加载 freeproxy_helper 模块，境外 VPS 上可能无法连接 139 服务（境内直连不受影响）")

# 代理模式：auto(默认，先直连遇网络错误/WAF再回退) / always(境外VPS推荐，直接走代理) / off
proxy_mode = os.getenv("USE_CN_PROXY", "auto").lower()

# 随机延迟配置
max_random_delay = int(os.getenv("MAX_RANDOM_DELAY", "3600"))
random_signin = os.getenv("RANDOM_SIGNIN", "true").lower() == "true"
privacy_mode = os.getenv("PRIVACY_MODE", "true").lower() == "true"


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


def mask_account(phone):
    """脱敏手机号"""
    if not phone or not privacy_mode:
        return phone or "未知"
    phone = str(phone)
    if len(phone) >= 11:
        return f"{phone[:3]}****{phone[-4:]}"
    return phone


def bytes_to_readable(n):
    """字节数转可读格式"""
    if not n:
        return "0 B"
    try:
        n = float(n)
    except (TypeError, ValueError):
        return "0 B"
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if abs(n) < 1024.0:
            return f"{n:.2f} {unit}"
        n /= 1024.0
    return f"{n:.2f} PB"


# 常量定义
CAIYUN_BASE = "https://m.mcloud.139.com"
ORCHES_BASE = "https://orches.yun.139.com"
PORTAL_BASE = "https://caiyun.feixin.10086.cn"
MARKET_SOURCE_ID = "1097"
TARGET_SOURCE_ID = "001005"
SIGNIN_ACTIVITY_ID = "sign_in_3"
DEFAULT_UA = (
    "Mozilla/5.0 (Linux; Android 11; M2012K10C Build/RP1A.200720.011; wv) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/90.0.4430.210 "
    "Mobile Safari/537.36 MCloudApp/10.0.1"
)


_proxied_session = None

def _get_shared_session():
    """跨账号共享的 ProxiedRequestSession（懒初始化，探针用签到页接口即可）。"""
    global _proxied_session
    if _proxied_session is None and _has_proxy_helper:
        _proxied_session = ProxiedRequestSession(
            base_url=CAIYUN_BASE,
            test_path='/ycloud/signin/page/infoV3',
            probe_headers={'User-Agent': DEFAULT_UA},
            probe_method='GET',
            proxy_mode=proxy_mode,
        )
    return _proxied_session


class CaiYun:
    def __init__(self, phone, auth, index):
        self.phone = phone.strip()
        self.auth = auth.strip()
        if not self.auth.lower().startswith("basic "):
            self.auth = f"Basic {self.auth}"
        self.index = index
        self.session = requests.Session()
        self.jwt_token = ""

    def _request(self, method, url, headers=None, cookies=None, params=None, body=None):
        """统一请求入口：支持国内代理自动回退；返回解析后的 JSON dict。

        有 freeproxy_helper 时走 ProxiedRequestSession（多域名用完整 URL），
        网络错误/代理全失效时抛 ConnectionError 交给上层处理；否则回退裸 requests 直连。
        """
        hdrs = dict(headers or {})
        if cookies:
            hdrs['Cookie'] = '; '.join(f"{k}={v}" for k, v in cookies.items())
        if params:
            sep = '&' if '?' in url else '?'
            url += sep + '&'.join(f"{k}={v}" for k, v in params.items())
        session = _get_shared_session()
        if session is not None:
            result = session.request(method, url, body=body, headers=hdrs)
            # 仅当返回的是 helper 内部网络错误标记(code=-1 且带 result:null)时转 ConnectionError，
            # 避免把业务真实返回的 code=-1(如 tyrzLogin 参数错误)误判为网络错误
            if isinstance(result, dict) and result.get('code') == -1 and 'result' in result:
                raise requests.exceptions.ConnectionError(result.get('msg', '网络连接错误'))
            return result
        resp = self.session.request(method, url, headers=hdrs, json=body, timeout=15)
        return resp.json()

    def _market_referer(self):
        return (
            f"{CAIYUN_BASE}/portal/mobilecloud/index.html?path=newsignin"
            f"&sourceid={MARKET_SOURCE_ID}&enableShare=1"
            f"&token={self.jwt_token}&targetSourceId={TARGET_SOURCE_ID}"
        )

    def _market_headers(self):
        return {
            "User-Agent": DEFAULT_UA,
            "Accept": "*/*",
            "jwtToken": self.jwt_token,
            "Referer": self._market_referer(),
        }

    def _market_cookies(self):
        return {"jwtToken": self.jwt_token}

    def login(self):
        """令牌交换：Authorization → ssoToken → jwtToken"""
        try:
            print(f"👤 账号{self.index}: 开始令牌交换")

            # Step 1: 用 Basic Authorization 换取 ssoToken
            sso_headers = {
                "Authorization": self.auth,
                "User-Agent": DEFAULT_UA,
                "Content-Type": "application/json",
                "Host": "orches.yun.139.com",
            }
            sso_data = self._request(
                "POST",
                f"{ORCHES_BASE}/orchestration/auth-rebuild/token/v1.0/querySpecToken",
                headers=sso_headers,
                body={"account": self.phone, "toSourceId": TARGET_SOURCE_ID},
            )
            if not sso_data.get("success"):
                msg = sso_data.get("message") or sso_data
                print(f"❌ 账号{self.index}: 获取 ssoToken 失败 - {msg}")
                return False
            sso_token = (sso_data.get("data") or {}).get("token", "")
            if not sso_token:
                print(f"❌ 账号{self.index}: ssoToken 为空")
                return False

            # Step 2: 用 ssoToken 换取 jwtToken
            jwt_data = self._request(
                "POST",
                f"{PORTAL_BASE}/portal/auth/tyrzLogin.action",
                headers={
                    "User-Agent": DEFAULT_UA,
                    "Content-Type": "application/json",
                },
                params={"ssoToken": sso_token},
            )
            try:
                code = int(jwt_data.get("code", -1))
            except (TypeError, ValueError):
                code = -1
            if code != 0:
                msg = jwt_data.get("msg") or jwt_data
                print(f"❌ 账号{self.index}: 获取 jwtToken 失败 - {msg}")
                return False
            jwt_token = (jwt_data.get("result") or {}).get("token", "")
            if not jwt_token:
                print(f"❌ 账号{self.index}: jwtToken 为空")
                return False

            self.jwt_token = jwt_token
            print(f"✅ 账号{self.index}: 令牌交换成功")
            return True

        except requests.exceptions.Timeout:
            print(f"❌ 账号{self.index}: 登录请求超时")
            return False
        except requests.exceptions.ConnectionError:
            print(f"❌ 账号{self.index}: 网络连接错误")
            return False
        except Exception as e:
            print(f"❌ 账号{self.index}: 登录异常 - {str(e)}")
            return False

    def _extract_reward(self, payload):
        """从返回结果中尽力提取奖励数值（云朵数）"""
        if isinstance(payload, dict):
            for key in ("cloudCount", "reward", "count", "total", "receive"):
                value = payload.get(key)
                try:
                    if value is not None:
                        return int(value)
                except (TypeError, ValueError):
                    continue
            for value in payload.values():
                reward = self._extract_reward(value)
                if reward:
                    return reward
        elif isinstance(payload, list):
            for item in payload:
                reward = self._extract_reward(item)
                if reward:
                    return reward
        return 0

    def _extract_signed_today(self, result):
        """从返回结果中判断今日是否已签到"""
        if not isinstance(result, dict):
            return None
        today = result.get("todaySignIn")
        if isinstance(today, bool):
            return today
        for day in result.get("cal") or []:
            if day.get("t"):
                return bool(day.get("s"))
        return None

    def query_sign_status(self):
        """查询今日签到状态与奖励"""
        try:
            data = self._request(
                "GET",
                f"{CAIYUN_BASE}/ycloud/signin/page/infoV3",
                params={"client": "app"},
                headers=self._market_headers(),
                cookies=self._market_cookies(),
            )
            try:
                code = int(data.get("code", -1))
            except (TypeError, ValueError):
                code = -1
            if code != 0:
                return None, f"查询签到状态失败: {data.get('msg') or data}"
            result = data.get("result") or {}
            return self._extract_signed_today(result), self._extract_reward(result)
        except Exception as e:
            return None, f"查询异常: {str(e)}"

    def do_signin(self):
        """执行签到"""
        try:
            data = self._request(
                "GET",
                f"{CAIYUN_BASE}/ycloud/signin/page/startSignIn",
                params={"client": "app"},
                headers=self._market_headers(),
                cookies=self._market_cookies(),
            )
            try:
                code = int(data.get("code", -1))
            except (TypeError, ValueError):
                code = -1
            if code != 0:
                return False, 0, f"签到失败: {data.get('msg') or data}"
            result = data.get("result") or {}
            reward = self._extract_reward(result)
            return True, reward, "签到成功"
        except Exception as e:
            return False, 0, f"签到异常: {str(e)}"

    def get_capacity(self):
        """尽力查询云盘容量（best-effort，失败返回 None）"""
        try:
            auth_b64 = self.auth.split(" ", 1)[-1] if " " in self.auth else self.auth
            decoded = base64.b64decode(auth_b64).decode("utf-8", errors="ignore")
            parts = decoded.split(":")
            if len(parts) >= 3:
                account = parts[1]
            else:
                account = self.phone

            data = self._request(
                "POST",
                "https://yun.139.com/orchestration/personalCloud/rankFiles/v1.0",
                body={
                    "catalogID": "",
                    "contentSort": 1,
                    "contentDirection": 0,
                    "startNumber": 1,
                    "endNumber": 10,
                    "commonAccount": {"account": account, "accountType": 1},
                },
                headers={
                    "Authorization": self.auth,
                    "User-Agent": DEFAULT_UA,
                    "Content-Type": "application/json",
                    "Referer": "https://yun.139.com/",
                    "Origin": "https://yun.139.com",
                },
            )
            if not data.get("success"):
                return None
            inner = data.get("data") or {}
            total = inner.get("totalSize") or inner.get("totalSpaceSize")
            used = inner.get("useSize") or inner.get("usedSpaceSize")
            if total is None and used is None:
                return None
            return {"total": total, "used": used}
        except Exception:
            return None

    def main(self):
        """主执行函数"""
        try:
            print(f"\n==== 账号{self.index} 开始执行 ====")
            print(f"🕐 开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

            if not self.login():
                error_msg = f"❌ 账号{self.index}: {mask_account(self.phone)}\n令牌交换失败，无法完成签到\n\n请检查 CAIYUN_AUTH 是否过期（通常 ~30 天需重新抓取）"
                print(error_msg)
                return error_msg, False

            # 查询签到状态
            signed_today, info_reward = self.query_sign_status()
            if signed_today is None and isinstance(info_reward, str):
                error_msg = f"❌ 账号{self.index}: {info_reward}"
                print(error_msg)
                return error_msg, False

            if signed_today:
                reward = info_reward
                status_msg = f"📅 今日已签到，本月累计获得 {reward} 个云朵" if reward else "📅 今日已签到"
                print(f"📅 账号{self.index}: {status_msg}")
                is_success = True
            else:
                # 执行签到
                print(f"🎯 账号{self.index}: 开始签到")
                ok, reward, message = self.do_signin()
                if ok:
                    status_msg = f"✅ 签到成功，获得 {reward} 个云朵" if reward else "✅ 签到成功"
                    print(f"✅ 账号{self.index}: {status_msg}")
                    is_success = True
                else:
                    status_msg = f"❌ {message}"
                    print(f"❌ 账号{self.index}: {message}")
                    is_success = False

            # 查询容量（best-effort）
            capacity_line = ""
            capacity = self.get_capacity()
            if capacity:
                capacity_line = f"\n💾 云盘空间: {bytes_to_readable(capacity.get('total'))} (已用 {bytes_to_readable(capacity.get('used'))})"

            # 拼装结果
            result_msg = f"""☁️ 移动云盘签到结果

👤 账号: {mask_account(self.phone)}
📊 签到状态: {status_msg}{capacity_line}
🕐 完成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"""

            print(f"\n🎉 === 最终签到结果 ===")
            print(result_msg)
            print(f"==== 账号{self.index} 签到完成 ====\n")

            return result_msg, is_success

        except Exception as e:
            error_msg = f"❌ 账号{self.index}: 执行异常 - {str(e)}"
            print(error_msg)
            return error_msg, False


def main():
    """主程序入口"""
    print(f"==== 移动云盘签到开始 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ====")

    # 随机延迟
    if random_signin:
        delay_seconds = random.randint(0, max_random_delay)
        if delay_seconds > 0:
            signin_time = datetime.now() + timedelta(seconds=delay_seconds)
            print(f"🎲 随机模式: 延迟 {format_time_remaining(delay_seconds)} 后开始")
            print(f"⏰ 预计开始时间: {signin_time.strftime('%H:%M:%S')}")
            wait_with_countdown(delay_seconds, "移动云盘签到")

    # 获取环境变量
    phone_env = os.getenv("CAIYUN_PHONE", "")
    auth_env = os.getenv("CAIYUN_AUTH", "")

    if not phone_env or not auth_env:
        error_msg = """❌ 未找到 CAIYUN_PHONE 或 CAIYUN_AUTH 环境变量

🔧 获取 Authorization 的方法:
1. 浏览器登录 https://yun.139.cn 并进入个人云盘
2. 按 F12 打开开发者工具 → Network 标签页
3. 在云盘页面进行任意操作（如刷新文件列表）
4. 找到任意发往 yun.139.com 或 *.yun.139.com 的请求
5. 在请求头中复制 Authorization: Basic <...> 的完整值
6. 该值填入 CAIYUN_AUTH 环境变量
7. 同时记下登录手机号填入 CAIYUN_PHONE

💡 详细教程可参考 AList 官方文档:
   https://alist.nn.ci/zh/guide/drivers/139.html

📝 多账号配置: 用换行分隔多个手机号和对应的 Authorization"""
        print(error_msg)
        notify_user("移动云盘签到失败", error_msg)
        return

    # 解析多账号
    phones = [p.strip() for p in phone_env.replace("\r\n", "\n").split("\n") if p.strip()]
    auths = [a.strip() for a in auth_env.replace("\r\n", "\n").split("\n") if a.strip()]

    if len(phones) != len(auths):
        error_msg = f"❌ 账号数量不匹配: CAIYUN_PHONE 有 {len(phones)} 个, CAIYUN_AUTH 有 {len(auths)} 个"
        print(error_msg)
        notify_user("移动云盘签到失败", error_msg)
        return

    print(f"📝 共发现 {len(phones)} 个账号")

    success_accounts = 0
    all_results = []

    for index, (phone, auth) in enumerate(zip(phones, auths)):
        try:
            # 账号间随机等待
            if index > 0:
                delay = random.uniform(10, 20)
                print(f"💤 随机等待 {delay:.1f} 秒后处理下一个账号...")
                time.sleep(delay)

            # 执行签到
            caiyun = CaiYun(phone, auth, index + 1)
            result_msg, is_success = caiyun.main()
            all_results.append(result_msg)

            if is_success:
                success_accounts += 1

            # 发送单个账号通知
            title = f"移动云盘账号{index + 1}签到{'成功' if is_success else '失败'}"
            notify_user(title, result_msg)

        except Exception as e:
            error_msg = f"❌ 账号{index + 1}: 处理异常 - {str(e)}"
            print(error_msg)
            all_results.append(error_msg)
            notify_user(f"移动云盘账号{index + 1}签到失败", error_msg)

    # 发送汇总通知
    if len(phones) > 1:
        summary_msg = f"""☁️ 移动云盘签到汇总

📊 总计处理: {len(phones)}个账号
✅ 成功账号: {success_accounts}个
❌ 失败账号: {len(phones) - success_accounts}个
📅 执行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

详细结果请查看各账号单独通知"""
        notify_user("移动云盘签到汇总", summary_msg)
        print(f"\n📊 === 汇总统计 ===")
        print(summary_msg)

    print(f"\n==== 移动云盘签到完成 - 成功{success_accounts}/{len(phones)} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ====")


if __name__ == "__main__":
    main()
