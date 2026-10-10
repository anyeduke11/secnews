"""routing_writer 单测 (DEV-0245) — 定点 yaml 编辑, 全程用 tmp 副本, 不碰真实 llm.yaml。

覆盖: 三档写入只动目标块 / 注释与相邻块保留 / 备份生成 / provider 块自动补建
(不重复) / 非法输入拒绝 / noop / 结构漂移拒绝。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.services.ai_hub.routing_writer import (
    RoutingWriteError,
    read_routing,
    write_task_override,
)

# 真实 llm.yaml 的结构缩影 (含注释/多档/其它 provider), 用于验证定点编辑不误伤
YAML_SAMPLE = """\
# hotspot/config/llm.yaml
# 注释行 — 必须原样保留
enabled: true
default_provider: pi
fallback_order:
  - pi
  - sensenova

providers:
  sensenova:
    type: openai_compatible
    api_key_env: "SENSENOVA_API_KEY"
    base_url: "https://token.sensenova.cn/v1"
    models:
      score: "sensenova-6.8-flash-lite"
      summary: "sensenova-6.8-flash-lite"
  # 注释在 provider 中间 — 保留
  ollama:
    type: ollama
    base_url: "http://127.0.0.1:11434"
    models:
      score: "qwen2.5:7b"

task_overrides:
  # STANDARD 档注释 — 保留
  t1_score:
    provider: pi
    model: claude-sonnet-4-5
    temperature: 0.0
    max_tokens: 512
  t3_summary:
    provider: sensenova
    model: deepseek-v4-pro
    temperature: 0.3
    max_tokens: 1600
  t3_chunk_summary:
    provider: ollama
    model: qwen2.5:7b
    temperature: 0.0

rate_limits:
  requests_per_minute: 60
