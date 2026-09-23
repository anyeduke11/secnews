# 采集管线 LLM 能力 pi 化 + 补齐 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** pi 成为 ai_hub 第 5 种 provider type；采集管线补齐语义门禁 / 智能分类增援 / NER 实体抽取三项能力（全 feature gate 默认关）。

**Architecture:** 双通道统一 — 管线 LLM 走 ai_hub（pi provider 子进程 `pi -p --mode json`，NDJSON 解析与 agent_bridge 共享单点实现）；agent_bridge 仅扩注册表 task_types。三新能力挂点：`info_filter_gate.filter_items`（neutral → verdict-only 判别）、`auto_classifier.classify_item_with_ai`（规则 miss 增援）、`t1_raw_to_refine`（score 成功后实体落库）。

**Tech Stack:** Python 3 / FastAPI / SQLite / Pydantic / pytest。Spec: `docs/superpowers/specs/2026-09-18-pipeline-llm-pi-provider-design.md`。

**计划阶段核实结论（覆盖 spec 两处待核实项）:**
1. `generate(task="semantic_filter")` 无需 schema 改动：`_try_order("semantic_filter")` 走默认 fallback 链，`_resolve_model` 未知 task 回落 `cfg.models.score` — 可接受。
2. 前端零改动确认：`api/llm_status.py` L33-42 对 providers 泛型遍历（无 type 白名单），pi provider 自动展示。

---

### Task 1: pi_transport.py — NDJSON 共享解析 + print 子进程

**Files:**
- Create: `backend/services/ai_hub/pi_transport.py`
- Modify: `backend/services/agent_bridge.py:83-126`（`_parse_jsonl_events` 改为委托）
- Test: `backend/tests/test_pi_transport.py`

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/test_pi_transport.py
"""pi_transport 单测 — NDJSON 解析契约 (与 agent_bridge 2026-09-05 实测对齐) + print 子进程。"""
import subprocess
import pytest

from backend.services.ai_hub.pi_transport import parse_pi_jsonl_events, run_pi_print


class TestParsePiJsonlEvents:
    def test_message_end_assistant_text(self):
        stdout = "\n".join([
            '{"type":"session","id":"s1"}',
            '{"type":"agent_start"}',
            '{"type":"message_end","message":{"role":"assistant","content":[{"type":"text","text":"你好"}]}}',
        ])
        assert parse_pi_jsonl_events(stdout) == "你好"

    def test_user_message_end_skipped(self):
        """实测缺口①: user 消息也发 message_end — 不算结果。"""
        stdout = "\n".join([
            '{"type":"message_end","message":{"role":"user","content":[{"type":"text","text":"问题"}]}}',
            '{"type":"message_end","message":{"role":"assistant","content":[{"type":"text","text":"答案"}]}}',
        ])
        assert parse_pi_jsonl_events(stdout) == "答案"

    def test_stop_reason_error_returns_none(self):
        """实测缺口②: 上游 429 时 pi rc=0 但 stopReason=error — 显式失败。"""
        stdout = '{"type":"message_end","message":{"role":"assistant","stopReason":"error","content":[]}}'
        assert parse_pi_jsonl_events(stdout) is None

    def test_non_json_lines_fallback_to_last_json(self):
        assert parse_pi_jsonl_events('garbage\n{"result":"x"}') == '{"result":"x"}'

    def test_empty_stdout(self):
        assert parse_pi_jsonl_events("") is None


class TestRunPiPrint:
    def test_model_empty_omits_flag(self, monkeypatch):
        captured = {}

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            return subprocess.CompletedProcess(cmd, 0, stdout='{"type":"message_end","message":{"role":"assistant","content":[{"type":"text","text":"ok"}]}}', stderr="")

        monkeypatch.setattr(subprocess, "run", fake_run)
        out = run_pi_print("提示词", "", 60)
        assert out == "ok"
        assert captured["cmd"] == ["pi", "-p", "--mode", "json"]
        assert kwargs_stdin(captured)  # stdin 收到 prompt

    def test_model_passed(self, monkeypatch):
        captured = {}

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            return subprocess.CompletedProcess(cmd, 0, stdout='{"type":"message_end","message":{"role":"assistant","content":[{"type":"text","text":"ok"}]}}', stderr="")

        monkeypatch.setattr(subprocess, "run", fake_run)
        run_pi_print("p", "claude-sonnet-4-5", 30)
        assert captured["cmd"] == ["pi", "-p", "--mode", "json", "--model", "claude-sonnet-4-5"]

    def test_nonzero_exit_raises(self, monkeypatch):
        monkeypatch.setattr(
            subprocess, "run",
            lambda cmd, **kw: subprocess.CompletedProcess(cmd, 1, stdout="", stderr="boom"),
        )
        with pytest.raises(RuntimeError, match="rc=1"):
            run_pi_print("p", "", 10)

    def test_error_stop_reason_raises(self, monkeypatch):
        """stopReason=error (pi rc=0) 必须抛错 — 让 gateway 健康窗口记账。"""
        monkeypatch.setattr(
            subprocess, "run",
            lambda cmd, **kw: subprocess.CompletedProcess(
                cmd, 0,
                stdout='{"type":"message_end","message":{"role":"assistant","stopReason":"error","content":[]}}',
                stderr=""),
        )
        with pytest.raises(RuntimeError, match="无效输出"):
            run_pi_print("p", "", 10)


def kwargs_stdin(captured):
    return True  # stdin 断言在 fake_run 的 kwargs 里不易捕获, 由 input= 参数契约保证
```

注：`kwargs_stdin` 辅助很弱 — 删掉它和对应 assert 行，`input=prompt` 契约由 `run_pi_print` 实现内 `subprocess.run(..., input=prompt, ...)` 静态保证（monkeypatch 的 fake_run 若缺 input kwarg 会 TypeError，test_model_empty_omits_flag 的 fake_run 签名 `**kwargs` 已兼容）。**最终测试文件不含 `kwargs_stdin`。**

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest backend/tests/test_pi_transport.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.services.ai_hub.pi_transport'`

- [ ] **Step 3: 实现 pi_transport.py**

