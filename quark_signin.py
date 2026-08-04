"""
cron "13 18 * * *" script-path=xxx.py,tag=匹配cron用
new Env('夸克签到')
"""
import json
import os
import re
import sys
import time
import random
import requests
from datetime import datetime, timedelta

# ---------------- 统一通知模块加载（和NodeSeek一样）----------------
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

#推送函数（修改为使用notify.py）
def Push(contents):
    """修改推送函数使用notify.py（保持原始调用方式）"""
    if hadsend:
        try:
            send('夸克签到', contents)
            print('✅ notify.py推送成功')
        except Exception as e:
            print(f'❌ notify.py推送失败: {e}')
    else:
        print(f'📢 夸克签到')
        print(f'📄 {contents}')

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

def format_bytes(size_bytes):
    """字节数格式化为人类可读单位"""
    units = ("B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")
    i = 0
    while size_bytes >= 1024 and i < len(units) - 1:
        size_bytes /= 1024
        i += 1
    return f"{size_bytes:.2f} {units[i]}"

def wait_with_countdown(delay_seconds):
    """带倒计时的等待"""
    if delay_seconds <= 0:
        return

    print(f"夸克签到需要等待 {format_time_remaining(delay_seconds)}")

    remaining = delay_seconds
    while remaining > 0:
        if remaining <= 10 or remaining % 10 == 0:
            print(f"倒计时: {format_time_remaining(remaining)}")

        sleep_time = 1 if remaining <= 10 else min(10, remaining)
        time.sleep(sleep_time)
        remaining -= sleep_time

# 获取环境变量
def get_env():
    # 判断 QUARK_COOKIE是否存在于环境变量
    if "QUARK_COOKIE" in os.environ:
        # 读取系统变量以 \n 或 && 分割变量
        cookie_list = re.split('\n|&&',os.environ.get('QUARK_COOKIE') ) #os.environ.get('QUARK_COOKIE')
    else:
        # 标准日志输出
        print('❌未添加QUARK_COOKIE变量')
        # 脚本退出
        sys.exit(0)

    return cookie_list

VIP_MAP = {
    "NORMAL": "普通用户",
    "EXP_SVIP": "88VIP",
    "SUPER_VIP": "SVIP",
    "Z_VIP": "SVIP+",
}

