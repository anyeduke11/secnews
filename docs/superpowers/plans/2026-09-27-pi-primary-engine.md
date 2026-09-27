# pi 升为 ai_hub 主力引擎 — 实施计划 (2026-09-27)

> **收口状态 (2026-09-27)**: Task 1-4 **全部完成** (勾选未逐项回填, 以本横幅与 DEV-0234 为准)。
> - T1 主力化 `cd6f680`: llm.yaml pi 带头 + 配置锚 3 用例; 2 处硬编码 sensenova 断言改锚定 cfg 现值
> - T2 chat 通道 `6621835`: serialize_messages_to_prompt + _call_provider_chat additive pi 分支; 过时 chat-unsupported 用例重写
> - T3 实弹 `c6da432`: 揪出裸模型名歧义 (pi 0.87.1) → models 留空走 pi 默认上游; score 首链 provider=pi ok=1 (14.1s) + chat 实弹 15.5s + fallback 三级降级实录
> - T4 收口: PRD 注记 + DEV-0234 + generate_meta --check OK + 全量回归 (见 DEV_LOG 收口段)

**Spec**: `docs/superpowers/specs/2026-09-27-pi-primary-engine-design.md`（owner 裁决 2026-09-27: "pi 取代原来的 aihub"）
**Base**: main@b5f482a · **Branch**: pi-primary-engine
**后续批次**: `docs/superpowers/plans/2026-09-22-settings-refactor.md`（设置页三期, 本计划收口后原样开工）

**计划阶段核实结论（覆盖 spec §4 待核实项）:**
1. 既有测试无 `default_provider == "sensenova"` 断言依赖（`grep -rn "sensenova" backend/tests/` 仅命中 provider 配置自身构造用例, 不读 config/llm.yaml）— 开工后以 Task 1 Step 4 实跑复核。
2. `_call_provider_chat` 签名 `(cfg, model, messages, *, max_tokens, temperature, provider_name)`; pi 分支忽略 max_tokens/temperature（子进程 CLI 无此参数语义）, 在代码注释明示。

---

### Task 1: llm.yaml 主力化（配置路由）

**Files:**
- Modify: `config/llm.yaml`（default_provider + fallback_order 两处）
- Test: `backend/tests/test_pi_primary_config.py`（新 — 解析冒烟锚）

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/test_pi_primary_config.py
"""pi 主力化配置锚 (2026-09-27 owner 裁决) — 防 fallback 链回退漂移。

契约: pi 是 default_provider 且 fallback_order 首位; 既有四 provider 保留
为兜底 (spec §2.2: 降级不删除)。config/llm.yaml 是仓库内配置文件, 锚定
防"有人改回 sensenova 主力而无人知晓"。
"""
import yaml

from backend.config.llm_schema import LLMConfig


def _load_repo_llm_yaml() -> LLMConfig:
    with open("config/llm.yaml", encoding="utf-8") as f:
        return LLMConfig.model_validate(yaml.safe_load(f))


def test_pi_is_default_provider():
    assert _load_repo_llm_yaml().default_provider == "pi"


def test_pi_leads_fallback_order():
    order = _load_repo_llm_yaml().fallback_order
    assert order[0] == "pi"
    assert order[1] == "ollama"  # 本地零成本为第一兜底


def test_legacy_providers_kept_as_fallback():
    names = set(_load_repo_llm_yaml().providers)
    assert {"ollama", "sensenova", "qwen", "openai"} <= names
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/python3 -m pytest backend/tests/test_pi_primary_config.py -v`
Expected: FAIL — default_provider 是 sensenova

- [ ] **Step 3: 改 config/llm.yaml**

L9 `default_provider: sensenova ...` → `default_provider: pi`（注释: 2026-09-27 owner 裁决 pi 主力, AI_PROVIDER env 可覆盖）
L10-16 `fallback_order` 块 → `pi` 带头, 注释按 spec §3.1（ollama 兜底1 本地零成本 / sensenova 兜底2 唯一持凭据 / qwen / openai）。provider 定义区块不动。

- [ ] **Step 4: 测试通过 + LLM 域回归**

Run: `.venv/bin/python3 -m pytest backend/tests/test_pi_primary_config.py -v && .venv/bin/python3 -m pytest backend/tests/ -k "llm or gateway or ai_hub or pi" -q`
Expected: 全 PASS（若有用例因 default_provider 翻转失败 → 按新事实修正断言, 汇报说明）

- [ ] **Step 5: Commit**

```bash
git add config/llm.yaml backend/tests/test_pi_primary_config.py
git commit -m "feat(ai_hub): pi 升为主力引擎 — default_provider + fallback 链首 (owner 2026-09-27 裁决)"
```

---

### Task 2: serialize_messages_to_prompt + chat pi 分支

**Files:**
- Modify: `backend/services/ai_hub/pi_transport.py`（新增 `serialize_messages_to_prompt`）
- Modify: `backend/services/ai_hub/gateway.py`（`_call_provider_chat` L631 区 additive 分支）
- Test: `backend/tests/test_pi_transport.py`（追加）

- [ ] **Step 1: 追加失败测试**

```python
# 追加到 backend/tests/test_pi_transport.py
from backend.services.ai_hub.pi_transport import serialize_messages_to_prompt


