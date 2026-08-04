# -*- coding: utf-8 -*-
"""
国内免费代理统一工具模块

针对海外 IP 被阿里云 WAF 等服务拦截的场景，封装「试直连 → 检测 WAF → 切国内代理
→ 代理失效剔除 → 全失效重抓」的完整回退流程，供所有签到脚本复用。

底层依赖改进版 freeproxy fork：
  - ip2region 本地离线地理定位（替代外部地理 API）
  - 找到可用代理即停（边抓边验，秒级完成）
安装：pip install git+https://github.com/LeapYa/freeproxy.git@master

典型用法：
    from freeproxy_helper import ProxiedRequestSession

    session = ProxiedRequestSession(
        base_url="https://api.example.com",
        test_path="/api/ping",                # 探针接口，用于验证代理可达
        probe_headers={"user-token": "..."},   # 探针请求头（一般和真实请求一致）
        proxy_mode="auto",                     # auto(默认) / always / off
    )
    result = session.request("POST", "/api/sign", body={...}, headers={...})

CLI 自检（验证 VPS 上代理是否可用）：
    python freeproxy_helper.py
    python freeproxy_helper.py --url https://api.example.com/api/ping
"""

import argparse
import json
import os
import ssl
import sys
import urllib.error
import urllib.request


# ============ 默认配置 ============

# 实测有效的 6 个免费代理源（已剔除 GoodIPS：约 34s 返 0 个）
DEFAULT_PROXY_SOURCES = [
    "KuaidailiProxiedSession",
    "QiyunipProxiedSession",
    "KxdailiProxiedSession",
    "IP89ProxiedSession",
    "TheSpeedXProxiedSession",
    "ProxyScrapeProxiedSession",
]

DEFAULT_FILTER_RULE = {"country_code": ["CN"], "protocol": ["http", "https"]}


# ============ WAF 检测与响应判定 ============

def default_waf_detector(result):
    """默认 WAF 拦截判定：403/405，或 msg 含 <!doctype/<html（被返回 HTML 而非 JSON）。

    result 是 _direct_request / _proxy_request 返回的 dict（含 code/msg/result 键）。
    """
    code = result.get("code")
    msg = str(result.get("msg", "")).lower()
    if code in (403, 405):
        return True
    if "<!doctype" in msg or "<html" in msg:
        return True
    return False


def default_is_valid(resp):
    """默认代理可用性判定：HTTP 响应能解析为 JSON dict 且含 code 字段。

    （能拿到业务码说明请求已绕过 WAF 抵达真实服务端）
    """
    try:
        data = resp.json()
        return isinstance(data, dict) and ("code" in data)
    except Exception:
        return False


# ============ 主类 ============