```python
"""pi 传输层 — NDJSON 解析共享纯函数 + print 模式子进程 (2026-09-18 方案 B)。

NDJSON 解析自 agent_bridge._parse_jsonl_events 提取为单点实现:
ai_hub pi provider (gateway type=="pi") 与 agent_bridge jsonl 协议共用,
禁止两处实现。协议契约来自 2026-09-05 pi 0.84.4 live 实测 (V0.8.1 D-d):
- user 消息也发 message_end → role=="user" 跳过;
- 上游 429 时 pi 仍 rc=0, assistant message_end 带 stopReason=="error"
  且 content=[] → 解析返回 None (调用方视为失败)。

认证: ``~/.pi/agent/auth.json`` 由 pi 自管, 本模块不触碰任何密钥。
prompt 经 stdin 传入 (防 ARG_MAX / 命令注入), 不走 argv。
"""
from __future__ import annotations

import json
import subprocess


def parse_pi_jsonl_events(stdout: str) -> str | None:
    """pi `--mode json` NDJSON 事件流 → 最终文本 (None = 失败/空流)。"""
    final_text: str | None = None
    last_json_text: str | None = None
    assistant_errored = False
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        last_json_text = line
        if event.get("type") == "message_end":
            message = event.get("message", {})
            if message.get("role") == "user":
                continue  # 实测缺口①: 用户回显不算结果
            if message.get("stopReason") == "error":
                assistant_errored = True  # 实测缺口②: 上游失败
                continue
            content = message.get("content", [])
            texts = [
                seg.get("text", "") for seg in content
                if isinstance(seg, dict) and seg.get("type") == "text"
            ]
            if texts:
                final_text = "\n".join(t for t in texts if t)
    if final_text:
        return final_text
    if assistant_errored:
        return None  # 上游失败显式失败, 不退化成 JSON 行假阳性
    return last_json_text


def run_pi_print(prompt: str, model: str, timeout_seconds: int = 60) -> str:
    """同步执行 `pi -p --mode json [--model M]`, prompt 走 stdin, 返回最终文本。

    任何失败 (非零退出 / stopReason=error / 空流 / 超时) 都抛异常 —
    gateway._call_provider 的健康窗口 / 熔断记账依赖异常路径。
    """
    cmd = ["pi", "-p", "--mode", "json"]
    if model:
        cmd += ["--model", model]
    try:
        proc = subprocess.run(
            cmd, input=prompt, capture_output=True, text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(f"pi timeout after {timeout_seconds}s") from e
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip()[-300:]
        raise RuntimeError(f"pi exit rc={proc.returncode}: {tail}")
    result = parse_pi_jsonl_events(proc.stdout)
    if result is None:
        raise RuntimeError("pi 无有效输出 (上游失败或空流)")
    return result


__all__ = ["parse_pi_jsonl_events", "run_pi_print"]
```

- [ ] **Step 4: agent_bridge 委托共享实现（行为不变）**

`backend/services/agent_bridge.py` L83-126 的 `_parse_jsonl_events` 函数体替换为委托（docstring 移入 pi_transport，此处留一行）：

```python
def _parse_jsonl_events(stdout: str) -> str | None:
    """pi NDJSON 解析 — 单点实现已提取到 ai_hub.pi_transport (方案 B 共享)。"""
    from backend.services.ai_hub.pi_transport import parse_pi_jsonl_events
    return parse_pi_jsonl_events(stdout)
```

- [ ] **Step 5: 运行新测试 + agent_bridge 回归**

Run: `python -m pytest backend/tests/test_pi_transport.py backend/tests/test_agent_bridge.py -v`
Expected: 全 PASS（agent_bridge 既有测试行为不变；若无 test_agent_bridge.py 则跑 `python -m pytest backend/tests/ -k agent_bridge -v`）

- [ ] **Step 6: Commit**

```bash
git add backend/services/ai_hub/pi_transport.py backend/services/agent_bridge.py backend/tests/test_pi_transport.py
git commit -m "feat(ai_hub): pi_transport — NDJSON 解析单点提取 + pi print 子进程传输"
```

---

### Task 2: llm_schema 接受 type "pi"

**Files:**
- Modify: `backend/config/llm_schema.py:50`
- Test: `backend/tests/test_pi_transport.py`（追加）

- [ ] **Step 1: 追加失败测试**

```python
# 追加到 backend/tests/test_pi_transport.py
from pydantic import ValidationError
from backend.config.llm_schema import LLMConfig, ProviderConfig, ProviderModels


def test_llm_schema_accepts_pi_type():
    cfg = ProviderConfig(type="pi", models=ProviderModels(score="", ner="", summary=""))
    assert cfg.type == "pi"


def test_llm_schema_rejects_unknown_type():
    with pytest.raises(ValidationError):
        ProviderConfig(type="pi_dev", models=ProviderModels())


def test_llm_config_full_yaml_pi(tmp_path):
    yaml_file = tmp_path / "llm.yaml"
    yaml_file.write_text(
        """
enabled: true
default_provider: pi
fallback_order: [pi]
providers:
  pi:
    type: pi
    models: {score: "", ner: "", summary: ""}
    timeout_seconds: 60
    max_concurrent: 2
""",
        encoding="utf-8",
    )
    cfg = LLMConfig.model_validate(
        __import__("yaml").safe_load(yaml_file.read_text(encoding="utf-8"))
    )
    assert cfg.providers["pi"].type == "pi"
    assert cfg.providers["pi"].max_concurrent == 2
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest backend/tests/test_pi_transport.py -k schema -v`
Expected: FAIL — ValidationError（"pi" 不在 Literal）

- [ ] **Step 3: 改 Literal**

`backend/config/llm_schema.py` L50:

```python
    # 2026-09-18 方案 B: +pi (pi.dev agent harness, 认证自管 ~/.pi/agent/auth.json,
    # 无 base_url / api_key_env 语义; 传输见 ai_hub/pi_transport.py)
    type: Literal["ollama", "openai", "openai_compatible", "anthropic", "pi"]
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest backend/tests/test_pi_transport.py -v`
Expected: 全 PASS

- [ ] **Step 5: Commit**

```bash
git add backend/config/llm_schema.py backend/tests/test_pi_transport.py
git commit -m "feat(llm_schema): provider type Literal 增 pi"
```

---

### Task 3: gateway `_call_provider` pi 分支

**Files:**
- Modify: `backend/services/ai_hub/gateway.py`（L14-18 import 区 + L587-607 dispatch）
- Test: `backend/tests/test_pi_transport.py`（追加）

- [ ] **Step 1: 追加失败测试**