class TestSerializeMessagesToPrompt:
    def test_single_user_message(self):
        msgs = [{"role": "user", "content": "你好"}]
        assert serialize_messages_to_prompt(msgs) == "你好"

    def test_multi_turn_history_then_question(self):
        msgs = [
            {"role": "user", "content": "什么是 CVE"},
            {"role": "assistant", "content": "CVE 是漏洞编号体系"},
            {"role": "user", "content": "举个例子"},
        ]
        out = serialize_messages_to_prompt(msgs)
        assert "[user] 什么是 CVE" in out
        assert "[assistant] CVE 是漏洞编号体系" in out
        assert out.rstrip().endswith("举个例子")

    def test_last_message_not_user_still_accepts(self):
        """非 user 收尾 (如 tool 结果回填) 也接受, 按 assistant 内容收尾。"""
        msgs = [{"role": "user", "content": "q"}, {"role": "assistant", "content": "a"}]
        assert serialize_messages_to_prompt(msgs).rstrip().endswith("a")

    def test_empty_messages_raises(self):
        import pytest
        with pytest.raises(ValueError, match="空 messages"):
            serialize_messages_to_prompt([])


def test_gateway_chat_pi_branch(monkeypatch):
    """chat pi 分支: 序列化 prompt 经 run_pi_print 下传, 失败上抛走 fallback。"""
    import asyncio
    calls = {}

    def fake_run_pi_print(prompt, model, timeout_seconds):
        calls.update(prompt=prompt, model=model, timeout_seconds=timeout_seconds)
        return "pi chat 回答"

    monkeypatch.setattr("backend.services.ai_hub.pi_transport.run_pi_print", fake_run_pi_print)
    msgs = [{"role": "user", "content": "深度分析这个"}]
    out = asyncio.run(LLMService()._call_provider_chat(
        _pi_cfg(), "claude-sonnet-4-5", msgs, provider_name="pi_test",
    ))
    assert out == "pi chat 回答"
    assert calls["prompt"] == "深度分析这个"
    assert calls["model"] == "claude-sonnet-4-5"


def test_gateway_chat_pi_error_propagates(monkeypatch):
    import asyncio

    def fake_fail(prompt, model, timeout_seconds):
        raise RuntimeError("pi exit rc=1: auth expired")

    monkeypatch.setattr("backend.services.ai_hub.pi_transport.run_pi_print", fake_fail)
    with pytest.raises(RuntimeError, match="auth expired"):
        asyncio.run(LLMService()._call_provider_chat(
            _pi_cfg(), "", [{"role": "user", "content": "x"}], provider_name="pi_test",
        ))
```

注: `_pi_cfg` / `LLMService` / `pytest` import 已在文件既有用例区（09-18 计划 Task 3 落地形态），不重复 import。

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/python3 -m pytest backend/tests/test_pi_transport.py -k "serialize or chat_pi" -v`
Expected: FAIL — ImportError serialize_messages_to_prompt

- [ ] **Step 3: 实现 serialize_messages_to_prompt**

`pi_transport.py` 追加（风格对齐既有纯函数）:

```python
def serialize_messages_to_prompt(messages: list[dict]) -> str:
    """chat messages → pi 单轮 prompt (历史轮次文本化, 最后一条为当前提问)。

    pi -p 为单发子进程, 无多轮会话语义; 历史以 [role] 前缀平铺,
    最后一条消息作为收尾提问。空列表 → ValueError (异常路径交
    gateway 健康窗口记账)。
    """
    if not messages:
        raise ValueError("空 messages, 无法序列化为 pi prompt")
    lines: list[str] = []
    for m in messages[:-1]:
        role = str(m.get("role", "user"))
        content = str(m.get("content", "") or "")
        if content.strip():
            lines.append(f"[{role}] {content}")
    lines.append(str(messages[-1].get("content", "") or ""))
    return "\n\n".join(lines)
```

`__all__` 增 `"serialize_messages_to_prompt"`。

- [ ] **Step 4: gateway `_call_provider_chat` additive 分支**

`gateway.py` `_call_provider_chat` 的类型 dispatch（`else: raise ValueError(f"Unsupported provider type for chat: ...")` 之前）插入:

