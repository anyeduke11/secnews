"""LLM 路由写入器 — 模型池"一键写入 yaml 路由"(DEV-0245)。

职责: 把模型池探测到的 (provider, model) 写进 ``config/llm.yaml`` 的
``task_overrides`` 三档锚点, 使路由真实生效:

- t1_score        → STANDARD 档 (score / ner / evaluate / semantic_filter …)
- t3_summary      → HEAVY 档 (deep_read / report)
- t3_chunk_summary→ FLASH 档 (summarize / refine / chunk_summary)

安全性:
- **定点文本编辑** (仿 knowledge_sync.update_md_frontmatter_field): 只改目标
  override 块内的 provider/model 两行, 全文件其余内容 (注释/顺序/空行) 原样
  保留 — 不用 pyyaml round-trip, 避免注释毁灭。
- **备份 + 原子写**: 先写 ``llm.yaml.bak-<ts>``, 再 .tmp → os.replace。
- **provider 块自动补建**: 平台在池目录 (pool.PLATFORM_PRESETS) 但 yaml 尚无
  provider 条目时, 追加最小 openai_compatible 块 (base_url/key_env 来自
  preset, models 五槽全部填所选模型); 已存在则不动 providers 节。
- **热重载**: gateway v0.8.2 Y-A2 (5s TTL + mtime 检测) 会在 ≤5s 内拾取变更,
  无需重启。
- 写入留痕: observability_records.record_audit(action="llm_routing.write")。

pii/凭据零接触: 本模块只写 base_url/key_env(变量名)/model 名, 永不接触 key 值。
"""
from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import Any

from backend.logging_config import logger

ROOT = Path(__file__).resolve().parent.parent.parent.parent
LLM_YAML = ROOT / "config" / "llm.yaml"

# 覆盖键 → 中文档位说明 (供 API/前端)
TIER_OVERRIDE_KEYS: dict[str, str] = {
    "t1_score": "STANDARD 档 (score/ner/evaluate 等标准分析)",
    "t3_summary": "HEAVY 档 (deep_read/report 等重分析)",
    "t3_chunk_summary": "FLASH 档 (summarize/refine 等轻量高频)",
}

# model/provider 名白名单: 字母数字与常见分隔符, 防止 yaml 结构注入
_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/\-]{0,120}$")

_PROVIDER_BLOCK_TMPL = (
    "  {name}:\n"
    '    type: openai_compatible\n'
    '    api_key_env: "{key_env}"\n'
    '    base_url: "{base_url}"\n'
    "    models:\n"
    '      score: "{model}"\n'
    '      tag: "{model}"\n'
    '      ner: "{model}"\n'
    '      summary: "{model}"\n'
    '      chunk_summary: "{model}"\n'
)


class RoutingWriteError(ValueError):
    """参数/结构不合法, 写入被拒绝。"""


def _validate(name: str, value: str, field: str) -> str:
    if not _NAME_RE.match(value):
        raise RoutingWriteError(f"invalid {field}: {value!r} (允许字母数字与 . _ : / -)")
    return value


def _ensure_provider_block(text: str, provider: str, model: str) -> tuple[str, bool]:
    """providers 节无该 provider 时追加最小块 (来自池 preset); 返回 (text, created)。"""
    if re.search(rf"^  {re.escape(provider)}:\s*$", text, re.MULTILINE):
        return text, False
    from .pool import PRESETS_BY_NAME

    preset = PRESETS_BY_NAME.get(provider)
    if preset is None:
        raise RoutingWriteError(
            f"provider {provider!r} 不在 llm.yaml providers 也不在模型池目录, 拒绝写入"
        )
    m = re.search(r"^providers:\s*$", text, re.MULTILINE)
    if m is None:
        raise RoutingWriteError("llm.yaml 缺少 providers: 节, 拒绝写入")
    # providers 节终点 = 其后第一个顶层键 (0 缩进) 或文件尾
    rest_start = m.end()
    top = re.search(r"^[a-zA-Z_][a-zA-Z0-9_]*:.*$", text[rest_start:], re.MULTILINE)
    insert_at = rest_start + top.start() if top else len(text)
    block = _PROVIDER_BLOCK_TMPL.format(
        name=provider, key_env=preset.key_env,
        base_url=preset.base_url, model=model,
    )
    # 拼回后半段 (task_overrides 等) — 漏拼会静默吞掉 providers 节之后的全部内容
    return text[:insert_at] + block + "\n" + text[insert_at:], True


