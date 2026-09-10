# 代理配置管理模块
#
# 四种模式 (mode):
#   off      全部直连
#   builtin  内置代理 (默认): 本机 Clash 类混合端口 http://127.0.0.1:7897 + 内置国内绕行清单
#   auto     自动检测系统/浏览器代理 (环境变量 HTTP_PROXY/HTTPS_PROXY, Windows 注册表)
#   manual   手动配置 HTTP/HTTPS/SOCKS 代理
#
# 优先级: 环境变量 HOTSPOT_PROXY_* > backend/proxy_config.json > 内置默认 (builtin)。
#
# 代理失效自动切回直连 (cadence 修正批 T5):
#   - 模块级熔断器 (内存态): 连续 PROXY_FAIL_THRESHOLD 次代理请求失败 → 熔断
#     PROXY_OPEN_SECONDS 秒, 期间 should_use_proxy()/get_proxy_url() 一律返回直连;
#     窗口过后半开, 下一次代理请求即探测, 成功归零 / 失败再熔断。
#   - 请求级回退由 ProxySession / BackendSession 实现: 单次代理请求失败立刻摘掉 proxy
#     直连重试, 并把结果回写到这里 (mark_proxy_failure / mark_proxy_success)。
#   - 架构上代理只是兜底 (直连优先, 见 collectors/base._session_factory), 国内源不会被
#     送到海外出口; no_proxy 绕行清单再兜一层。

from __future__ import annotations

import json
import os
import tempfile
import threading
import time
from dataclasses import asdict, dataclass

PROXY_CONFIG_FILE = os.path.join(os.path.dirname(__file__), "proxy_config.json")

VALID_MODES = ("off", "builtin", "auto", "manual")
DEFAULT_MODE = "builtin"

# 内置代理: 本机 Clash / mihomo 等常见混合端口。仅在 mode=builtin 时生效,
# 可用 HOTSPOT_BUILTIN_PROXY_URL 覆盖 (例如换 7890)。
BUILTIN_PROXY_URL = os.environ.get("HOTSPOT_BUILTIN_PROXY_URL", "http://127.0.0.1:7897")

# 内置国内绕行清单: 国内站走海外出口只会更慢甚至被 geo-block, 一律直连。
# *.cn 覆盖 com.cn / gov.cn / org.cn / edu.cn; 后面是信源清单里的国内 .com 主站。
BUILTIN_NO_PROXY = ",".join([
    "localhost", "127.0.0.1", "::1", ".local",
    "*.cn",
    "sogou.com", "qq.com", "weixin.qq.com", "36kr.com", "secrss.com", "freebuf.com",
    "anquanke.com", "sec-wiki.com", "jin10.com", "eastmoney.com", "caixin.com",
    "ithome.com", "zbj.com", "qianlima.com", "bidcenter.com.cn", "zhaobiao.cn",
    "okcis.cn", "ebnew.com", "mayitb.com", "zhiliaobiaoxun.com", "bidnews.cn", "dlzb.com",
])

# 熔断参数 (可 env 覆盖, 便于演练)
PROXY_FAIL_THRESHOLD = int(os.environ.get("HOTSPOT_PROXY_FAIL_THRESHOLD", "3"))
PROXY_OPEN_SECONDS = float(os.environ.get("HOTSPOT_PROXY_OPEN_SECONDS", "300"))

_ENV_KEYS = (
    "HOTSPOT_PROXY_MODE", "HOTSPOT_HTTP_PROXY", "HOTSPOT_HTTPS_PROXY",
    "HOTSPOT_SOCKS_PROXY", "HOTSPOT_NO_PROXY",
)