class ProxiedRequestSession:
    """统一请求会话：直连优先，遇 WAF 自动回退到国内免费代理。

    代理池在一次 ProxiedRequestSession 实例内共享；多个签到账号共用同一实例
    即可避免每个账号都重新抓代理。
    """

    def __init__(
        self,
        base_url,
        test_path,
        probe_headers=None,
        probe_body=None,
        probe_method="POST",
        waf_detector=None,
        is_valid=None,
        proxy_mode="auto",
        need_proxies=3,
        proxy_sources=None,
        max_pages=2,
        source_timeout=15,
        validate_timeout=10,
        validate_workers=64,
        direct_timeout=15,
        proxy_timeout=15,
    ):
        self.base_url = base_url.rstrip("/")
        self.test_path = test_path if test_path.startswith("/") else "/" + test_path
        self.test_url = self.base_url + self.test_path
        self.probe_headers = probe_headers or {}
        self.probe_body = probe_body
        self.probe_method = probe_method.upper()
        self.waf_detector = waf_detector or default_waf_detector
        self.is_valid = is_valid or default_is_valid
        self.proxy_mode = proxy_mode.lower()
        if self.proxy_mode not in ("auto", "always", "off"):
            print(f"[proxy] 未知的 proxy_mode={proxy_mode}，回退为 auto")
            self.proxy_mode = "auto"
        self.need_proxies = need_proxies
        self.proxy_sources = proxy_sources or list(DEFAULT_PROXY_SOURCES)
        self.max_pages = max_pages
        self.source_timeout = source_timeout
        self.validate_timeout = validate_timeout
        self.validate_workers = validate_workers
        self.direct_timeout = direct_timeout
        self.proxy_timeout = proxy_timeout

        # 运行态
        self._waf_blocked = False           # 直连是否已被 WAF 拦截（标记后后续请求直接走代理）
        self._working_proxies = []          # 已验证可用的代理（requests 格式 dict 列表）
        self._proxy_client = None           # freeproxy ProxiedSessionClient 实例
        self._proxy_disabled = False        # freeproxy import 失败后永久禁用代理

        # 静默 urllib3 的 InsecureRequestWarning（免费代理常配自签证书）
        try:
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        except Exception:
            pass

        # SSL 上下文（GitHub Actions 等环境证书链可能不完整，跳过校验）
        self._ssl_ctx = ssl.create_default_context()
        self._ssl_ctx.check_hostname = False
        self._ssl_ctx.verify_mode = ssl.CERT_NONE

    # ---------- 直连 ----------

    def _direct_request(self, method, path, body=None, headers=None):
        """urllib 直连，零额外依赖。失败返回 {'code': -1, ...} 表示网络错误。"""
        url = self.base_url + (path if path.startswith("/") else "/" + path)
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(
            url, data=data, headers=headers or {}, method=method.upper()
        )
        try:
            with urllib.request.urlopen(
                req, timeout=self.direct_timeout, context=self._ssl_ctx
            ) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            body_text = e.read().decode(errors="replace") if e.fp else ""
            return {
                "code": e.code,
                "msg": f"HTTP {e.code}: {body_text[:200]}",
                "result": None,
            }
        except Exception as e:
            return {"code": -1, "msg": str(e), "result": None}

    # ---------- 代理 ----------

    def _ensure_proxy_client(self):
        """懒加载 freeproxy；import 失败给友好错误并永久禁用代理。"""
        if self._proxy_disabled:
            return False
        if self._proxy_client is not None:
            return True
        try:
            from freeproxy.freeproxy import ProxiedSessionClient
        except ImportError:
            print("[proxy] 未安装代理库，请运行: pip install -r requirements.txt")
            print("[proxy] 已禁用代理模式（后续请求只走直连）")
            self._proxy_disabled = True
            return False

        self._proxy_client = ProxiedSessionClient(
            proxy_sources=self.proxy_sources,
            init_proxied_session_cfg={
                "max_pages": self.max_pages,
                "filter_rule": dict(DEFAULT_FILTER_RULE),
            },
            disable_print=True,
            lazy=True,  # 不在构造阶段抓取，交给 fetch_working_streaming 边抓边验、命中即停
        )
        return True

    def _fetch_working_proxies(self):
        """抓取并验证一批可用国内代理，凑够 need_proxies 个就停。"""
        if not self._ensure_proxy_client():
            return []
        print("[proxy] 并发抓取+验证国内免费代理（边抓边验，找到可用即停）...")
        proxies = self._proxy_client.fetch_working_streaming(
            test_url=self.test_url,
            headers=self.probe_headers,
            need=self.need_proxies,
            source_timeout=self.source_timeout,
            validate_timeout=self.validate_timeout,
            validate_workers=self.validate_workers,
            method=self.probe_method,
            json_body=self.probe_body if self.probe_body is not None else {},
            is_valid=self.is_valid,
        )
        print(f"[proxy] 可用代理 {len(proxies)} 个")
        return proxies

    def _get_working_proxies(self, force_refetch=False):
        """获取可用代理池；池为空时自动抓一批。"""
        if self._working_proxies and not force_refetch:
            return self._working_proxies
        self._working_proxies = self._fetch_working_proxies()
        return self._working_proxies

    def _proxy_request(self, method, path, body=None, headers=None, _refetch=True):
        """通过已验证的代理发请求；某代理失效则剔除，全部失效再抓一批。"""
        try:
            import requests
        except ImportError:
            print("[proxy] 未安装 requests 库，无法走代理")
            return {"code": -1, "msg": "requests not installed", "result": None}

        url = self.base_url + (path if path.startswith("/") else "/" + path)
        proxies_list = list(self._get_working_proxies())
        last_err = {"code": -1, "msg": "proxy: no working proxy", "result": None}

        for proxies in proxies_list:
            try:
                if method.upper() == "POST":
                    resp = requests.post(
                        url, headers=headers or {}, json=body,
                        proxies=proxies, timeout=self.proxy_timeout, verify=False,
                    )
                else:
                    resp = requests.get(
                        url, headers=headers or {},
                        proxies=proxies, timeout=self.proxy_timeout, verify=False,
                    )
                result = resp.json()
                # code == -1 是脚本内部网络错误标记，不是服务端业务码
                if result.get("code") != -1:
                    return result
                last_err = result
            except Exception as e:
                last_err = {"code": -1, "msg": f"proxy error: {e}", "result": None}
                if proxies in self._working_proxies:
                    self._working_proxies.remove(proxies)
                    print(f"[proxy] 代理失效已剔除，剩余 {len(self._working_proxies)} 个")

        # 现有可用代理均失效，重新抓一批再试一次
        if _refetch and not self._proxy_disabled:
            print("[proxy] 可用代理均失效，重新抓取一批...")
            self._working_proxies.clear()
            return self._proxy_request(method, path, body, headers, _refetch=False)
        return last_err

    # ---------- 统一入口 ----------

    def request(self, method, path, body=None, headers=None):
        """统一请求入口。返回服务端 JSON（dict）。

        - proxy_mode='off'    : 永远直连
        - proxy_mode='always' : 永远走代理
        - proxy_mode='auto'   : 先直连，遇 WAF 自动切代理并打标记
        """
        if self.proxy_mode == "always":
            return self._proxy_request(method, path, body, headers)

        if self.proxy_mode == "off":
            return self._direct_request(method, path, body, headers)

        # auto
        if self._waf_blocked:
            return self._proxy_request(method, path, body, headers)

        result = self._direct_request(method, path, body, headers)
        if self.waf_detector(result):
            print("[proxy] 检测到 WAF 拦截（海外 IP 被拒），切换到国内代理...")
            self._waf_blocked = True
            return self._proxy_request(method, path, body, headers)
        return result