def _rewrite_override_block(text: str, override_key: str, provider: str, model: str) -> str:
    """定点改写 task_overrides.<key> 块内的 provider/model 两行。"""
    block_re = re.compile(
        rf"^(?P<indent>[ ]{{2}}{re.escape(override_key)}:[ \t]*\n)"
        rf"(?P<body>(?:[ ]{{4}}[^\n]*\n?)*)",
        re.MULTILINE,
    )
    m = block_re.search(text)
    if m is None:
        raise RoutingWriteError(f"task_overrides.{override_key} 块未找到, 拒绝写入 (结构漂移?)")
    body = m.group("body")
    if not re.search(r"^    provider:", body, re.MULTILINE) or not re.search(r"^    model:", body, re.MULTILINE):
        raise RoutingWriteError(f"task_overrides.{override_key} 块缺 provider/model 行, 拒绝写入")
    new_body = re.sub(r"^    provider:.*$", f"    provider: {provider}", body, count=1, flags=re.MULTILINE)
    # model 不加引号: 值已经 _NAME_RE 白名单校验 (无 yaml 特殊字符), 且原文件
    # 风格即无引号 (model: claude-sonnet-4-5) — 强加引号会破坏幂等 (同值再写
    # 变成 text != original, noop 永远不触发)。
    new_body = re.sub(r"^    model:.*$", f"    model: {model}", new_body, count=1, flags=re.MULTILINE)
    return text[:m.start("body")] + new_body + text[m.end("body"):]


def _validate_key_usable(provider: str, model: str, *, force: bool) -> dict[str, Any]:
    """写前 key 体检 (DEV-0246; 仅池内平台 — yaml-only provider 如 pi/ollama 不在此范围)。

    - 无 key → RoutingWriteError: override 是单点选择, 无 key 写入使该档任务必败
      (此项不可 force 绕过 — force 只跳过在线探测)
    - 有 key → probe_platform 在线验证: available=False (401/403/网络) → raise;
      True → 校验 model 在列表内 (不在 → warning, 部分网关列表不全);
      None (平台无 /models 接口) → warning 放行
    """
    from .pool import PRESETS_BY_NAME, probe_platform, resolve_preset_key

    preset = PRESETS_BY_NAME.get(provider)
    if preset is None:
        return {}
    key, src = resolve_preset_key(provider)
    if not key:
        raise RoutingWriteError(
            f"{provider} 无可用密钥 (env {preset.key_env} 未设置且加密保险箱无记录) — "
            "override 是单点选择, 无 key 写入会使该档任务必败; "
            "请先在模型池贴 key 或设置环境变量"
        )
    if force:
        return {"source": src, "probed": False,
                "warning": "已跳过在线探测 (force=true) — 模型可用性未经验证"}
    probe = probe_platform(preset)
    if probe["available"] is True:
        if model not in probe["models"]:
            return {
                "source": src, "probed": True,
                "warning": (
                    f"模型 {model} 不在平台 /models 列表 ({probe['model_count']} 款) "
                    "— 可能仍有效 (部分网关列表不全)"
                ),
            }
        return {"source": src, "probed": True, "warning": None}
    if probe["available"] is None:
        return {
            "source": src, "probed": True,
            "warning": "平台无 /models 列表接口, 已跳过在线验证 (key 已配置)",
        }
    raise RoutingWriteError(
        f"{provider} 密钥探测未通过: {probe['error']} — 请修正 key 后重试;"
        " 确认模型名无误可带 force=true 重试 (跳过在线探测, 直接写入)"
    )


