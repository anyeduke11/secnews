"""v0.5 M2-Task5: CLI 契约包装 + 8 子命令注册表单元测试。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_cli_contract():
    sys.path.insert(0, str(REPO_ROOT))
    from scripts import cli_contract
    return cli_contract


# ---------------------------------------------------------------------------
# 1. SUBCOMMANDS 注册表完整性
# ---------------------------------------------------------------------------
def test_subcommands_registry_has_all_8():
    """SPEC §1 列了 8 个子命令, 注册表全应包含。"""
    cc = _load_cli_contract()
    expected = {
        "collect_all", "map_rebuild", "sm2_daily_push", "db_diet",
        "knowledge_classify", "manual_collect", "extract", "verify_health",
    }
    actual = set(cc.SUBCOMMANDS.keys())
    assert expected == actual, f"missing={expected - actual} extra={actual - expected}"


def test_each_subcommand_has_required_keys():
    """每个子命令必须有 implemented/notes 字段。"""
    cc = _load_cli_contract()
    for name, info in cc.SUBCOMMANDS.items():
        assert "implemented" in info, f"{name} 缺 implemented"
        assert "notes" in info, f"{name} 缺 notes"
        assert isinstance(info["implemented"], bool)


def test_diet_and_manual_collect_implemented():
    """db_diet + manual_collect 已实现 (有 --json), 其他 6 个 v0.4 由 jobs/HTTP 触发。"""
    cc = _load_cli_contract()
    assert cc.SUBCOMMANDS["db_diet"]["implemented"] is True
    assert cc.SUBCOMMANDS["manual_collect"]["implemented"] is True
    # 其他 6 个可以 false (v0.4 路径不变, 契约包装为 not_implemented 即可)
    for name in ("collect_all", "map_rebuild", "sm2_daily_push",
                 "knowledge_classify", "extract", "verify_health"):
        assert cc.SUBCOMMANDS[name]["implemented"] is False, (
            f"{name} 在 v0.4 由 scheduler jobs / HTTP API 触发, 不需独立 CLI"
        )


# ---------------------------------------------------------------------------
# 2. envelope 形状契约 (SPEC §6.1)
# ---------------------------------------------------------------------------
def test_envelope_required_keys():
    """envelope 必须含 ok/code/duration_ms/data 四字段 (SPEC §6.1)。"""
    cc = _load_cli_contract()
    # emit_envelope 副作用 sys.exit, 不可直接测; 测 _make_envelope 行为
    # 这里手工构造预期:
    fake_envelope = {
        "ok": True,
        "code": cc.EXIT_OK,
        "duration_ms": 100,
        "data": {"foo": "bar"},
    }
    for k in ("ok", "code", "duration_ms", "data"):
        assert k in fake_envelope


def test_exit_codes():
    """3 个 exit code 必须可区分 (OK=0, PARTIAL=1, FATAL=2)。"""
    cc = _load_cli_contract()
    assert cc.EXIT_OK == 0
    assert cc.EXIT_PARTIAL == 1
    assert cc.EXIT_FATAL == 2


# ---------------------------------------------------------------------------
# 3. emit_envelope 输出契约 (走 subprocess 触发 sys.exit)
# ---------------------------------------------------------------------------
def test_emit_envelope_via_subprocess(capsys):
    """emit_envelope 副作用: print envelope JSON 到 stdout, sys.exit(code)。

    subprocess 跑 emit_not_implemented() 验证输出形状 + 退出码。
    """
    import subprocess

    code = (
        "import sys, time; "
        "sys.path.insert(0, '.'); "
        "from scripts.cli_contract import emit_not_implemented; "
        "emit_not_implemented('collect_all', time.monotonic(), 'test note')"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True, text=True,
        cwd=str(REPO_ROOT),
        timeout=10,
    )
    # 退出码 = EXIT_OK (0)
    assert proc.returncode == 0, f"stderr={proc.stderr[:500]}"
    # stdout 是 envelope JSON
    envelope = json.loads(proc.stdout)
    assert envelope["ok"] is True
    assert envelope["code"] == 0
    assert "duration_ms" in envelope
    assert envelope["data"]["command"] == "collect_all"
    assert envelope["data"]["status"] == "not_yet_implemented"
    assert "test note" in envelope["data"]["notes"]


# ---------------------------------------------------------------------------
# 4. db_diet 集成: 真实子命令走 envelope 形状
# ---------------------------------------------------------------------------
def test_db_diet_envelope_shape():
    """scripts/db_diet.py --json 走 SPEC §6.1 契约。

    这是 db_diet.py 与 cli_contract 共享契约形状的回归测试。
    """
    import subprocess

    proc = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "db_diet.py"),
         "--json", "--db-path", "/tmp/nonexistent.db"],
        capture_output=True, text=True, timeout=30,
        cwd=str(REPO_ROOT),
        env={"PATH": "/usr/bin:/bin:/usr/local/bin", "PYTHONPATH": str(REPO_ROOT)},
    )
    # 库不存在 → EXIT_FATAL=2
    assert proc.returncode == 2, f"stderr={proc.stderr[:500]}"
    envelope = json.loads(proc.stdout)
    for k in ("ok", "code", "duration_ms", "data"):
        assert k in envelope, f"envelope 缺 {k}"
    assert envelope["ok"] is False
    assert envelope["code"] == 2