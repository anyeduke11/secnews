"""skill_runner.dispatch — A/B fast-path + C/D pipeline 执行器 (B2).

设计纪律:
- A/B 类 → ``dispatch_fast(skill, inputs)`` 直调 target (ServiceTarget /
  ApiTarget), 不调 LLM, 不经过 agent_loop 五阶段, 返回原始产物 dict.
- C/D 类 → ``dispatch_pipeline(skill, inputs, ctx)`` 走完整 pipeline:
    step kind="service"  → importlib + getattr 反射调 service
    step kind="llm"      → LLMPort.complete (由 ctx 注入)
    step kind="wiki"     → 渲染路径模板 + 落 llm-wiki-2.0/
- ApiTarget 通过进程内 httpx.Client 调本机 backend (反 import 禁令).
- ServiceTarget.class_name 为 None 时按模块级函数调.
- prompt_template 仅 C/D 类有, 用于填充 step.kind="llm" 的 prompt.
- args 模板支持 ``{{ input.X }}`` / ``{{ steps.N.output }}`` / ``{{ run.date }}``
  三类占位 (B5 接线时由更多 fixture 验证).

非目标 (B2 不做):
- LLM provider 选择 — 走 LLMPort 协议, 默认 build_default_llm_port().
- Wiki 内容校验 — wiki_fs.write_item 已含原子写 + FTS 同步.
- 并发跑多 step — skill 语义是顺序, 不引入 async/await.
"""
from __future__ import annotations

import importlib
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from backend.logging_config import logger
from backend.services.agent_loop import LLMPort, build_default_llm_port
from backend.services.skill_registry.core import (
    ApiTarget,
    ServiceTarget,
    SkillDef,
    Step,
)


# ---------------------------------------------------------------------------
# Template rendering — args / path 模板占位
# ---------------------------------------------------------------------------
_TEMPLATE_RE = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_.]*)\s*\}\}")


def _render_template(
    template: Any,
    *,
    inputs: dict[str, Any],
    step_outputs: list[dict[str, Any]],
) -> Any:
    """递归渲染 ``{{ X }}`` 占位。

    支持的 X:
      - input.X        → inputs.get("X")
      - steps.<i>.output → step_outputs[i].get("output")
      - run.date       → 当日 YYYY-MM-DD
      - run.datetime   → 当前 datetime ISO 字符串

    非 str 类型 (dict/list) 递归走字段; 渲染失败保留原占位字符串便于调试.
    """
    if isinstance(template, str):
        # 单占位且完全等于模板 → 直接返回原值类型 (避免 1 → "1")
        m = _TEMPLATE_RE.fullmatch(template.strip())
        if m:
            key = m.group(1)
            val = _resolve_key(key, inputs=inputs, step_outputs=step_outputs)
            if val is not None:
                return val
        # 否则字符串内插值
        def _replace(match: re.Match) -> str:
            key = match.group(1)
            v = _resolve_key(key, inputs=inputs, step_outputs=step_outputs)
            return str(v) if v is not None else match.group(0)

        return _TEMPLATE_RE.sub(_replace, template)
    if isinstance(template, dict):
        return {
            k: _render_template(v, inputs=inputs, step_outputs=step_outputs)
            for k, v in template.items()
        }
    if isinstance(template, list):
        return [
            _render_template(v, inputs=inputs, step_outputs=step_outputs)
            for v in template
        ]
    return template


def _resolve_key(
    key: str,
    *,
    inputs: dict[str, Any],
    step_outputs: list[dict[str, Any]],
) -> Any | None:
    """单 key 解析 — 返回 None 表示未识别 (调用方决定是否回退原占位)."""
    if key.startswith("input."):
        return inputs.get(key[len("input."):])
    if key.startswith("steps."):
        # steps.<i>.<field>
        parts = key.split(".", 2)
        if len(parts) >= 3:
            try:
                idx = int(parts[1])
            except ValueError:
                return None
            if not (0 <= idx < len(step_outputs)):
                return None
            return step_outputs[idx].get(parts[2])
        return None
    if key == "run.date":
        return datetime.now().strftime("%Y-%m-%d")
    if key == "run.datetime":
        return datetime.now().isoformat()
    return None