# ============ CLI 自检 ============

def _cli():
    """命令行自检：抓一批代理并打印耗时，方便用户在境外 VPS 上验证可用性。"""
    parser = argparse.ArgumentParser(
        description="国内免费代理工具自检（验证 VPS 上代理抓取是否可用）"
    )
    parser.add_argument(
        "--url",
        default="https://sss-web.tastientech.com/api/wx/point/myPoint",
        help="探针 URL（默认塔斯汀积分接口，可用任意返回 JSON 的接口替换）",
    )
    parser.add_argument(
        "--mode", default="always",
        choices=["auto", "always", "off"],
        help="代理模式（自检默认 always）",
    )
    parser.add_argument("--need", type=int, default=3, help="目标可用代理数")
    args = parser.parse_args()

    # 拆出 base_url 和 path
    from urllib.parse import urlparse
    parsed = urlparse(args.url)
    base_url = f"{parsed.scheme}://{parsed.netloc}"
    path = parsed.path or "/"

    import time
    print(f"[cli] 探针 URL : {args.url}")
    print(f"[cli] 代理模式 : {args.mode}")
    print(f"[cli] 目标数量 : {args.need}")
    print()

    session = ProxiedRequestSession(
        base_url=base_url,
        test_path=path,
        proxy_mode=args.mode,
        need_proxies=args.need,
    )

    start = time.monotonic()
    proxies = session._get_working_proxies()
    elapsed = time.monotonic() - start

    print()
    print(f"[cli] 抓取完成，耗时 {elapsed:.1f}s，可用代理 {len(proxies)} 个")
    if proxies:
        for i, p in enumerate(proxies, 1):
            # proxies 是 requests 格式 dict：{"http": "...", "https": "..."}
            preview = next(iter(p.values())) if p else "?"
            print(f"  [{i}] {preview}")
        sys.exit(0)
    else:
        print("[cli] 没抓到可用代理，请检查：")
        print("  1. 已安装依赖：pip install -r requirements.txt")
        print("  2. 当前网络能访问免费代理源站点")
        sys.exit(1)


if __name__ == "__main__":
    _cli()
