"""LLM provider 出站凭据门禁 (C3)。

威胁: provider 的 ``base_url`` 来自 ``config/llm.yaml``, 而同步包应用流程
(``backend/services/sync_bundle.py`` 会写 ``base_url``) 让该文件成为可写面。
一旦 ``base_url`` 被改成攻击者主机, 调用方仍会照常附上
``Authorization: Bearer <key>`` —— 密钥与全部 prompt 内容就此外泄, 同时构成
SSRF。

因此本模块提供 **代码侧常量白名单**: 白名单不读 llm.yaml, 否则就等于让被
保护的配置自己批准自己。需要接新 provider 时, 改本文件的常量, 或用环境变量
``HOTSPOT_LLM_ALLOWED_HOSTS`` (逗号分隔) 显式追加。

调用约定: 只在**即将附带凭据**的请求前调用 :func:`check_credential_egress`。
本机 ollama (``http://127.0.0.1:11434``) 不发任何 Authorization, 因此不在
本门禁范围内 —— 它既无密钥可泄, 也不出本机。
"""
from __future__ import annotations

import os
from urllib.parse import urlsplit

# 已知合法 provider 主机。新增 provider 必须在这里显式登记。
TRUSTED_LLM_HOSTS: frozenset[str] = frozenset({
    "token.sensenova.cn",   # sensenova (config/llm.yaml)
    "api.openai.com",       # openai
    "dashscope.aliyuncs.com",  # qwen (compatible-mode)
    "api.anthropic.com",    # anthropic (gateway 内硬编码)
})

_ENV_EXTRA = "HOTSPOT_LLM_ALLOWED_HOSTS"


class EgressNotAllowedError(RuntimeError):
    """目标主机不允许携带凭据出站。"""


def allowed_hosts() -> frozenset[str]:
    extra = {
        h.strip().lower()
        for h in os.getenv(_ENV_EXTRA, "").split(",")
        if h.strip()
    }
    return TRUSTED_LLM_HOSTS | extra


def host_of(base_url: str) -> str:
    """取小写主机名 (去端口); 无法解析时返回空串。"""
    parts = urlsplit(base_url or "")
    host = (parts.hostname or "").lower()
    return host


def check_credential_egress(base_url: str) -> str:
    """校验 base_url 是否允许携带 API key 出站, 返回其主机名。

    拒绝条件: 非 https / 主机为空 / 主机不在白名单。
    抛 :class:`EgressNotAllowedError` 而不是静默降级 —— 静默会让密钥照发。
    """
    parts = urlsplit(base_url or "")
    host = (parts.hostname or "").lower()
    if parts.scheme != "https":
        raise EgressNotAllowedError(
            f"拒绝向非 https 的 LLM provider 发送凭据: {base_url!r}"
        )
    if parts.username or parts.password:
        # userinfo 会被 httpx 转成 Basic 头, 且是 authority 混淆的经典写法;
        # 注意 urlsplit 对 "https://user:pw@trusted/" 给出的 hostname 仍是 trusted,
        # 所以这一条必须独立于白名单检查。
        raise EgressNotAllowedError(
            f"拒绝携带 userinfo 的 LLM provider URL: {base_url!r}"
        )
    if not host:
        raise EgressNotAllowedError(f"无法解析 LLM provider 主机: {base_url!r}")
    if host not in allowed_hosts():
        raise EgressNotAllowedError(
            f"LLM provider 主机 {host!r} 不在代码侧白名单; "
            f"如确需接入, 请登记 TRUSTED_LLM_HOSTS 或设置 {_ENV_EXTRA}"
        )
    return host