# ---------------------------------------------------------------------------
# ServiceTarget / ApiTarget — 反射执行
# ---------------------------------------------------------------------------
def _resolve_service_target(target: ServiceTarget) -> Any:
    """反射: 返回 ``module.class_name().method`` 或 ``module.method`` 绑定函数.

    失败抛 RuntimeError (含 module/class/method 便于排查).
    """
    try:
        module = importlib.import_module(target.module)
    except ImportError as e:
        raise RuntimeError(
            f"ServiceTarget module import failed: {target.module!r}"
        ) from e
    if target.class_name is None:
        # 模块级函数
        fn = getattr(module, target.method, None)
        if fn is None:
            raise RuntimeError(
                f"ServiceTarget method not found: {target.module}.{target.method}"
            )
        return fn
    # 实例方法 — 拿类, 实例化
    cls = getattr(module, target.class_name, None)
    if cls is None:
        raise RuntimeError(
            f"ServiceTarget class not found: {target.module}.{target.class_name}"
        )
    instance = cls()
    fn = getattr(instance, target.method, None)
    if fn is None:
        raise RuntimeError(
            f"ServiceTarget method not found: "
            f"{target.module}.{target.class_name}.{target.method}"
        )
    return fn


def _invoke_service(
    target: ServiceTarget,
    args: dict[str, Any] | None,
    *,
    inputs: dict[str, Any],
    step_outputs: list[dict[str, Any]],
) -> dict[str, Any]:
    """执行 service target, 返回 dict 形式产物 (output 字段).

    约定: 反射函数返回值是 dict 时直接透传; 否则包成 ``{"output": ret}``.
    args 渲染后整体传参 (命名参数), 反射函数需签名一致.

    支持 async: 若反射函数是 coroutinefunction, 在 event loop 状态用
    ``loop.run_until_complete`` (业务层无 await 上下文) 同步执行; 如当前
    已在 event loop 中则抛 RuntimeError — 提示调用方换异步入口.
    """
    fn = _resolve_service_target(target)
    rendered = _render_template(args or {}, inputs=inputs, step_outputs=step_outputs) or {}
    raw = _maybe_await(fn(**rendered))
    if isinstance(raw, dict):
        # 同步保证 output 键存在 — 服务字典无 output 时整字典塞 output=raw (str repr)
        out = dict(raw)
        out.setdefault("output", raw)
        return out
    return {"output": raw}


def _maybe_await(value: Any) -> Any:
    """协程结果就地等待 — 同步入口 (skill_runner.fast_path 必经此处).

    - 普通返回值: 原样返回
    - coroutine: 当前 event loop 不存在 → run_until_complete;
                  已存在 → 抛 RuntimeError (避免 sync→async 静默死循环)
    """
    if not hasattr(value, "__await__"):
        return value
    import asyncio as _asyncio

    try:
        loop = _asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop is not None:
        raise RuntimeError(
            "skill_runner 不支持在已有 event loop 中调 async service target;"
            " 请将 skill_runner 放到同步入口, 或为该 skill 写同步包装"
        )
    return _asyncio.run(value)