```python
# 追加到 backend/tests/test_pi_transport.py
import asyncio
from backend.services.ai_hub.gateway import LLMService


def _pi_cfg():
    return ProviderConfig(
        type="pi", models=ProviderModels(score="", ner="", summary=""),
        timeout_seconds=15, max_concurrent=1,
    )


def test_gateway_call_provider_pi(monkeypatch):
    calls = {}

    def fake_run_pi_print(prompt, model, timeout_seconds):
        calls.update(prompt=prompt, model=model, timeout_seconds=timeout_seconds)
        return "pi 回答"

    monkeypatch.setattr(
        "backend.services.ai_hub.pi_transport.run_pi_print", fake_run_pi_print
    )
    out = asyncio.run(LLMService()._call_provider(
        _pi_cfg(), "", "你好", provider_name="pi_test",
    ))
    assert out == "pi 回答"
    assert calls == {"prompt": "你好", "model": "", "timeout_seconds": 15}


def test_gateway_call_provider_pi_error_propagates(monkeypatch):
    """pi 失败必须上抛 — _call_provider 异常路径记健康窗口后抛给 fallback 循环。"""
    def fake_fail(prompt, model, timeout_seconds):
        raise RuntimeError("pi exit rc=1: boom")

    monkeypatch.setattr(
        "backend.services.ai_hub.pi_transport.run_pi_print", fake_fail
    )
    with pytest.raises(RuntimeError, match="boom"):
        asyncio.run(LLMService()._call_provider(
            _pi_cfg(), "", "你好", provider_name="pi_test",
        ))


def test_gateway_chat_unsupported_pi():
    """_call_provider_chat 不支持 pi → ValueError → fallback 链跳下一 provider (spec §3.2 明确不做)。"""
    with pytest.raises(ValueError, match="Unsupported provider type for chat: pi"):
        asyncio.run(LLMService()._call_provider_chat(
            _pi_cfg(), "", [{"role": "user", "content": "x"}],
        ))
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest backend/tests/test_pi_transport.py -k gateway -v`
Expected: FAIL — `Unsupported provider type: pi`

- [ ] **Step 3: 实现 dispatch 分支**

`backend/services/ai_hub/gateway.py`：

(a) import 区（L14-18）补 `import asyncio`（当前模块只有 json/logging/time/pathlib/typing/httpx）。

(b) `_call_provider` L601 `elif cfg.type == "anthropic":` 块之后、L606 `else:` 之前插入：

```python
                elif cfg.type == "pi":
                    # 2026-09-18 方案 B: pi provider — 子进程 pi -p --mode json,
                    # NDJSON 解析与 agent_bridge 共享 (pi_transport 单点)。
                    # 失败抛异常 → 上方 except 记健康窗口 → fallback 下一 provider。
                    from backend.services.ai_hub.pi_transport import run_pi_print

                    result = await asyncio.to_thread(
                        run_pi_print, prompt, model, cfg.timeout_seconds
                    )
```

`_call_provider_chat` **不加分支**（现有 L696 `raise ValueError(f"Unsupported provider type for chat: {cfg.type}")` 对 pi 自然生效）。

- [ ] **Step 4: 运行确认通过 + ai_hub 回归**

Run: `python -m pytest backend/tests/test_pi_transport.py -v && python -m pytest backend/tests/ -k "ai_hub or gateway or llm" -q`
Expected: 全 PASS

- [ ] **Step 5: Commit**

```bash
git add backend/services/ai_hub/gateway.py backend/tests/test_pi_transport.py
git commit -m "feat(ai_hub): gateway pi provider 分支 — stdin 子进程 + to_thread, chat 场景明确不支持"
```

---

### Task 4: agents.yaml 注册 score/classify/ner

**Files:**
- Modify: `config/agents.yaml`（pi runner `task_types`）
- Test: `backend/tests/test_pi_transport.py`（追加）

- [ ] **Step 1: 追加失败测试**

```python
# 追加到 backend/tests/test_pi_transport.py
from backend.config.agent_runner_schema import load_agents_config


def test_agents_yaml_pi_registers_pipeline_task_types():
    cfg = load_agents_config()
    assert cfg is not None
    pi = cfg.agents["pi"]
    assert set(pi.task_types) >= {"execute", "score", "classify", "ner"}
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest backend/tests/test_pi_transport.py -k agents_yaml -v`
Expected: FAIL — assertion error（task_types 只有 execute）

- [ ] **Step 3: 改 agents.yaml**

`config/agents.yaml` pi runner：

```yaml
  pi:
    command: ["pi", "-p", "--mode", "json"]
    protocol: jsonl
    cwd: "{workspace}"
    # 2026-09-18 方案 B: +score/classify/ner — dsh / 手动任务可路由;
    # 管线内消费仍走 ai_hub (LLM 单出口), 本通道只服务 agent 任务面
    task_types: [execute, score, classify, ner]
    timeout_seconds: 600
```

（保持缩进与文件既有风格一致；只改 `task_types` 一行 + 注释。）

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest backend/tests/test_pi_transport.py -v && python -m pytest backend/tests/ -k agent -q`
Expected: 全 PASS

- [ ] **Step 5: Commit**

```bash
git add config/agents.yaml backend/tests/test_pi_transport.py
git commit -m "feat(agents): pi runner 注册 score/classify/ner 任务面"
```

---

### Task 5: 三个 feature gate 登记（默认关）

**Files:**
- Modify: `backend/config/feature_gates.toml`（`[extensions]` 末尾 +3 行）
- Modify: `backend/extensions/__init__.py:30-56`（`_EXTENSION_NAMES` +3 名）
- Test: `backend/tests/test_pipeline_llm_gates.py`（新建）

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/test_pipeline_llm_gates.py
"""管线 LLM 三 gate (semantic_filter / ai_classify / pipeline_ner) 登记与默认态。

契约 (user_skills 先例): gate 化须随消费点同时登记 — 不登记则 TOML/env
同名 key 被 _load_gates 过滤, is_extension_enabled 恒 False (fail-closed)。
"""
import os

import pytest

from backend.extensions import _EXTENSION_NAMES, is_extension_enabled, reset_gates

PIPELINE_GATES = ("semantic_filter", "ai_classify", "pipeline_ner")


def test_three_gates_registered():
    for name in PIPELINE_GATES:
        assert name in _EXTENSION_NAMES, f"{name} 未登记 — TOML 键会被过滤恒 False"


def test_default_off_in_toml(monkeypatch):
    """生产默认关: 不设 env 时三 gate 读 TOML false。"""
    monkeypatch.delenv("HOTSPOT_FEATURE_GATES", raising=False)
    reset_gates()
    for name in PIPELINE_GATES:
        assert is_extension_enabled(name) is False
    reset_gates()


@pytest.mark.parametrize("gate", PIPELINE_GATES)
def test_env_override_on(monkeypatch, gate):
    monkeypatch.setenv(
        "HOTSPOT_FEATURE_GATES", f'{{"extensions": {{"{gate}": true}}}}'
    )
    reset_gates()
    assert is_extension_enabled(gate) is True
    reset_gates()
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest backend/tests/test_pipeline_llm_gates.py -v`
Expected: FAIL — `semantic_filter 未登记`

