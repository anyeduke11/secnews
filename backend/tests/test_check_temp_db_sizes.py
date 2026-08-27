"""check_temp_db_sizes.py 契约测试 — v0.6 P0 清场第二批 commit 6。

覆盖:
  1. report["limits_mb"] 含 HOT/WARM/COLD 三键
  2. report["layers"] 含 HOT/WARM/COLD 三层
  3. violations 列表 — 当 HOT 超阈值时应有 entry
  4. violations 列表 — 各 entry 字段齐 (size_mb/limit_mb/delta_mb/delta_pct)
  5. --json 模式输出可被 json.loads 解析
  6. missing 文件 size=0.0 + exists=False
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "check_temp_db_sizes.py"


def _run_json() -> dict:
    """跑 --json 模式拿 dict 返回."""
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--json"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_limits_keys_present() -> None:
    """report.limits_mb 含 HOT/WARM/COLD 三键."""
    report = _run_json()
    assert set(report["limits_mb"].keys()) == {"HOT", "WARM", "COLD"}
    # 与 v0.5 M2 终验口径一致
    assert report["limits_mb"]["HOT"] == 80
    assert report["limits_mb"]["WARM"] == 300
    assert report["limits_mb"]["COLD"] == 200


def test_layers_present() -> None:
    """report.layers 含 HOT/WARM/COLD 三层, 每层有 size_mb/limit_mb/headroom_mb/ok/path."""
    report = _run_json()
    for layer in ("HOT", "WARM", "COLD"):
        info = report["layers"][layer]
        assert "size_mb" in info
        assert "limit_mb" in info
        assert "headroom_mb" in info
        assert "ok" in info
        assert "path" in info
        assert "exists" in info
        assert isinstance(info["size_mb"], (int, float))
        assert isinstance(info["ok"], bool)


def test_violations_structure() -> None:
    """violations 列表 entry 字段齐."""
    report = _run_json()
    for v in report["violations"]:
        assert "layer" in v
        assert "size_mb" in v
        assert "limit_mb" in v
        assert "delta_mb" in v
        assert "delta_pct" in v
        # delta_mb/delta_pct 必须正数 (超阈值)
        assert v["delta_mb"] > 0
        assert v["delta_pct"] > 0


def test_hot_violation_when_over_limit() -> None:
    """若某层实际 > 阈值, violations 应包含该层 entry, summary 以 FAIL 开头。"""
    report = _run_json()
    # 当前实际: HOT 7.76MB < 80MB (不违规); WARM 364.57MB > 300MB (违规)
    # 测 WARM 违规路径 (HOT 已达标, 不再触发)
    warm_size = report["layers"]["WARM"]["size_mb"]
    warm_limit = report["layers"]["WARM"]["limit_mb"]
    if warm_size > warm_limit:
        violation_layers = [v["layer"] for v in report["violations"]]
        assert "WARM" in violation_layers
        assert report["summary"].startswith("FAIL")
    else:
        # 若 WARM 也达标, 则 violations 应为空, summary 为 OK
        violation_layers = [v["layer"] for v in report["violations"]]
        assert "WARM" not in violation_layers
        assert report["summary"].startswith("OK")


def test_json_output_parseable() -> None:
    """--json 输出可被 json.loads 解析, 含顶层 summary/violations/layers/limits_mb."""
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--json"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 0
    parsed = json.loads(proc.stdout)
    for key in ("limits_mb", "layers", "violations", "summary"):
        assert key in parsed, f"missing key: {key}"


def test_missing_layer_zero_size() -> None:
    """missing 文件 (COLD 当前未启用) size_mb=0.0 + exists=False."""
    report = _run_json()
    for layer in ("HOT", "WARM", "COLD"):
        info = report["layers"][layer]
        if not info["exists"]:
            assert info["size_mb"] == 0.0
            # missing 时一定 ok (不阻塞)
            assert info["ok"] is True