```python
                elif cfg.type == "pi":
                    # 2026-09-27 pi 主力化: chat 场景补 pi 通道 — messages
                    # 序列化为单轮 prompt (pi_transport 纯函数), 子进程执行。
                    # max_tokens/temperature 为 http provider 语义, pi CLI
                    # 不下传; 失败上抛走 fallback 下一 provider。
                    from backend.services.ai_hub.pi_transport import (
                        run_pi_print,
                        serialize_messages_to_prompt,
                    )

                    result = await asyncio.to_thread(
                        run_pi_print,
                        serialize_messages_to_prompt(messages),
                        model,
                        cfg.timeout_seconds,
                    )
```

（对齐既有分支的变量形态: 若该函数既有分支用 `raw = ...` / 直接 return 文本, 以就地形态为准, 不强行改名。）

- [ ] **Step 5: 测试通过 + gateway 回归**

Run: `.venv/bin/python3 -m pytest backend/tests/test_pi_transport.py -v && .venv/bin/python3 -m pytest backend/tests/ -k "gateway or llm" -q`
Expected: 全 PASS

- [ ] **Step 6: Commit**

```bash
git add backend/services/ai_hub/pi_transport.py backend/services/ai_hub/gateway.py backend/tests/test_pi_transport.py
git commit -m "feat(ai_hub): chat 场景补 pi 通道 — messages 序列化单轮 prompt (additive 分支, fallback 不变)"
```

---

### Task 3: 实弹验证（真通道, 非 mock）

- [ ] **Step 1: 后端起服 + 状态确认**

Run: `HOTSPOT_DISABLE_SCHEDULER=1 .venv/bin/python3 run.py`（后台）
curl `http://127.0.0.1:8000/api/llm/status` → 确认 pi 在 default/fallback 首位且 enabled。

- [ ] **Step 2: 真实 generate 走 pi**

对任一条 hotspot 触发 summarize/score（现有 API 或 `.venv/bin/python3 -c` 直调 `llm_service.summarize`），确认返回非回显文本；`/api/llm/usage`（或 usage 表）最近一笔 `provider=pi, model=claude-sonnet-4-5`。
若 pi 上游失败（auth/429）: 记录失败原文, 确认 fallback 自动落到 ollama/sensenova（这本身是 §2.2 兜底验收项）, 结果如实汇报。

- [ ] **Step 3: chat 场景抽查**

触发一次 deep_read（任一 knowledge item）或直调 chat_messages 短消息, 确认 usage `scene=chat, provider=pi`；失败时 fallback 生效。

- [ ] **Step 4: 停服**

---

### Task 4: 收口 — 文档同步 + 全量回归

**Files:**
- Modify: `docs/HOTSPOT_SECURITY_AI_WORKBENCH_PRD.md`（能力条目一句, §5 措辞对齐既有风格）
- Modify: `DEV_LOG.md`（头部追加 [DEV-0234]）
- Modify: `docs/superpowers/plans/2026-09-27-pi-primary-engine.md`（本文件勾选回填）

- [ ] **Step 1: 全量后端回归**

Run: `.venv/bin/python3 -m pytest backend/tests/ --tb=short -q`
Expected: 0 failed（pre-existing 环境性失败单独列明）

- [ ] **Step 2: 架构数字核查**

Run: `python scripts/generate_meta.py --check`
Expected: OK（无新 service/router/job, 数字不变）

- [ ] **Step 3: PRD + DEV_LOG**

PRD 能力条目补"pi 主力化（2026-09-27 owner 裁决, 既有链降兜底）"；DEV_LOG 按 DEV-0233 格式追加 [DEV-0234]（关联本 spec + 计划 + llm.yaml/pi_transport/gateway + 实弹证据）。

- [ ] **Step 4: Commit**

```bash
git add docs/HOTSPOT_SECURITY_AI_WORKBENCH_PRD.md DEV_LOG.md docs/superpowers/plans/2026-09-27-pi-primary-engine.md
git commit -m "docs(pi): pi 主力化收口 — PRD/DEV_LOG 同步 + 计划落账"
```

---

## Self-Review 结论

1. **Spec 覆盖**: §3.1→Task 1 / §3.2→Task 2 / §4 测试→各 Task + Task 4 / §5 文档→Task 4 — 无缺口。
2. **红线核对**: 两处代码改动均为 additive 分支（`_call_provider` 09-18 已落 / `_call_provider_chat` 本批次）, `_try_order`/`_resolve_provider`/场景重排零触碰 — 符合 spec §2 放行范围。
3. **风险**: default_provider 翻转使门禁 LLM 调用 (evaluate/gate_detect) 切到 pi 子进程 — 延迟升高但语义不变, 实弹验证覆盖; pi 失效时 ollama 本地兜底零成本可达。