@dataclass
class ProxySettings:
    mode: str = DEFAULT_MODE  # "off" | "builtin" | "auto" | "manual"
    http_proxy: str = ""
    https_proxy: str = ""
    socks_proxy: str = ""
    no_proxy: str = BUILTIN_NO_PROXY

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> ProxySettings:
        mode = str(data.get("mode", DEFAULT_MODE) or DEFAULT_MODE).lower()
        if mode not in VALID_MODES:
            mode = DEFAULT_MODE
        return cls(
            mode=mode,
            http_proxy=data.get("http_proxy", "") or "",
            https_proxy=data.get("https_proxy", "") or "",
            socks_proxy=data.get("socks_proxy", "") or "",
            no_proxy=data.get("no_proxy", BUILTIN_NO_PROXY) or BUILTIN_NO_PROXY,
        )


# ---------------------------------------------------------------------------
# 配置加载 (env > json > 默认), mtime 缓存
# ---------------------------------------------------------------------------
_cache_lock = threading.Lock()
_cache: dict = {"key": None, "settings": None}


def _env_overrides() -> dict:
    out: dict = {}
    for key in _ENV_KEYS:
        val = os.environ.get(key)
        if val is not None and val != "":
            out[key.removeprefix("HOTSPOT_").lower()] = val
    return out


def _file_mtime() -> float | None:
    try:
        return os.stat(PROXY_CONFIG_FILE).st_mtime
    except OSError:
        return None


def _read_file() -> dict | None:
    if not os.path.exists(PROXY_CONFIG_FILE):
        return None
    try:
        with open(PROXY_CONFIG_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except (json.JSONDecodeError, OSError, ValueError):
        return None


def invalidate_settings_cache() -> None:
    """保存配置 / 测试注入后调用, 下次 load 强制重读。"""
    with _cache_lock:
        _cache["key"] = None
        _cache["settings"] = None


def load_proxy_settings() -> ProxySettings:
    """加载代理配置: 环境变量 HOTSPOT_PROXY_* > proxy_config.json > 内置默认 (builtin)。

    文件缺失 / 损坏 → 内置默认 (不再回退到 off: 代理是默认开启的可选项)。
    结果按 (文件 mtime, env 签名) 缓存, 避免每次请求读磁盘。
    """
    env = _env_overrides()
    key = (PROXY_CONFIG_FILE, _file_mtime(), tuple(sorted(env.items())))
    with _cache_lock:
        if _cache["key"] == key and _cache["settings"] is not None:
            return _cache["settings"]
    data = _read_file() or {}
    settings = ProxySettings.from_dict(data)
    if "proxy_mode" in env:
        mode = env["proxy_mode"].lower()
        settings.mode = mode if mode in VALID_MODES else settings.mode
    if "http_proxy" in env:
        settings.http_proxy = env["http_proxy"]
    if "https_proxy" in env:
        settings.https_proxy = env["https_proxy"]
    if "socks_proxy" in env:
        settings.socks_proxy = env["socks_proxy"]
    if "no_proxy" in env:
        settings.no_proxy = env["no_proxy"]
    with _cache_lock:
        _cache["key"] = key
        _cache["settings"] = settings
    return settings


def save_proxy_settings(settings: ProxySettings):
    """保存代理配置到 JSON 文件 (原子写: 同目录临时文件 + os.replace), 并失效缓存。"""
    target_dir = os.path.dirname(PROXY_CONFIG_FILE)
    payload = json.dumps(settings.to_dict(), ensure_ascii=False, indent=2)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=target_dir, prefix=".proxy_config.", suffix=".tmp", delete=False
    ) as f:
        f.write(payload)
        tmp_name = f.name
    os.replace(tmp_name, PROXY_CONFIG_FILE)
    invalidate_settings_cache()