- [ ] **Step 3: 登记**

(a) `backend/extensions/__init__.py` `_EXTENSION_NAMES` 元组末尾（`"interest_engine",` 之后）追加：

```python
    # 2026-09-18 方案 B: 管线 LLM 三能力 — 语义门禁 / 分类增援 / NER 实体抽取。
    # 全部默认关; 消费点: info_filter_gate.filter_items / auto_classifier /
    # t1_raw_to_refine (spec: docs/superpowers/specs/2026-09-18-*.md)
    "semantic_filter",
    "ai_classify",
    "pipeline_ner",
```

(b) `backend/config/feature_gates.toml` `interest_engine` 块之后追加：

```toml
semantic_filter = false  # 2026-09-18 方案 B — 采集语义门禁 (info_filter 规则 neutral 时 LLM verdict-only 判别)
ai_classify = false      # 2026-09-18 方案 B — 智能分类增援 (auto_classifier 规则 miss 时 LLM 补 domain)
pipeline_ner = false     # 2026-09-18 方案 B — NER 实体抽取 (t1 score 成功后 extract_entities 落库)
```

**注意：不把三 gate 加进 conftest 全开 env** — 测试默认关保证"gate 关 = 行为与现状一致"可被验证；需要开的用例自行 env + reset_gates。

- [ ] **Step 4: 运行确认通过 + gates 矩阵回归**

Run: `python -m pytest backend/tests/test_pipeline_llm_gates.py backend/tests/test_feature_gates.py -v`
Expected: 全 PASS

- [ ] **Step 5: Commit**

```bash
git add backend/extensions/__init__.py backend/config/feature_gates.toml backend/tests/test_pipeline_llm_gates.py
git commit -m "feat(gates): 登记管线 LLM 三 gate (semantic_filter/ai_classify/pipeline_ner, 默认关)"
```

---

### Task 6: 语义门禁 — semantic_verdict + filter_items 挂点

**Files:**
- Modify: `backend/services/ai_hub/tasks.py`（新增 prompt + 解析 + `semantic_verdict`）
- Modify: `backend/services/info_filter_gate.py`（`filter_items` neutral 分支）
- Test: `backend/tests/test_semantic_filter_gate.py`（新建）

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/test_semantic_filter_gate.py
"""语义门禁 (gate semantic_filter) — info_filter 规则 neutral 时的 LLM verdict 判别。

契约: 仅 neutral 触发; verdict=reject → drop; LLM 失败/解析失败 →
fail-open 保留 (门禁故障不丢内容); gate 关 → 零 LLM 调用行为不变。
"""
import asyncio

import pytest

from backend.extensions import reset_gates
from backend.services import info_filter_gate
from backend.services.ai_hub import tasks as ai_tasks


@pytest.fixture(autouse=True)
def _gate_toggle():
    yield
    reset_gates()


def _enable(monkeypatch):
    monkeypatch.setenv(
        "HOTSPOT_FEATURE_GATES", '{"extensions": {"info_filter": true, "semantic_filter": true}}'
    )
    reset_gates()


def _neutral_rules(monkeypatch):
    monkeypatch.setattr(info_filter_gate, "_load_rules_cached", lambda: [{"id": 1}])
    import backend.services.info_filter_service as svc
    monkeypatch.setattr(svc, "evaluate", lambda rules, **kw: ("neutral", None))


def _fake_generate(payload: str, fail: bool = False):
    async def _gen(prompt, *, task="summary", **kw):
        assert task == "semantic_filter"
        if fail:
            raise RuntimeError("all providers failed")
        return payload
    return _gen


ITEM = {"source_name": "测试源", "title": "标题", "summary": "摘要"}


class TestSemanticVerdict:
    def test_parse_allow(self, monkeypatch):
        monkeypatch.setattr(
            ai_tasks.llm_service_ref(), "generate", _fake_generate('{"verdict":"allow","reason":"ok"}'),
        )
        assert ai_tasks.semantic_verdict("内容")["verdict"] == "allow"

    def test_parse_reject(self, monkeypatch):
        monkeypatch.setattr(
            ai_tasks.llm_service_ref(), "generate", _fake_generate('前置噪声 {"verdict":"reject","reason":"广告"} 尾部'),
        )
        assert ai_tasks.semantic_verdict("内容")["verdict"] == "reject"

    def test_parse_failure_fail_open(self, monkeypatch):
        monkeypatch.setattr(
            ai_tasks.llm_service_ref(), "generate", _fake_generate("不是 JSON"),
        )
        assert ai_tasks.semantic_verdict("内容")["verdict"] == "allow"

    def test_llm_failure_fail_open(self, monkeypatch):
        monkeypatch.setattr(
            ai_tasks.llm_service_ref(), "generate", _fake_generate("", fail=True),
        )
        assert ai_tasks.semantic_verdict("内容")["verdict"] == "allow"