def _invoke_api(
    target: ApiTarget,
    args: dict[str, Any] | None,
    *,
    inputs: dict[str, Any],
    step_outputs: list[dict[str, Any]],
) -> dict[str, Any]:
    """进程内 httpx 调本机 backend endpoint (B 类查询专用).

    默认 base_url 经 ``backend.config.config.api_base_url`` 解析;
    args 渲染后按 method 区分: GET → query params / POST/PUT → json body.
    """
    import httpx

    from backend.config import config

    rendered = _render_template(args or {}, inputs=inputs, step_outputs=step_outputs) or {}
    base_url = getattr(config, "api_base_url", "http://127.0.0.1:8000")
    url = f"{base_url.rstrip('/')}/{target.path.lstrip('/')}"
    method = target.http_method.upper()
    try:
        with httpx.Client(timeout=30.0) as client:
            if method == "GET":
                resp = client.get(url, params=rendered)
            elif method == "POST":
                resp = client.post(url, json=rendered)
            elif method == "PUT":
                resp = client.put(url, json=rendered)
            elif method == "DELETE":
                resp = client.delete(url, params=rendered)
            else:
                raise RuntimeError(f"unsupported http method: {method}")
    except Exception as e:
        raise RuntimeError(f"ApiTarget call failed: {method} {url}: {e}") from e
    try:
        body = resp.json()
    except Exception:
        body = {"raw": resp.text}
    return {"status_code": resp.status_code, "output": body}


# ---------------------------------------------------------------------------
# Step execution — pipeline 步骤通用执行
# ---------------------------------------------------------------------------
@dataclass
class StepOutcome:
    """单步执行结果 — pipeline dispatcher 的最小聚合单元."""

    step_index: int
    kind: str
    output: dict[str, Any]
    llm_tokens: int = 0


def execute_step(
    step: Step,
    *,
    step_index: int,
    inputs: dict[str, Any],
    step_outputs: list[dict[str, Any]],
    skill: SkillDef,
    llm: LLMPort,
    run_date: str,
) -> StepOutcome:
    """执行一个 Step — service/llm/wiki 三类分支.

    - kind="service": 走 ServiceTarget 反射
    - kind="llm":     prompt_template 优先 step 自身 → skill.prompt_template →
                      拼接 inputs; 调 llm.complete
    - kind="wiki":    渲染 path/content + 落 llm-wiki-2.0/
    """
    if step.kind == "service":
        if step.target is None:
            raise RuntimeError(f"step[{step_index}] service: target 缺失")
        output = _invoke_service(
            step.target, step.args, inputs=inputs, step_outputs=step_outputs
        )
        return StepOutcome(step_index=step_index, kind="service", output=output)
    if step.kind == "llm":
        prompt = step.prompt_template or skill.prompt_template
        if not prompt:
            raise RuntimeError(
                f"step[{step_index}] llm: prompt_template 缺失 (skill/skill_runner)"
            )
        rendered = _render_template(
            prompt, inputs=inputs, step_outputs=step_outputs
        )
        result = llm.complete(rendered)
        text = result.get("text", "")
        tokens = int(result.get("tokens", 0) or 0)
        # 同时提供 output 键, 让模板 {{ steps.N.output }} 直接拿到文本
        return StepOutcome(
            step_index=step_index,
            kind="llm",
            output={"output": text, "text": text, "prompt": rendered},
            llm_tokens=tokens,
        )
    if step.kind == "wiki":
        if step.path is None or step.content is None:
            raise RuntimeError(f"step[{step_index}] wiki: path/content 缺失")
        path = _render_template(
            step.path, inputs=inputs, step_outputs=step_outputs
        )
        content = _render_template(
            step.content, inputs=inputs, step_outputs=step_outputs
        )
        # 写入 wiki (wiki-first 哲学: 路径为相对 llm-wiki-2.0/)
        wiki_path = _write_wiki(path=path, content=content, run_date=run_date)
        return StepOutcome(
            step_index=step_index, kind="wiki", output={"path": wiki_path, "content": content}
        )
    raise RuntimeError(f"step[{step_index}] unknown kind: {step.kind!r}")