def write_task_override(
    override_key: str,
    provider: str,
    model: str,
    *,
    actor: str = "web",
    yaml_path: Path | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """把 (provider, model) 写入 task_overrides.<override_key>; 返回写入报告。

    provider 不在 yaml providers 时自动从模型池 preset 追加最小块。
    真实写入前做 key 体检 (DEV-0246): 无 key 拒绝, 有 key 在线探测,
    force=true 仅跳过探测。备份 ``llm.yaml.bak-<HHMMSS>`` 后原子替换;
    热重载 ≤5s 生效。
    """
    if override_key not in TIER_OVERRIDE_KEYS:
        raise RoutingWriteError(
            f"unknown override_key: {override_key!r} (允许: {', '.join(TIER_OVERRIDE_KEYS)})"
        )
    _validate(provider, provider, "provider")
    _validate(model, model, "model")

    path = yaml_path or LLM_YAML
    if not path.exists():
        raise RoutingWriteError(f"{path} 不存在")
    original = path.read_text(encoding="utf-8")

    # 先改 override 块 (结构漂移在此报错), 再补 provider 块 — 顺序保证
    # "yaml 结构坏了" 优先于 "provider 缺失" 被报告。
    text = _rewrite_override_block(original, override_key, provider, model)
    text, provider_created = _ensure_provider_block(text, provider, model)
    if text == original:
        return {
            "status": "noop", "override_key": override_key,
            "provider": provider, "model": model,
            "message": "路由已是指向该 (provider, model), 无需写入",
        }

    # DEV-0246: 真实写入前的 key 体检 (noop 已提前返回, 不做无谓出站)
    key_check = _validate_key_usable(provider, model, force=force)

    # 备份 + 原子写
    backup = path.with_name(f"{path.name}.bak-{time.strftime('%H%M%S')}")
    backup.write_text(original, encoding="utf-8")
    tmp = path.with_suffix(".yaml.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)

    try:
        from backend.observability_records import record_audit

        record_audit(
            actor=actor, action="llm_routing.write",
            target=f"task_overrides.{override_key}",
            detail={"provider": provider, "model": model,
                    "provider_block_created": provider_created,
                    "backup": backup.name},
        )
    except Exception as e:  # 留痕失败不阻塞写入
        logger.warning("llm_routing audit log skipped: %s", e)
    logger.info(
        "llm routing updated: %s -> %s/%s (provider_block_created=%s, backup=%s)",
        override_key, provider, model, provider_created, backup.name,
    )
    warn = key_check.get("warning")
    message = (
        f"已写入 {override_key} → {provider}/{model}"
        + (" (新增 provider 块)" if provider_created else "")
        + "; 热重载 ≤5s 生效"
    )
    if force:
        # force 语义提示: 本次写入未做在线探测, 可用性未经验证 (key 存在性已确认)。
        # 不再拼 key_check.warning — force 的 warning 与这句同义, 重复两遍是噪声。
        message += "; 已跳过在线探测 (force) — 模型可用性未经验证, 若调用失败请回到模型池探测或检查模型名"
    elif warn:
        message += f"; 注意: {warn}"
    return {
        "status": "ok", "override_key": override_key,
        "provider": provider, "model": model,
        "provider_block_created": provider_created,
        "backup": backup.name,
        "key_check": key_check,
        "message": message,
    }


def read_routing() -> dict[str, Any]:
    """读当前三档路由 (task_overrides t1_score/t3_summary/t3_chunk_summary)。"""
    if not LLM_YAML.exists():
        return {"routing": {}, "error": "llm.yaml 不存在"}
    try:
        import yaml

        cfg = yaml.safe_load(LLM_YAML.read_text(encoding="utf-8")) or {}
    except Exception as e:
        return {"routing": {}, "error": f"parse: {type(e).__name__}"}
    overrides = cfg.get("task_overrides") or {}
    routing = {}
    for key, label in TIER_OVERRIDE_KEYS.items():
        ov = overrides.get(key) or {}
        routing[key] = {
            "label": label,
            "provider": ov.get("provider"),
            "model": ov.get("model"),
        }
    return {"routing": routing, "error": None}


__all__ = [
    "TIER_OVERRIDE_KEYS",
    "RoutingWriteError",
    "read_routing",
    "write_task_override",
]