class TestFilterItemsSemanticLayer:
    def test_gate_off_no_llm(self, monkeypatch):
        monkeypatch.delenv("HOTSPOT_FEATURE_GATES", raising=False)
        reset_gates()
        _neutral_rules(monkeypatch)
        called = {"n": 0}
        monkeypatch.setattr(
            ai_tasks.llm_service_ref(), "generate",
            async_fail_counter(called),
        )
        kept = info_filter_gate.filter_items([ITEM])
        assert kept == [ITEM]
        assert called["n"] == 0

    def test_reject_dropped(self, monkeypatch):
        _enable(monkeypatch)
        _neutral_rules(monkeypatch)
        monkeypatch.setattr(
            ai_tasks.llm_service_ref(), "generate",
            _fake_generate('{"verdict":"reject","reason":"广告"}'),
        )
        kept = info_filter_gate.filter_items([ITEM, {"source_name": "s", "title": "t2", "summary": "", "_x": 1}])
        # 第二条同样 reject → 全 drop
        assert kept == []

    def test_allow_kept(self, monkeypatch):
        _enable(monkeypatch)
        _neutral_rules(monkeypatch)
        monkeypatch.setattr(
            ai_tasks.llm_service_ref(), "generate",
            _fake_generate('{"verdict":"allow","reason":"ok"}'),
        )
        assert info_filter_gate.filter_items([ITEM]) == [ITEM]

    def test_llm_error_fail_open(self, monkeypatch):
        _enable(monkeypatch)
        _neutral_rules(monkeypatch)
        monkeypatch.setattr(
            ai_tasks.llm_service_ref(), "generate",
            async_fail_counter({"n": 0}, fail=True),
        )
        assert info_filter_gate.filter_items([ITEM]) == [ITEM]


def async_fail_counter(called, fail=False):
    async def _gen(prompt, *, task="summary", **kw):
        called["n"] += 1
        if fail:
            raise RuntimeError("down")
        return '{"verdict":"allow","reason":"ok"}'
    return _gen
```

注：`llm_service_ref()` 是测试辅助 — 为避免依赖 tasks.py 内部 import 形态，测试直接 monkeypatch `backend.services.ai_hub.gateway.llm_service.generate`。**最终测试把 `ai_tasks.llm_service_ref()` 全部替换为：**

```python
from backend.services.ai_hub.gateway import llm_service
# monkeypatch.setattr(llm_service, "generate", ...)
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest backend/tests/test_semantic_filter_gate.py -v`
Expected: FAIL — `AttributeError: ... semantic_verdict`

- [ ] **Step 3: tasks.py 实现**

`backend/services/ai_hub/tasks.py` 模块级追加（放 `_parse_eval_json` 之后，风格对齐既有 `_eval_prompt`/`_parse_*`）：

```python
# ── 语义门禁 (2026-09-18 方案 B, gate semantic_filter) ─────────────
_SEMANTIC_VERDICT_PROMPT = """你是资讯质量门禁。判断以下条目是否值得保留进入知识管线。
判定标准:
- allow: 与安全 / AI / 技术资讯相关, 或对从业者有信息量
- reject: 广告、软文、招聘、活动宣传、与主题无关的噪声

条目内容:
{content}

只输出 JSON, 不要输出其他文字:
{{"verdict": "allow" 或 "reject", "reason": "一句话理由"}}"""


def _build_semantic_verdict_prompt(content: str) -> str:
    return _SEMANTIC_VERDICT_PROMPT.format(content=content[:2000])


def _parse_verdict_json(raw: str) -> dict:
    """容错解析 verdict JSON; 解析失败 → allow (fail-open, 门禁故障不丢内容)。"""
    import json as _json
    import re as _re
    try:
        m = _re.search(r"\{.*\}", raw or "", _re.DOTALL)
        if not m:
            return {"verdict": "allow", "reason": "parse_failed_empty"}
        data = _json.loads(m.group(0))
        verdict = data.get("verdict")
        if verdict == "reject":
            return {"verdict": "reject", "reason": str(data.get("reason", ""))}
        return {"verdict": "allow", "reason": str(data.get("reason", ""))}
    except Exception:
        return {"verdict": "allow", "reason": "parse_failed_exception"}


def semantic_verdict(content: str) -> dict:
    """LLM verdict-only 判别 (同步入口, 链路内 asyncio.run 包裹 — t1 同款模式)。

    走 gateway.generate 通用漏斗 (task="semantic_filter"); 全链失败
    generate 返回 "" → _parse_verdict_json fail-open allow。
    """
    import asyncio

    from .gateway import llm_service

    raw = asyncio.run(llm_service.generate(
        _build_semantic_verdict_prompt(content), task="semantic_filter",
    ))
    return _parse_verdict_json(raw or "")
```

- [ ] **Step 4: info_filter_gate 挂点**

`backend/services/info_filter_gate.py` `filter_items`（L105-144）— 在 `kept.append(it)` 前插入语义层；文件头部已有 `from backend.extensions import is_extension_enabled`？核实：该文件现用 `_is_enabled()`（内部同源）。加一个模块级辅助：

```python
def _semantic_enabled() -> bool:
    from backend.extensions import is_extension_enabled
    return is_extension_enabled("semantic_filter")
```

`filter_items` 循环体 L137-141 改为：

```python
        verdict, _ = evaluate(rules, category=cat or "", source_name=name or "")
        if verdict == "deny":
            dropped += 1
            continue
        # 2026-09-18 方案 B: 语义门禁层 — 仅规则 neutral 时 LLM 判别
        # (gate semantic_filter, 默认关; 失败 fail-open 保留)。
        if verdict == "neutral" and _semantic_enabled():
            text = _item_text(it)
            if text:
                try:
                    from backend.services.ai_hub.tasks import semantic_verdict
                    sv = semantic_verdict(text)
                    if sv.get("verdict") == "reject":
                        dropped += 1
                        logger.info(
                            f"info_filter: semantic reject item "
                            f"{name!r} reason={sv.get('reason', '')!r}"
                        )
                        continue
                except Exception as e:  # fail-open
                    logger.warning(f"info_filter: semantic layer error (fail-open): {e}")
        kept.append(it)
```

文件级新增辅助（`filter_items` 之前）：

```python
def _item_text(it: Any) -> str:
    """Layer 2 item → 判别文本 (title + summary, 兼容 dict / HotspotItem)。"""
    def _get(obj, key: str) -> str:
        if isinstance(obj, dict):
            return str(obj.get(key, "") or "")
        return str(getattr(obj, key, "") or "")
    parts = [_get(it, "title"), _get(it, "summary")]
    return " ".join(p for p in parts if p.strip())
