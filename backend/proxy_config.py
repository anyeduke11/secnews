# 代理配置管理模块
# 支持两种模式：
#   1. auto: 自动检测系统/浏览器代理
#   2. manual: 手动配置 HTTP/HTTPS/SOCKS 代理

import json
import os
import re
import subprocess
from dataclasses import dataclass, asdict
from typing import Optional

PROXY_CONFIG_FILE = os.path.join(os.path.dirname(__file__), "proxy_config.json")

@dataclass
class ProxySettings:
    mode: str = "off"  # "off" | "auto" | "manual"
    http_proxy: str = ""
    https_proxy: str = ""
    socks_proxy: str = ""
    no_proxy: str = "localhost,127.0.0.1,::1"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ProxySettings":
        return cls(
            mode=data.get("mode", "off"),
            http_proxy=data.get("http_proxy", ""),
            https_proxy=data.get("https_proxy", ""),
            socks_proxy=data.get("socks_proxy", ""),
            no_proxy=data.get("no_proxy", "localhost,127.0.0.1,::1"),
        )


def load_proxy_settings() -> ProxySettings:
    """从 JSON 文件加载代理配置"""
    if os.path.exists(PROXY_CONFIG_FILE):
        try:
            with open(PROXY_CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            return ProxySettings.from_dict(data)
        except (json.JSONDecodeError, KeyError):
            pass
    return ProxySettings(mode="off")


def save_proxy_settings(settings: ProxySettings):
    """保存代理配置到 JSON 文件"""
    with open(PROXY_CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(settings.to_dict(), f, ensure_ascii=False, indent=2)


def detect_system_proxy_windows() -> dict:
    """检测 Windows 系统代理设置（从注册表和环境变量）"""
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
                # 按协议分别配置
                parts = proxy_server.replace(" ", "").split(";")
                for part in parts:
                    if "=" in part:
                        proto, addr = part.split("=", 1)
                        proto = proto.lower().strip()
                        if proto in ("http", "https"):
                            result[proto] = f"{proto}://{addr}"
            else:
                # 统一代理
                if not result["http"]:
                    result["http"] = f"http://{proxy_server}"
                if not result["https"]:
                    result["https"] = f"http://{proxy_server}"

            # 检查是否对本地地址绕过
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


def get_proxy_url(target_url: str = "") -> Optional[str]:
    """
    根据当前配置返回适合 aiohttp 的代理 URL。
    返回 None 表示不使用代理。
    
    Args:
        target_url: 目标 URL，用于选择 HTTP/HTTPS 代理
    """
    settings = load_proxy_settings()

    if settings.mode == "off":
        return None

    proxy_url = None

    if settings.mode == "auto":
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

    return proxy_url if proxy_url else None


def should_use_proxy(target_url: str) -> bool:
    """
    检查目标 URL 是否需要使用代理。
    白名单中的域名/模式将绕过代理（直接连接）。
    支持通配符匹配: *.cn, *.baidu.com
    """
    settings = load_proxy_settings()
    if settings.mode == "off":
        return False

    no_proxy = settings.no_proxy or "localhost,127.0.0.1,::1"
    from urllib.parse import urlparse
    import fnmatch
    try:
        parsed = urlparse(target_url)
        hostname = parsed.hostname or ""
        for bypass in no_proxy.split(","):
            bypass = bypass.strip().lower()
            if not bypass:
                continue
            # 精确匹配
            if bypass == hostname:
                return False
            # 通配符匹配（如 *.cn, *.example.com）
            if bypass.startswith("*.") and hostname.endswith(bypass[1:]):
                return False
            # 子串匹配（如 baidu.com 匹配 news.baidu.com）
            if "*" not in bypass and "." in bypass and bypass in hostname:
                return False
            # fnmatch 通配符
            if "*" in bypass and fnmatch.fnmatch(hostname, bypass):
                return False
    except Exception:
        pass
    return True