"""


@pytest.fixture
def yaml_file(tmp_path: Path) -> Path:
    p = tmp_path / "llm.yaml"
    p.write_text(YAML_SAMPLE, encoding="utf-8")
    return p


class TestWriteTaskOverride:
    def _patch_pool(self, monkeypatch, *, env_var: str, models: list[str],
                    available: bool | None = True, error: str | None = None):
        """给池内平台 mock key (env) + 探测结果 — 写前 key 体检 (DEV-0246) 需要真实感数据。"""
        monkeypatch.setenv(env_var, "test-key")
        import backend.services.ai_hub.pool as pm
        monkeypatch.setattr(pm, "probe_platform", lambda preset: {
            "available": available, "models": models, "model_count": len(models),
            "latency_ms": 1, "error": error,
        })

    def test_targeted_edit_only_touches_target_block(self, yaml_file: Path, monkeypatch):
        self._patch_pool(monkeypatch, env_var="SENSENOVA_API_KEY",
                         models=["sensenova-v4-pro", "sensenova-6.8-flash-lite"])
        out = write_task_override("t1_score", "sensenova", "sensenova-v4-pro", yaml_path=yaml_file)
        assert out["status"] == "ok"
        text = yaml_file.read_text(encoding="utf-8")
        # 目标块已改 (model 不加引号 — 与原文件风格一致)
        assert "    provider: sensenova\n    model: sensenova-v4-pro" in text
        # 相邻块未动
        assert "  t3_summary:\n    provider: sensenova\n    model: deepseek-v4-pro" in text
        assert "  t3_chunk_summary:\n    provider: ollama\n    model: qwen2.5:7b" in text
        # 注释保留
        assert "# 注释行 — 必须原样保留" in text
        assert "# STANDARD 档注释 — 保留" in text
        assert "# 注释在 provider 中间 — 保留" in text
        # 备份生成
        backups = list(yaml_file.parent.glob("llm.yaml.bak-*"))
        assert len(backups) == 1
        assert backups[0].read_text(encoding="utf-8") == YAML_SAMPLE

    def test_new_platform_appends_provider_block_once(self, yaml_file: Path, monkeypatch):
        self._patch_pool(monkeypatch, env_var="DEEPSEEK_API_KEY",
                         models=["deepseek-chat", "deepseek-reasoner"])
        write_task_override("t3_summary", "deepseek", "deepseek-chat", yaml_path=yaml_file)
        text1 = yaml_file.read_text(encoding="utf-8")
        assert text1.count("  deepseek:\n") == 1
        assert 'api_key_env: "DEEPSEEK_API_KEY"' in text1
        assert 'base_url: "https://api.deepseek.com/v1"' in text1
        # 写入后路由可被 pyyaml 读出
        import yaml
        cfg = yaml.safe_load(text1)
        assert cfg["task_overrides"]["t3_summary"]["provider"] == "deepseek"
        # 第二次写不同档: 不重复追加
        write_task_override("t1_score", "deepseek", "deepseek-reasoner", yaml_path=yaml_file)
        text2 = yaml_file.read_text(encoding="utf-8")
        assert text2.count("  deepseek:\n") == 1
        cfg2 = yaml.safe_load(text2)
        assert cfg2["task_overrides"]["t1_score"]["model"] == "deepseek-reasoner"

    def test_noop_when_already_routed(self, yaml_file: Path):
        out = write_task_override("t3_summary", "sensenova", "deepseek-v4-pro", yaml_path=yaml_file)
        assert out["status"] == "noop"

    def test_unknown_override_key_rejected(self, yaml_file: Path):
        with pytest.raises(RoutingWriteError, match="unknown override_key"):
            write_task_override("evil_key", "sensenova", "m", yaml_path=yaml_file)

    def test_yaml_injection_rejected(self, yaml_file: Path):
        with pytest.raises(RoutingWriteError, match="invalid model"):
            write_task_override("t1_score", "sensenova", "m\n    hacked: true", yaml_path=yaml_file)

    def test_unknown_provider_without_preset_rejected(self, yaml_file: Path):
        with pytest.raises(RoutingWriteError, match=r"不在 llm\.yaml providers"):
            write_task_override("t1_score", "skynet", "m", yaml_path=yaml_file)

    def test_structural_drift_rejected(self, tmp_path: Path):
        p = tmp_path / "broken.yaml"
        p.write_text("providers:\n  sensenova:\n    models:\n      score: s\n\ntask_overrides:\n  t1_score: 'flat-value'\n", encoding="utf-8")
        with pytest.raises(RoutingWriteError, match="t1_score 块未找到"):
            write_task_override("t1_score", "sensenova", "m", yaml_path=p)

    def test_missing_file_rejected(self, tmp_path: Path):
        with pytest.raises(RoutingWriteError, match="不存在"):
            write_task_override("t1_score", "sensenova", "m", yaml_path=tmp_path / "nope.yaml")


class TestKeyValidation:
    """DEV-0246 写前 key 体检 — 单点锚点无 key = 该档任务必败, 必须写前拦截。"""

    def _patch_probe(self, monkeypatch, *, available, models=None, error=None):
        import backend.services.ai_hub.pool as pm
        monkeypatch.setattr(pm, "probe_platform", lambda preset: {
            "available": available, "models": models or [], "model_count": len(models or []),
            "latency_ms": 1, "error": error,
        })

    def test_no_key_rejected_regardless_of_force(self, yaml_file, monkeypatch):
        """无 key 不可 force 绕过 — force 只跳过在线探测。"""
        monkeypatch.delenv("SENSENOVA_API_KEY", raising=False)
        with pytest.raises(RoutingWriteError, match="无可用密钥"):
            write_task_override("t1_score", "sensenova", "m", yaml_path=yaml_file, force=True)

    def test_probe_401_rejected(self, yaml_file, monkeypatch):
        monkeypatch.setenv("SENSENOVA_API_KEY", "bad")
        self._patch_probe(monkeypatch, available=False, error="HTTP 401 (密钥无效或无权限)")
        with pytest.raises(RoutingWriteError, match="密钥探测未通过") as ei:
            write_task_override("t1_score", "sensenova", "m", yaml_path=yaml_file)
        # 拒绝文案必须指明 force 出口及其语义 (跳过探测直接写入)
        assert "force=true 重试" in str(ei.value)
        assert "跳过在线探测" in str(ei.value)

    def test_ok_when_model_in_probe_list(self, yaml_file, monkeypatch):
        monkeypatch.setenv("SENSENOVA_API_KEY", "k")
        self._patch_probe(monkeypatch, available=True, models=["sensenova-v4-pro"])
        out = write_task_override("t1_score", "sensenova", "sensenova-v4-pro", yaml_path=yaml_file)
        assert out["status"] == "ok"
        assert out["key_check"] == {"source": "env", "probed": True, "warning": None}

    def test_model_not_in_list_warns_but_writes(self, yaml_file, monkeypatch):
        """部分网关 /models 列表不全 — 模型不在列表是 warning 不是拒绝。"""
        monkeypatch.setenv("SENSENOVA_API_KEY", "k")
        self._patch_probe(monkeypatch, available=True, models=["other-model"])
        out = write_task_override("t1_score", "sensenova", "sensenova-v4-pro", yaml_path=yaml_file)
        assert out["status"] == "ok"
        assert "不在平台 /models 列表" in out["key_check"]["warning"]
        assert "注意:" in out["message"]

    def test_no_models_endpoint_warns_but_writes(self, yaml_file, monkeypatch):
        monkeypatch.setenv("SENSENOVA_API_KEY", "k")
        self._patch_probe(monkeypatch, available=None, error="platform_no_models_endpoint")
        out = write_task_override("t1_score", "sensenova", "m", yaml_path=yaml_file)
        assert out["status"] == "ok"
        assert "跳过在线验证" in out["key_check"]["warning"]

    def test_force_skips_probe_entirely(self, yaml_file, monkeypatch):
        monkeypatch.setenv("SENSENOVA_API_KEY", "k")
        import backend.services.ai_hub.pool as pm

        def _boom(preset):
            raise AssertionError("force=true 不得出站探测")

        monkeypatch.setattr(pm, "probe_platform", _boom)
        out = write_task_override("t1_score", "sensenova", "m", yaml_path=yaml_file, force=True)
        assert out["status"] == "ok"
        assert out["key_check"] == {"source": "env", "probed": False,
                                    "warning": "已跳过在线探测 (force=true) — 模型可用性未经验证"}
        # force 语义提示必须进 message — 用户需知道本次写入未经验证
        assert "已跳过在线探测 (force)" in out["message"]
        assert "可用性未经验证" in out["message"]

    def test_yaml_only_provider_skips_check(self, yaml_file, monkeypatch):
        """ollama 等 yaml-only provider 无 key 概念 — 不在体检范围。"""
        out = write_task_override("t3_chunk_summary", "ollama", "qwen2.5:14b", yaml_path=yaml_file)
        assert out["status"] == "ok"
        assert out["key_check"] == {}

    def test_noop_skips_validation(self, yaml_file, monkeypatch):
        """同值再写是 noop — 不触发 key 体检 (无谓出站)。"""
        monkeypatch.delenv("SENSENOVA_API_KEY", raising=False)
        import backend.services.ai_hub.pool as pm

        def _boom(*a, **kw):
            raise AssertionError("noop 不得出站探测")

        monkeypatch.setattr(pm, "probe_platform", _boom)
        out = write_task_override("t3_summary", "sensenova", "deepseek-v4-pro", yaml_path=yaml_file)
        assert out["status"] == "noop"

    def test_reads_three_tiers(self, yaml_file: Path, monkeypatch):
        import backend.services.ai_hub.routing_writer as rw
        monkeypatch.setattr(rw, "LLM_YAML", yaml_file)
        out = read_routing()
        assert out["error"] is None
        r = out["routing"]
        assert r["t1_score"]["provider"] == "pi"
        assert r["t3_summary"]["model"] == "deepseek-v4-pro"
        assert r["t3_chunk_summary"]["provider"] == "ollama"