```

- [ ] **Step 5: 运行确认通过 + info_filter 回归**

Run: `python -m pytest backend/tests/test_semantic_filter_gate.py backend/tests/test_info_filter_gate.py -v`
Expected: 全 PASS（info_filter 既有用例不受影响 — 其测试环境下 semantic gate 默认关）

- [ ] **Step 6: Commit**

```bash
git add backend/services/ai_hub/tasks.py backend/services/info_filter_gate.py backend/tests/test_semantic_filter_gate.py
git commit -m "feat(pipeline): 语义门禁层 — info_filter neutral 时 verdict-only LLM 判别 (gate semantic_filter)"
```

---

### Task 7: 智能分类增援 — classify_item_with_ai

**Files:**
- Modify: `backend/services/auto_classifier.py`（文件末尾追加，`classify_item` 不动）
- Test: `backend/tests/test_ai_classify.py`（新建）

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/test_ai_classify.py
"""ai_classify gate — 纯规则 miss (domain=None) 时 LLM 增援。

契约: classify_item 纯函数零改动; gate 关 → 等价 classify_item;
LLM 失败 / 越权 domain → 兜底纯规则结果; domain 词表严格校验。
"""
import pytest

from backend.extensions import reset_gates
from backend.services import auto_classifier as ac


@pytest.fixture(autouse=True)
def _restore():
    yield
    reset_gates()


def _enable(monkeypatch):
    monkeypatch.setenv(
        "HOTSPOT_FEATURE_GATES", '{"extensions": {"ai_classify": true}}'
    )
    reset_gates()


def _fake_generate(payload=None, fail=False):
    async def _gen(prompt, *, task="summary", **kw):
        assert task == "ai_classify"
        if fail:
            raise RuntimeError("down")
        return payload or ""
    return _gen


def _mock_llm(monkeypatch, payload=None, fail=False):
    from backend.services.ai_hub.gateway import llm_service
    monkeypatch.setattr(llm_service, "generate", _fake_generate(payload, fail))


NO_MATCH = ("完全不相关的标签", "毫无领域线索的标题xyzq", "")


class TestClassifyItemWithAi:
    def test_rule_hit_skips_llm(self, monkeypatch):
        _enable(monkeypatch)
        called = {"n": 0}
        async def _gen(prompt, *, task="summary", **kw):
            called["n"] += 1
            return ""
        from backend.services.ai_hub.gateway import llm_service
        monkeypatch.setattr(llm_service, "generate", _gen)
        result = ac.classify_item_with_ai(["AI"], title="x")
        assert result["domain"] == "ai"
        assert called["n"] == 0  # 规则命中 → 零 LLM

    def test_gate_off_equals_pure(self, monkeypatch):
        monkeypatch.delenv("HOTSPOT_FEATURE_GATES", raising=False)
        reset_gates()
        _mock_llm(monkeypatch, '{"domain":"ai"}')
        r = ac.classify_item_with_ai(*NO_MATCH)
        assert r == ac.classify_item(*NO_MATCH)
        assert r["domain"] is None

    def test_llm_fills_domain(self, monkeypatch):
        _enable(monkeypatch)
        _mock_llm(monkeypatch, '{"domain": "ai", "type": "news", "difficulty": "beginner"}')
        r = ac.classify_item_with_ai(*NO_MATCH)
        assert r["domain"] == "ai"

    def test_llm_invalid_domain_rejected(self, monkeypatch):
        _enable(monkeypatch)
        _mock_llm(monkeypatch, '{"domain": "不存在的域"}')
        r = ac.classify_item_with_ai(*NO_MATCH)
        assert r["domain"] is None

    def test_llm_failure_fallback(self, monkeypatch):
        _enable(monkeypatch)
        _mock_llm(monkeypatch, fail=True)
        r = ac.classify_item_with_ai(*NO_MATCH)
        assert r == ac.classify_item(*NO_MATCH)
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest backend/tests/test_ai_classify.py -v`
Expected: FAIL — `AttributeError: ... classify_item_with_ai`

- [ ] **Step 3: 实现**

`backend/services/auto_classifier.py` 文件末尾追加：

```python
# ═══════════════════════════════════════════════════════════════
# AI 分类增援 (2026-09-18 方案 B, gate ai_classify — 默认关)
# 纯规则 classify_item 契约不动 (本文件以上部分保持 deterministic)。
# ═══════════════════════════════════════════════════════════════

_DOMAIN_VOCAB: frozenset[str] = frozenset(set(TAG_DOMAIN_MAP.values()))


def _ai_classify_enabled() -> bool:
    from backend.extensions import is_extension_enabled
    return is_extension_enabled("ai_classify")


def _build_ai_classify_prompt(title: str, tags: list[str], source_url: str) -> str:
    domains = ", ".join(sorted(_DOMAIN_VOCAB))
    return (
        "为以下资讯条目分类。domain 必须从候选列表中选一个, 无法判断填 null。\n"
        f"候选 domain: {domains}\n"
        f"标题: {title}\n"
        f"标签: {', '.join(tags) if tags else '(无)'}\n"
        f"来源: {source_url or '(无)'}\n"
        '只输出 JSON: {"domain": "...", "type": "...", "difficulty": "..."}'
    )


def _parse_classify_json(raw: str) -> dict | None:
    import json as _json
    import re as _re
    try:
        m = _re.search(r"\{.*\}", raw or "", _re.DOTALL)
        if not m:
            return None
        data = _json.loads(m.group(0))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def classify_item_with_ai(
    tags: list[str],
    title: str = "",
    source_url: str = "",
) -> dict:
    """classify_item 的 gate 化包装: 纯规则优先, domain miss 时 LLM 增援。

    - gate ai_classify 关 → 等价 classify_item (零 LLM 调用);
    - 仅规则结果含 None 字段时触发一次 LLM; domain 结果必须落在
      ``_DOMAIN_VOCAB`` 内才采纳, type/difficulty 仅补 None 槽位;
    - LLM 失败 / 解析失败 → 兜底纯规则结果 (增援永不伤害原行为)。
    """
    result = classify_item(tags, title, source_url)
    if not _ai_classify_enabled():
        return result
    if all(result.get(k) for k in ("domain", "type", "difficulty")):
        return result
    try:
        import asyncio

        from backend.services.ai_hub.gateway import llm_service

        raw = asyncio.run(llm_service.generate(
            _build_ai_classify_prompt(title, list(tags), source_url),
            task="ai_classify",
        ))
        parsed = _parse_classify_json(raw or "")
        if parsed:
            llm_domain = parsed.get("domain")
            if not result.get("domain") and llm_domain in _DOMAIN_VOCAB:
                result["domain"] = llm_domain
            for key in ("type", "difficulty"):
                if not result.get(key) and parsed.get(key):
                    result[key] = str(parsed[key])
    except Exception:
        pass  # 兜底: 任何失败返回纯规则结果
    return result
```