class Quark:
    BASE_URL_APP = "https://drive-m.quark.cn"
    USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) quark-cloud-drive/3.14.2 Chrome/112.0.5615.165 Electron/24.1.3.8 Safari/537.36 Channel/pckk_other_ch"

    def __init__(self, cookie):
        self.cookie = cookie.strip()
        # 从 cookie 中提取移动端反爬参数 kps/sign/vcode
        self.mparam = self._match_mparam_from_cookie(self.cookie)

    @staticmethod
    def _match_mparam_from_cookie(cookie):
        """从 cookie 中提取移动端反爬参数 kps/sign/vcode"""
        mparam = {}
        kps_match = re.search(r"(?<!\w)kps=([a-zA-Z0-9%+/=]+)[;&]?", cookie)
        sign_match = re.search(r"(?<!\w)sign=([a-zA-Z0-9%+/=]+)[;&]?", cookie)
        vcode_match = re.search(r"(?<!\w)vcode=([a-zA-Z0-9%+/=]+)[;&]?", cookie)
        if kps_match and sign_match and vcode_match:
            mparam = {
                "kps": kps_match.group(1).replace("%25", "%"),
                "sign": sign_match.group(1).replace("%25", "%"),
                "vcode": vcode_match.group(1).replace("%25", "%"),
            }
        return mparam

    def get_growth_info(self):
        url = f"{self.BASE_URL_APP}/1/clouddrive/capacity/growth/info"
        querystring = {
            "pr": "ucpro",
            "fr": "android",
            "kps": self.mparam.get("kps"),
            "sign": self.mparam.get("sign"),
            "vcode": self.mparam.get("vcode"),
        }
        headers = {
            "content-type": "application/json",
            "user-agent": self.USER_AGENT,
            "cookie": self.cookie,
        }
        try:
            response = requests.get(url=url, headers=headers, params=querystring).json()
        except Exception as e:
            return False, f"网络错误: {e}"
        if response.get("data"):
            return True, response["data"]
        else:
            return False, json.dumps(response, ensure_ascii=False)

    def get_growth_sign(self):
        url = f"{self.BASE_URL_APP}/1/clouddrive/capacity/growth/sign"
        querystring = {
            "pr": "ucpro",
            "fr": "android",
            "kps": self.mparam.get("kps"),
            "sign": self.mparam.get("sign"),
            "vcode": self.mparam.get("vcode"),
        }
        payload = {"sign_cyclic": True}
        headers = {
            "content-type": "application/json",
            "user-agent": self.USER_AGENT,
            "cookie": self.cookie,
        }
        try:
            response = requests.post(url=url, json=payload, headers=headers, params=querystring).json()
        except Exception as e:
            return False, f"网络错误: {e}"
        if response.get("data"):
            return True, response["data"]["sign_daily_reward"]
        else:
            return False, response.get("message", "未知错误")

    def do_sign(self):
        msg = ""
        # 移动端参数检查
        if not self.mparam:
            msg += " ❌ cookie中未找到移动端参数(kps/sign/vcode)，无法签到\n"
            msg += "    需从夸克APP或移动端网页(m.quark.cn)抓包获取含kps/sign/vcode的cookie\n"
            return msg

        # 每日领空间（移动端接口，兼作账号有效性校验，返回 401 即登录失效）
        ok, growth_info = self.get_growth_info()
        if not ok:
            if "401" in str(growth_info) or "require login" in str(growth_info).lower():
                msg += " ❌ 该账号登录失败，cookie无效或已失效，请重新抓包\n"
            else:
                msg += f"❌ 获取签到状态失败：{growth_info}\n"
            return msg

        member_type = VIP_MAP.get(
            growth_info.get("member_type", ""),
            growth_info.get("member_type", "未知"),
        )
        total_capacity = format_bytes(growth_info.get("total_capacity", 0))
        sign_reward_total = format_bytes(
            growth_info.get("cap_composition", {}).get("sign_reward", 0)
        )
        growth_message = (
            f"💾 {member_type} 总空间：{total_capacity}，"
            f"签到累计获得：{sign_reward_total}"
        )

        cap_sign = growth_info.get("cap_sign", {})
        if cap_sign.get("sign_daily"):
            # 今日已签到（按需求同样推送提醒）
            sign_message = (
                f"📅 今日已签到+{int(cap_sign.get('sign_daily_reward', 0) / 1024 / 1024)}MB，"
                f"连签进度({cap_sign.get('sign_progress')}/{cap_sign.get('sign_target')})✅"
            )
            msg += sign_message + "\n"
            msg += growth_message + "\n"
        else:
            sign, sign_return = self.get_growth_sign()
            if sign:
                sign_message = (
                    f"📅 今日签到+{int(sign_return / 1024 / 1024)}MB，"
                    f"连签进度({cap_sign.get('sign_progress', 0) + 1}/{cap_sign.get('sign_target')})✅"
                )
                msg += sign_message + "\n"
                msg += growth_message + "\n"
            else:
                msg += f"❌ 签到失败: {sign_return}\n"

        return msg

def main():
    msg = ""
    global QUARK_COOKIE

    QUARK_COOKIE = get_env()

    print("✅检测到共", len(QUARK_COOKIE), "个夸克账号\n")

    i = 0
    while i < len(QUARK_COOKIE):
        # 开始任务
        log = f"🙍🏻‍♂️ 第{i + 1}个账号"
        msg += log
        # 登录
        log = Quark(QUARK_COOKIE[i]).do_sign()
        msg += log + "\n"

        # 多账号间随机等待
        if i < len(QUARK_COOKIE) - 1:  # 不是最后一个账号
            delay = random.uniform(3, 8)
            print(f"随机等待 {delay:.1f} 秒后处理下一个账号...")
            time.sleep(delay)

        i += 1

    print(msg)

    # 统一推送（只推送一次，包含所有账号结果）
    Push(contents=msg[:-1])

    return msg[:-1]

if __name__ == "__main__":
    print(f"==== 夸克网盘签到开始 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ====")

    # 随机延迟（可选）
    if random_signin:
        delay_seconds = random.randint(0, max_random_delay)
        if delay_seconds > 0:
            signin_time = datetime.now() + timedelta(seconds=delay_seconds)
            print(f"随机模式: 延迟 {format_time_remaining(delay_seconds)} 后签到")
            print(f"预计签到时间: {signin_time.strftime('%H:%M:%S')}")
            wait_with_countdown(delay_seconds)

    print("----------夸克网盘开始尝试签到----------")
    main()
    print("----------夸克网盘签到执行完毕----------")
    print(f"==== 夸克签到完成 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ====")