# ---------------------------------------------------------------------------
# 系统代理探测 (auto 模式)
# ---------------------------------------------------------------------------
def detect_system_proxy_windows() -> dict:
    """检测系统代理设置（环境变量 + Windows 注册表; macOS/Linux 只认环境变量）"""
    result = {"http": "", "https": "", "socks": ""}

    # 1. 优先检查环境变量
    for env_var in ["HTTP_PROXY", "http_proxy"]:
        val = os.environ.get(env_var, "")
        if val:
            result["http"] = val
            break
    for env_var in ["HTTPS_PROXY", "https_proxy"]:
        val = os.environ.get(env_var, "")
        if val:
            result["https"] = val
            break

    # 2. 从 Windows 注册表读取 IE/系统代理
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"
        )
        proxy_enable, _ = winreg.QueryValueEx(key, "ProxyEnable")
        proxy_server, _ = winreg.QueryValueEx(key, "ProxyServer")

        if proxy_enable and proxy_server:
            proxy_server = proxy_server.strip()
            # 格式可能是 "host:port" 或 "http=host:port;https=host:port"
            if "=" in proxy_server:
                parts = proxy_server.replace(" ", "").split(";")
                for part in parts:
                    if "=" in part:
                        proto, addr = part.split("=", 1)
                        proto = proto.lower().strip()
                        if proto in ("http", "https"):
                            result[proto] = f"{proto}://{addr}"
            else:
                if not result["http"]:
                    result["http"] = f"http://{proxy_server}"
                if not result["https"]:
                    result["https"] = f"http://{proxy_server}"

            try:
                bypass, _ = winreg.QueryValueEx(key, "ProxyOverride")
                if bypass:
                    os.environ["NO_PROXY"] = bypass
            except (OSError, ValueError):
                pass

        winreg.CloseKey(key)
    except (ImportError, OSError, ValueError):
        pass

    return result


def detect_system_proxy() -> dict:
    """检测系统代理设置"""
    return detect_system_proxy_windows()


# ---------------------------------------------------------------------------
# 熔断器 (内存态, 进程级)
# ---------------------------------------------------------------------------
_now = time.monotonic  # 测试可 monkeypatch
_health_lock = threading.Lock()
_health: dict = {
    "consecutive_failures": 0,
    "open_until": 0.0,
    "opened_count": 0,
    "total_failures": 0,
    "total_successes": 0,
    "last_error": "",
    "last_failure_at": 0.0,
    "last_success_at": 0.0,
}


def proxy_circuit_open() -> bool:
    """熔断中 (代理被判失效, 全部直连)?"""
    with _health_lock:
        return _now() < _health["open_until"]


def mark_proxy_failure(error: str | Exception | None = None) -> bool:
    """记一次代理请求失败; 连续达阈值即熔断。返回本次是否触发了熔断。"""
    msg = (f"{type(error).__name__}: {error}" if isinstance(error, Exception) else str(error or ""))[:200]
    with _health_lock:
        now = _now()
        _health["consecutive_failures"] += 1
        _health["total_failures"] += 1
        _health["last_error"] = msg
        _health["last_failure_at"] = now
        if _health["consecutive_failures"] >= PROXY_FAIL_THRESHOLD and now >= _health["open_until"]:
            _health["open_until"] = now + PROXY_OPEN_SECONDS
            _health["opened_count"] += 1
            return True
        return False


def mark_proxy_success() -> None:
    """代理请求成功: 连续失败归零, 若在半开态则闭合熔断。"""
    with _health_lock:
        _health["consecutive_failures"] = 0
        _health["total_successes"] += 1
        _health["last_success_at"] = _now()
        _health["open_until"] = 0.0


def reset_proxy_health() -> None:
    with _health_lock:
        for k, v in _health.items():
            _health[k] = 0.0 if isinstance(v, float) else (0 if isinstance(v, int) else "")


def proxy_health_snapshot() -> dict:
    with _health_lock:
        now = _now()
        remaining = max(0.0, _health["open_until"] - now)
        return {
            "circuit_open": remaining > 0,
            "open_remaining_seconds": round(remaining, 1),
            "consecutive_failures": _health["consecutive_failures"],
            "fail_threshold": PROXY_FAIL_THRESHOLD,
            "open_seconds": PROXY_OPEN_SECONDS,
            "opened_count": _health["opened_count"],
            "total_failures": _health["total_failures"],
            "total_successes": _health["total_successes"],
            "last_error": _health["last_error"],
            "seconds_since_last_failure": round(now - _health["last_failure_at"], 1) if _health["last_failure_at"] else None,
            "seconds_since_last_success": round(now - _health["last_success_at"], 1) if _health["last_success_at"] else None,
        }


