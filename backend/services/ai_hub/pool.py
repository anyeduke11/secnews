"""ai_hub 模型池 — 内置国产主流平台目录 + 密钥解析 + 可用模型探测 (DEV-0244)。

定位裁决 (owner: "pi 是 Agent 不是模型, 模型池内置各平台接口信息, 用户提供
key 即可, 自动识别有哪些模型可用"):

- **模型池 (本模块)** = 平台目录 + key 存放 + /models 探测, 回答"有哪些
  平台可用、各有哪些模型"。pi (type=pi, 子进程 Agent harness) **不属于**
  模型池 — 它在 agent_channels 单列。
- **llm.yaml providers** = 路由配置 (哪个任务用哪个 provider/model), 不因
  本目录扩大而膨胀; 平台接入流程 = 池内存 key → 探测确认 → 需要参与路由时
  再在 llm.yaml 加 provider 条目。
- 密钥解析与 AIService._resolve_api_key 同链: env (key_env/别名) > 加密
  保险箱 (llm_secrets WHERE provider=<平台名>)。env 永不落库, 保险箱经
  Fernet 加密。
- 探测: GET {base_url}/models (OpenAI 兼容), 6s 超时, 401/403 = 密钥无效,
  404/405 = 平台不提供模型列表接口 (key 有效与否未知 → unknown), 其余报错
  截断 120 字。附带凭据前过 check_credential_egress (C3 门禁同链)。
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any

import httpx

from backend.logging_config import logger

# 内置平台目录 — 全部 OpenAI 兼容网关。新增平台: 加条目 + egress.py 登记 host。
@dataclass(frozen=True)
class PlatformPreset:
    name: str            # 平台标识 (llm_secrets.provider 与此对齐)
    label: str           # 中文展示名
    base_url: str        # OpenAI 兼容 base
    key_env: str         # 首选环境变量名
    key_env_aliases: tuple[str, ...] = ()  # 社区常见别名


PLATFORM_PRESETS: tuple[PlatformPreset, ...] = (
    PlatformPreset("sensenova", "商汤日日新", "https://token.sensenova.cn/v1", "SENSENOVA_API_KEY"),
    PlatformPreset("deepseek", "DeepSeek", "https://api.deepseek.com/v1", "DEEPSEEK_API_KEY"),
    PlatformPreset("qwen", "阿里通义 (百炼)", "https://dashscope.aliyuncs.com/compatible-mode/v1",
                   "QWEN_API_KEY", ("DASHSCOPE_API_KEY",)),
    PlatformPreset("moonshot", "月之暗面 Kimi", "https://api.moonshot.cn/v1", "MOONSHOT_API_KEY"),
    PlatformPreset("zhipu", "智谱 GLM", "https://open.bigmodel.cn/api/paas/v4", "ZHIPU_API_KEY",
                   ("GLM_API_KEY",)),
    PlatformPreset("doubao", "字节豆包 (方舟)", "https://ark.cn-beijing.volces.com/api/v3", "ARK_API_KEY",
                   ("DOUBAO_API_KEY", "VOLC_API_KEY")),
    PlatformPreset("minimax", "MiniMax", "https://api.minimax.chat/v1", "MINIMAX_API_KEY"),
    PlatformPreset("siliconflow", "硅基流动", "https://api.siliconflow.cn/v1", "SILICONFLOW_API_KEY"),
    PlatformPreset("hunyuan", "腾讯混元", "https://api.hunyuan.cloud.tencent.com/v1", "HUNYUAN_API_KEY"),
)

PRESETS_BY_NAME: dict[str, PlatformPreset] = {p.name: p for p in PLATFORM_PRESETS}

# Agent 通道 — 非模型, 模型池 UI 单列展示 (pi = earendil 子进程 harness)
AGENT_CHANNELS: tuple[dict[str, str], ...] = (
    {"name": "pi", "kind": "subprocess-agent",
     "desc": "pi -p --mode json 子进程 (认证自管 ~/.pi/agent/auth.json), 非模型池成员"},
)

_PROBE_TIMEOUT = 6.0


def resolve_preset_key(name: str) -> tuple[str, str]:
    """解析平台密钥, 返回 (key, source); source ∈ env|secrets|none。

    与 AIService._resolve_api_key 同链 (env 优先, 保险箱兜底, fail-soft)。
    """
    preset = PRESETS_BY_NAME.get(name)
    if preset is None:
        return "", "none"
    for env_name in (preset.key_env, *preset.key_env_aliases):
        if v := os.environ.get(env_name, ""):
            return v, "env"
    try:
        from backend.repository.secrets_repo import SecretRepository
        from backend.services.secrets_service import SecretsService, _is_unlocked
        item = SecretRepository().get_by_provider(name)
        if item is None:
            return "", "none"
        if not _is_unlocked(item.encryption_key_id):
            return "", "none"
        return SecretsService().decrypt_for_internal_use(item.id) or "", "secrets"
    except Exception as e:
        logger.warning("pool key read for %s failed: %s", name, e)
        return "", "none"


def probe_platform(preset: PlatformPreset) -> dict[str, Any]:
    """探测单平台: GET /models。返回 {available, models, model_count, latency_ms, error}。

    available 三态: True (拿到模型列表) / None (平台无列表接口, key 未知) /
    False (401/403 或网络错误)。
    """
    from .egress import check_credential_egress

    key, _src = resolve_preset_key(preset.name)
    out: dict[str, Any] = {
        "available": None, "models": [], "model_count": 0,
        "latency_ms": None, "error": None,
    }
    if not key:
        out["error"] = "no_key"
        out["available"] = False
        return out
    check_credential_egress(preset.base_url)

    t0 = time.monotonic()
    try:
        resp = httpx.get(
            f"{preset.base_url.rstrip('/')}/models",
            headers={"Authorization": f"Bearer {key}"},
            timeout=_PROBE_TIMEOUT,
        )
    except Exception as e:
        out["available"] = False
        out["error"] = f"{type(e).__name__}: {str(e)[:120]}"
        return out
    out["latency_ms"] = int((time.monotonic() - t0) * 1000)
    if resp.status_code in (401, 403):
        out["available"] = False
        out["error"] = f"HTTP {resp.status_code} (密钥无效或无权限)"
        return out
    if resp.status_code in (404, 405):
        # 平台不提供 /models (如部分方舟/MiniMax 网关) — key 有效性未知
        out["error"] = "platform_no_models_endpoint"
        return out
    if resp.status_code != 200:
        out["available"] = False
        out["error"] = f"HTTP {resp.status_code}"
        return out
    try:
        data = resp.json().get("data", [])
        models = sorted(str(m.get("id")) for m in data if isinstance(m, dict) and m.get("id"))
    except Exception as e:
        out["available"] = False
        out["error"] = f"parse: {type(e).__name__}"
        return out
    out["available"] = True
    out["models"] = models[:100]
    out["model_count"] = len(models)
    return out


def pool_snapshot(*, probe: bool = False, only: str | None = None) -> dict[str, Any]:
    """模型池快照。probe=False 只报配置状态 (零出站); probe=True 逐平台探测。"""
    platforms: list[dict[str, Any]] = []
    for preset in PLATFORM_PRESETS:
        if only and preset.name != only:
            continue
        key, src = resolve_preset_key(preset.name)
        entry: dict[str, Any] = {
            "name": preset.name,
            "label": preset.label,
            "base_url": preset.base_url,
            "key_env": preset.key_env,
            "configured": bool(key),
            "key_source": src,
            "available": None,
            "models": [],
            "model_count": 0,
            "latency_ms": None,
            "error": None,
        }
        if probe and key:
            entry.update(probe_platform(preset))
        platforms.append(entry)
    return {
        "platforms": platforms,
        "agent_channels": [dict(a) for a in AGENT_CHANNELS],
        "probed": probe,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


__all__ = [
    "PLATFORM_PRESETS",
    "PRESETS_BY_NAME",
    "AGENT_CHANNELS",
    "resolve_preset_key",
    "probe_platform",
    "pool_snapshot",
]