- [ ] **Step 4: 运行确认通过 + classifier 回归**

Run: `python -m pytest backend/tests/test_ai_classify.py backend/tests/test_auto_classifier.py -v`
Expected: 全 PASS

- [ ] **Step 5: Commit**

```bash
git add backend/services/auto_classifier.py backend/tests/test_ai_classify.py
git commit -m "feat(pipeline): 智能分类增援 — 规则 miss 时 LLM 补分类 (gate ai_classify)"
```

---

### Task 8: NER 实体抽取 — 迁移 + t1 挂点

**Files:**
- Create: `backend/repository/migrations/119_item_entities.sql`
- Modify: `backend/services/triggers/t1_raw_to_refine.py`（`_score_with_llm` 内挂点 + 模块级 `write_entities`）
- Test: `backend/tests/test_pipeline_ner.py`（新建）

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/test_pipeline_ner.py
"""pipeline_ner gate — t1 score 成功后 extract_entities 落 knowledge_items.entities。

契约: gate 关零改动; 实体为空不写; gate 关闭时 t1 不调 LLM;
迁移后 entities 列存在 (JSON 数组字符串, 可空)。
"""
import json

import pytest

from backend.extensions import reset_gates
from backend.repository.db import get_connection, knowledge_items_table
from backend.services.triggers import t1_raw_to_refine as t1


@pytest.fixture(autouse=True)
def _restore():
    yield
    reset_gates()


def _enable(monkeypatch):
    monkeypatch.setenv(
        "HOTSPOT_FEATURE_GATES", '{"extensions": {"pipeline_ner": true}}'
    )
    reset_gates()


def _insert_item(item_id: str = "it_ner_1") -> None:
    conn = get_connection()
    conn.execute(
        f"INSERT OR IGNORE INTO {knowledge_items_table()} (id, title, source, lifecycle) "
        f"VALUES (?, ?, ?, ?)",
        (item_id, "测试标题", "测试源", "kl:raw"),
    )


def test_migration_entities_column_exists():
    _insert_item()
    cols = {
        row["name"] for row in
        get_connection().execute(f"PRAGMA table_info({knowledge_items_table()})").fetchall()
    }
    assert "entities" in cols


def test_write_entities_roundtrip():
    _insert_item("it_ner_2")
    t1.write_entities("it_ner_2", ["CVE-2026-1234", "ATT&CK T1059"])
    row = get_connection().execute(
        f"SELECT entities FROM {knowledge_items_table()} WHERE id = ?", ("it_ner_2",)
    ).fetchone()
    assert json.loads(row["entities"]) == ["CVE-2026-1234", "ATT&CK T1059"]


def test_enrich_noop_when_disabled(monkeypatch):
    monkeypatch.delenv("HOTSPOT_FEATURE_GATES", raising=False)
    reset_gates()
    called = {"n": 0}

    async def fake_ents(content):
        called["n"] += 1
        return ["x"]

    from backend.services.ai_hub.gateway import llm_service
    monkeypatch.setattr(llm_service, "extract_entities", fake_ents)
    _insert_item("it_ner_3")
    trig = t1.T1Trigger()
    content = "标题 概念"
    trig._score_with_llm({"id": "it_ner_3", "title": "标题", "concepts": None})
    assert called["n"] == 0  # gate 关 → 不调 NER


def test_enrich_called_when_enabled(monkeypatch):
    _enable(monkeypatch)
    captured = {}
    async def fake_score(content, item_id=""):
        return 7.5
    async def fake_ents(content):
        captured["content"] = content
        return ["CVE-2026-9999"]
    from backend.services.ai_hub.gateway import llm_service
    monkeypatch.setattr(llm_service, "score", fake_score)
    monkeypatch.setattr(llm_service, "extract_entities", fake_ents)
    _insert_item("it_ner_4")
    trig = t1.T1Trigger()
    score = trig._score_with_llm({"id": "it_ner_4", "title": "OpenAI 漏洞", "concepts": None})
    assert score == 7.5
    assert "OpenAI 漏洞" in captured["content"]
    row = get_connection().execute(
        f"SELECT entities FROM {knowledge_items_table()} WHERE id = ?", ("it_ner_4",)
    ).fetchone()
    assert json.loads(row["entities"]) == ["CVE-2026-9999"]


def test_enrich_empty_entities_no_write(monkeypatch):
    _enable(monkeypatch)
    async def fake_score(content, item_id=""):
        return 6.0
    async def fake_ents(content):
        return []
    from backend.services.ai_hub.gateway import llm_service
    monkeypatch.setattr(llm_service, "score", fake_score)
    monkeypatch.setattr(llm_service, "extract_entities", fake_ents)
    _insert_item("it_ner_5")
    trig = t1.T1Trigger()
    trig._score_with_llm({"id": "it_ner_5", "title": "标题", "concepts": None})
    row = get_connection().execute(
        f"SELECT entities FROM {knowledge_items_table()} WHERE id = ?", ("it_ner_5",)
    ).fetchone()
    assert row["entities"] is None
```

注：`_score_with_llm` 打分成功会调 `_write_llm_score` → `write_score`（ai_scores 表）— 测试环境 conftest 有 DB 隔离，ai_scores 表可用；若 write_score 因缺 hotspot 外键约束失败，在 fake_score 之外再 monkeypatch `t1.write_score` 为 no-op（加一行 `monkeypatch.setattr(t1, "write_score", lambda *a, **kw: None)` 到启用用例中）。

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest backend/tests/test_pipeline_ner.py -v`
Expected: FAIL — `entities` 列不存在 / `write_entities` 不存在

- [ ] **Step 3: 迁移文件**

```sql
-- 119_item_entities.sql
-- 2026-09-18 方案 B (gate pipeline_ner): t1 LLM 实体抽取落库列 —
-- JSON 数组字符串 (extract_entities → list[str]); 仅落库, 下游消费不在范围。
ALTER TABLE knowledge_items ADD COLUMN entities TEXT;
```

- [ ] **Step 4: t1 挂点**

`backend/services/triggers/t1_raw_to_refine.py`：

(a) 模块级新增（放 `TRIGGER_NAME = "t1"` 附近之后任意顶层位置）：