# ---------------------------------------------------------------------------
# 决策: 该 URL 现在走不走代理 / 走哪个代理
# ---------------------------------------------------------------------------
def configured_proxy_url(target_url: str = "", settings: ProxySettings | None = None) -> str | None:
    """按配置 (不看熔断) 返回代理 URL; None = 未配置。"""
    settings = settings or load_proxy_settings()
    if settings.mode == "off":
        return None
    proxy_url = None
    if settings.mode == "builtin":
        proxy_url = BUILTIN_PROXY_URL
    elif settings.mode == "auto":
        system_proxy = detect_system_proxy()
        if target_url and target_url.startswith("https"):
            proxy_url = system_proxy.get("https") or system_proxy.get("http")
        else:
            proxy_url = system_proxy.get("http") or system_proxy.get("https")
    elif settings.mode == "manual":
        if settings.socks_proxy:
            proxy_url = settings.socks_proxy
        elif target_url and target_url.startswith("https") and settings.https_proxy:
            proxy_url = settings.https_proxy
        elif settings.http_proxy:
            proxy_url = settings.http_proxy
        elif settings.https_proxy:
            proxy_url = settings.https_proxy
    return proxy_url or None


def get_proxy_url(target_url: str = "") -> str | None:
    """返回当前应使用的代理 URL; None = 直连 (未配置 / off / 熔断中)。"""
    if proxy_circuit_open():
        return None
    return configured_proxy_url(target_url)


def _host_bypassed(hostname: str, no_proxy: str) -> bool:
    import fnmatch

    hostname = (hostname or "").lower()
    for bypass in no_proxy.split(","):
        bypass = bypass.strip().lower()
        if not bypass:
            continue
        # 精确匹配
        if bypass == hostname:
            return True
        # 通配符匹配（如 *.cn, *.example.com）
        if bypass.startswith("*.") and hostname.endswith(bypass[1:]):
            return True
        # 前导点后缀 (如 .local)
        if bypass.startswith(".") and hostname.endswith(bypass):
            return True
        # 子串匹配（如 baidu.com 匹配 news.baidu.com）
        if "*" not in bypass and "." in bypass and bypass in hostname:
            return True
        # fnmatch 通配符
        if "*" in bypass and fnmatch.fnmatch(hostname, bypass):
            return True
    return False


def should_use_proxy(target_url: str) -> bool:
    """该 URL 现在是否应走代理。

    False 的情形: mode=off / 熔断中 (代理被判失效 → 直连) / host 命中 no_proxy 绕行清单。
    注意不校验代理是否真的可达 — 可达性由请求级回退 + 熔断器负责。
    """
    settings = load_proxy_settings()
    if settings.mode == "off":
        return False
    if proxy_circuit_open():
        return False
    no_proxy = settings.no_proxy or BUILTIN_NO_PROXY
    from urllib.parse import urlparse

    try:
        hostname = urlparse(target_url).hostname or ""
        if _host_bypassed(hostname, no_proxy):
            return False
    except Exception:
        pass
    return True


__all__ = [
    "BUILTIN_NO_PROXY",
    "BUILTIN_PROXY_URL",
    "DEFAULT_MODE",
    "PROXY_CONFIG_FILE",
    "PROXY_FAIL_THRESHOLD",
    "PROXY_OPEN_SECONDS",
    "VALID_MODES",
    "ProxySettings",
    "configured_proxy_url",
    "detect_system_proxy",
    "detect_system_proxy_windows",
    "get_proxy_url",
    "invalidate_settings_cache",
    "load_proxy_settings",
    "mark_proxy_failure",
    "mark_proxy_success",
    "proxy_circuit_open",
    "proxy_health_snapshot",
    "reset_proxy_health",
    "save_proxy_settings",
    "should_use_proxy",
]