# ---------------------------------------------------------------------------
# Wiki 落盘 (wiki-first: llm-wiki-2.0/ 为唯一知识存档)
# ---------------------------------------------------------------------------
def _write_wiki(*, path: str, content: str, run_date: str) -> str:
    """落 wiki 文件 — frontmatter 最小三字段 (id/created/source).

    path 支持两种形态:
      - 绝对路径 → 直接写
      - 相对路径 → 拼到 llm-wiki-2.0/ 根 (env HOTSPOT_WIKI_ROOT 可覆盖, 测试用)
    """
    from backend.wiki_fs.root import resolve_wiki_root

    if path.startswith("/") or (len(path) > 1 and path[1] == ":"):
        full_path = path
    else:
        root = resolve_wiki_root()
        full_path = f"{root.rstrip('/')}/{path.lstrip('/')}"

    # 渲染 frontmatter — 简化: id 取 path basename, created=run_date, source=skill-runner
    import datetime as _dt
    fm = {
        "id": full_path.rsplit("/", 1)[-1].rsplit(".", 1)[0],
        "created": run_date,
        "source": "skill-runner",
        "ingested_at": _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    fm_str = "<!-- metadata\n" + "\n".join(f"{k}: {v}" for k, v in fm.items()) + "\n-->\n"
    try:
        import os
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(fm_str + content)
    except OSError as e:
        logger.warning(
            "skill_runner wiki write failed",
            extra={"trace_id": "", "path": full_path, "error": str(e)},
        )
        # 落盘失败不阻断 run 主流程, 把 path 退回 path 字符串便于 debug
        return path
    return full_path


# ---------------------------------------------------------------------------
# Fast-path — A/B 类直调
# ---------------------------------------------------------------------------
def dispatch_fast(skill: SkillDef, inputs: dict[str, Any]) -> dict[str, Any]:
    """A/B 类 fast-path: resolve→execute→commit 直调 target (零 LLM token).

    - target=ServiceTarget → importlib + getattr 反射调
    - target=ApiTarget     → 进程内 httpx 调本机
    返回值: dict (由反射函数决定结构, 通常含 'output' 或具名字段).
    """
    if skill.target is None:
        raise RuntimeError(
            f"A/B fast-path 需 target; skill={skill.id!r} pipeline={skill.pipeline!r}"
        )
    if isinstance(skill.target, ServiceTarget):
        return _invoke_service(skill.target, inputs, inputs=inputs, step_outputs=[])
    if isinstance(skill.target, ApiTarget):
        return _invoke_api(skill.target, inputs, inputs=inputs, step_outputs=[])
    raise RuntimeError(f"unknown target type: {type(skill.target).__name__}")


# ---------------------------------------------------------------------------
# Pipeline — C/D 类按序执行
# ---------------------------------------------------------------------------
def dispatch_pipeline(
    skill: SkillDef,
    inputs: dict[str, Any],
    *,
    llm: LLMPort | None = None,
) -> dict[str, Any]:
    """C/D 类走完整 pipeline — 按 step 顺序执行, 收集 step_outputs.

    返回 dict 含:
      - "step_outputs": list[dict] 每步产物
      - "wiki_path": str | None (最后一个 wiki 步的产物, RunHistory 直读)
      - "llm_tokens": int 累计 LLM token
    """
    if not skill.pipeline:
        raise RuntimeError(f"C/D pipeline 需 pipeline; skill={skill.id!r}")
    llm = llm or build_default_llm_port()
    run_date = datetime.now().strftime("%Y-%m-%d")

    step_outputs: list[dict[str, Any]] = []
    wiki_path: str | None = None
    llm_tokens = 0

    for idx, step in enumerate(skill.pipeline):
        outcome = execute_step(
            step,
            step_index=idx,
            inputs=inputs,
            step_outputs=step_outputs,
            skill=skill,
            llm=llm,
            run_date=run_date,
        )
        step_outputs.append(outcome.output)
        llm_tokens += outcome.llm_tokens
        if outcome.kind == "wiki" and "path" in outcome.output:
            wiki_path = outcome.output["path"]

    return {
        "step_outputs": step_outputs,
        "wiki_path": wiki_path,
        "llm_tokens": llm_tokens,
    }


__all__ = [
    "StepOutcome",
    "dispatch_fast",
    "dispatch_pipeline",
    "execute_step",
    "render_template",
]


# 反向兼容别名 — B5 e2e 可能直接调用
render_template = _render_template