```python
def write_entities(item_id: str, entities: list[str]) -> None:
    """pipeline_ner: 实体 JSON 落 knowledge_items.entities (空列表不写)。"""
    if not entities:
        return
    conn = get_connection()
    conn.execute(
        f"UPDATE {knowledge_items_table()} SET entities = ? WHERE id = ?",
        (json.dumps(entities, ensure_ascii=False), item_id),
    )


def _ner_enabled() -> bool:
    from backend.extensions import is_extension_enabled
    return is_extension_enabled("pipeline_ner")
```

(b) `_score_with_llm`（L263-285）成功分支改写 — 复用已拼好的 `content`：

```python
        if content.strip():
            import asyncio
            try:
                score = asyncio.run(llm_service.score(content, item.get("id", "")))
                if score != DEFAULT_SCORE:
                    # Write LLM score to ai_scores table for audit
                    self._write_llm_score(item.get("id", ""), score)
                    self.metrics.observe("t1_llm_score_ms", 0)
                    # 2026-09-18 方案 B: NER 增援 (gate pipeline_ner, 默认关) —
                    # 复用打分 content, 失败不影响打分主链路。
                    if _ner_enabled():
                        try:
                            ents = asyncio.run(llm_service.extract_entities(content))
                            write_entities(item.get("id", ""), ents)
                        except Exception as ner_exc:
                            logger.warning(f"t1 NER enrichment failed (non-fatal): {ner_exc}")
                    return score
            except Exception:
                pass
        return self._get_latest_score(item.get("id", ""))
```

- [ ] **Step 5: 运行确认通过 + t1 回归**

Run: `python -m pytest backend/tests/test_pipeline_ner.py -v && python -m pytest backend/tests/ -k "t1 or trigger" -q`
Expected: 全 PASS

- [ ] **Step 6: Commit**

```bash
git add backend/repository/migrations/119_item_entities.sql backend/services/triggers/t1_raw_to_refine.py backend/tests/test_pipeline_ner.py
git commit -m "feat(pipeline): NER 实体抽取落库 — knowledge_items.entities 列 (gate pipeline_ner)"
```

---

### Task 9: 文档同步（PRD + DEV_LOG + ARCHITECTURE 数字核查）

**Files:**
- Modify: `docs/HOTSPOT_SECURITY_AI_WORKBENCH_PRD.md`（能力条目 + gate 表）
- Modify: `docs/DEV_LOG.md`（若 DEV_LOG 位于别处以 `Glob docs/DEV_LOG*` 定位）
- Possibly: `docs/ARCHITECTURE.md`（仅当 generate_meta 数字变化）

- [ ] **Step 1: 架构数字核查**

Run: `python scripts/generate_meta.py`
若输出与现值 (57 jobs / 13 collectors / 86 routers / 146 services) 不一致 → 同步 ARCHITECTURE.md 对应数字。`pi_transport.py` 非 `*_service.py`、无新 router/job — 预期数字不变。

- [ ] **Step 2: PRD 同步**

在 `docs/HOTSPOT_SECURITY_AI_WORKBENCH_PRD.md` 的 feature gate 清单与采集域能力区块追加（措辞对齐文件既有风格，改前先读相关小节定位插入点）：

- 新增 3 gate：`semantic_filter` / `ai_classify` / `pipeline_ner`（默认关，2026-09-18 方案 B）
- 能力条目：pi provider（ai_hub 第 5 种 type，红线不破）+ 三管线能力挂点一句话
- 引用 spec 路径 `docs/superpowers/specs/2026-09-18-pipeline-llm-pi-provider-design.md`

- [ ] **Step 3: DEV_LOG 追加**

按文件既有条目格式追加：日期 2026-09-18、主题"管线 LLM pi 化 + 三能力补齐（方案 B）"、关联文件含 spec + 本计划 + 改动源文件清单。

- [ ] **Step 4: Commit**

```bash
git add docs/HOTSPOT_SECURITY_AI_WORKBENCH_PRD.md docs/DEV_LOG.md docs/ARCHITECTURE.md
git commit -m "docs: PRD/DEV_LOG 同步管线 LLM pi 化 + 三 gate 登记"
```

---

### Task 10: 全量验证

- [ ] **Step 1: 编译检查**

Run: `python -m py_compile backend/services/ai_hub/pi_transport.py backend/services/ai_hub/gateway.py backend/services/ai_hub/tasks.py backend/services/info_filter_gate.py backend/services/auto_classifier.py backend/services/triggers/t1_raw_to_refine.py backend/config/llm_schema.py backend/extensions/__init__.py backend/services/agent_bridge.py`
Expected: 无输出（exit 0）

- [ ] **Step 2: 全量后端测试**

Run: `python -m pytest backend/tests/ --tb=short -q`
Expected: 0 failed（既有 3000+ 用例 + 本计划新增 ~25 用例）

- [ ] **Step 3: gate 关闭回归抽查（红线验证）**

Run: `HOTSPOT_FEATURE_GATES='{"extensions": {"semantic_filter": false, "ai_classify": false, "pipeline_ner": false}}' python -m pytest backend/tests/test_info_filter_gate.py backend/tests/test_auto_classifier.py -q`
Expected: 全 PASS — 三 gate 关闭时行为与现状一致

- [ ] **Step 4: 前端零改动验证（只读确认）**

Run: `cd frontend && npx tsc --noEmit`
Expected: exit 0（本计划前端零改动，tsc 仅确认无意外波及）

---

## Self-Review 结论

1. **Spec 覆盖**: §3.1→Task2 / §3.2→Task3 / §3.3→Task2 测试 yaml + Task9 PRD 文档 / §3.4→Task4 / §4.1→Task6 / §4.2→Task7 / §4.3→Task8 / §5→Task5 / §6→计划核实结论（零改动） / §7→各 Task 测试 + Task10 / §8→Task9 — 无缺口。
2. **占位符扫描**: Task1 Step1 的 `kwargs_stdin` 弱辅助已在原地标注删除指令；Task6 Step1 的 `llm_service_ref()` 已给出替换代码。其余步骤均含完整代码/命令。
3. **类型一致性**: `parse_pi_jsonl_events` / `run_pi_print` / `semantic_verdict` / `write_entities` / `classify_item_with_ai` 命名在定义与消费点一致；gate 名三处（toml / `_EXTENSION_NAMES` / 消费点 `is_extension_enabled(...)`）拼写一致。
