# P1-4 Mutation Test — 验证 golden 数值真能 catch bug
#
# 对 simhash / decay_score / link_tags_to_concepts 三个核心函数做 11 类变异,
# 每个变异后跑对应的 golden test, 统计 catch rate。
#
# 运行: PYTHONPATH=. .venv/bin/python scripts/p1_4_mutation_test.py
#
# 退出码:
#   0 — 所有变异都被 golden test catch  (mutation score ≥ 80%)
#   1 — 部分变异没被 catch, golden 有盲点 (mutation score < 80%)

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# 变异定义 (old → new)
# ---------------------------------------------------------------------------

# (function_module, function_name, original, mutated, description)
# 注: golden test 用的是 backend.quality.simhash.compute_simhash (不是
# backend.services.simhash.simhash)。两套 simhash 实现并存 — services 是
# Phase 8 新实现 (FNV-1a), quality 是 Phase 0 旧实现 (SHA-256)。
MUTATIONS: list[tuple[str, str, str, str, str]] = [
    # ── compute_simhash (4 mutations, backend.quality.simhash) ────────────
    (
        "backend.quality.simhash",
        "compute_simhash",
        "if not tokens:",
        "if not tokens:\n        return 42",
        "M1: 空 token 返回 42 — 应返回 0 但被错改为固定值",
    ),
    (
        "backend.quality.simhash",
        "compute_simhash",
        "v[i] -= 1",
        "v[i] += 1",
        "M2: 反转位权 — 0/1 投票方向颠倒",
    ),
    (
        "backend.quality.simhash",
        "compute_simhash",
        "if v[i] > 0:",
        "if v[i] >= 0:",
        "M3: >0 → >=0 — 平票时也置位",
    ),
    (
        "backend.quality.simhash",
        "_hash_token",
        "digest = hashlib.sha256(token.encode(\"utf-8\")).digest()",
        "digest = hashlib.sha256((token + \"salt\").encode(\"utf-8\")).digest()",
        "M4: SHA-256 输入加盐 — fingerprint 全部重排",
    ),
    # ── decay_score (4 mutations, backend.services.retention_engine) ──────
    (
        "backend.services.retention_engine",
        "decay_score",
        "if days_since_access < 0:",
        "if days_since_access <= 0:\n        return initial * 0.5",
        "M5: <=0 早退并返回 0.5*initial — 0 天时原本是 1.0*initial",
    ),
    (
        "backend.services.retention_engine",
        "decay_score",
        "DECAY_FACTOR_PER_WINDOW ** (days_since_access / DECAY_WINDOW_DAYS)",
        "DECAY_FACTOR_PER_WINDOW ** days_since_access",
        "M6: 去掉 /7 — 衰减窗口从 7 天变 1 天",
    ),
    (
        "backend.services.retention_engine",
        "decay_score",
        "bounded = max(0.0, min(initial, raw))",
        "bounded = max(0.0, max(initial, raw))",
        "M7: min → max — 衰减后分数上限变 initial * initial",
    ),
    (
        "backend.services.retention_engine",
        "decay_score",
        "return round(bounded, 4)",
        "return bounded",
        "M8: 去掉 round — 精度漂移",
    ),
    # ── link_tags_to_concepts (3 mutations, backend.services.concept_linker) ─
    (
        "backend.services.concept_linker",
        "link_tags_to_concepts",
        "if slug and slug not in seen:",
        "if slug not in seen:",
        "M9: 去掉 `slug and` — None slug 加入列表",
    ),
    (
        "backend.services.concept_linker",
        "link_tags_to_concepts",
        "slugs.append(slug)",
        "slugs.append(slug + '_x')",
        "M10: 变形 slug — 末尾加 _x",
    ),
    (
        "backend.services.concept_linker",
        "link_tags_to_concepts",
        "seen = set()",
        "seen = []",
        "M11: set → list — dedup 失效",
    ),
]


# golden test 选择器 (用 -k 关键字匹配)
TEST_SELECTOR = {
    "backend.quality.simhash": "TestSimHashGolden or TestSimHashDeterminism or TestSimHashEdgeCases or TestHammingDistance or TestIsDuplicateGolden",
    "backend.services.retention_engine": "TestRetentionRunDecayFrozen or TestRetentionRecordAccessFrozen or TestRetentionHealthFrozen or TestDecayScorePrecisionFrozen",
    "backend.services.concept_linker": "TestLinkTagsToConceptsGolden",
}


# ---------------------------------------------------------------------------
# 变异注入 + 运行测试
# ---------------------------------------------------------------------------
#
# 用 .bak 文件保存原始内容, 测试后用 cp 还原 — 比 sentinel 包裹更可靠
# (sentinel marker 若与 Python 语法冲突会 SyntaxError, 见 git log)

import shutil


def apply_mutation(module_name: str, function_name: str, original: str, mutated: str) -> bool:
    """Inject mutation; backup original to .bak for safe revert."""
    file_path = Path("/Users/duke/Documents/hotspot") / (module_name.replace(".", "/") + ".py")
    if not file_path.exists():
        print(f"  ❌ file not found: {file_path}")
        return False
    content = file_path.read_text(encoding="utf-8")
    if original not in content:
        print(f"  ❌ original not found in {file_path}")
        return False
    # 备份原文件
    backup = file_path.with_suffix(file_path.suffix + ".bak")
    shutil.copy2(file_path, backup)
    # 应用 mutation
    new_content = content.replace(original, mutated, 1)
    file_path.write_text(new_content, encoding="utf-8")
    return True


def revert_mutation(module_name: str, function_name: str, original: str, mutated: str) -> None:
    """Revert by restoring from .bak backup (single source of truth)."""
    file_path = Path("/Users/duke/Documents/hotspot") / (module_name.replace(".", "/") + ".py")
    backup = file_path.with_suffix(file_path.suffix + ".bak")
    if backup.exists():
        shutil.copy2(backup, file_path)
        backup.unlink()
    else:
        # 兜底: 找不到 backup 时用 string replace (但会有 else 分支已存在的风险)
        print(f"  ⚠️  no .bak found for {file_path}, fallback to string replace")
        content = file_path.read_text(encoding="utf-8")
        content = content.replace(mutated, original, 1)
        file_path.write_text(content, encoding="utf-8")


def run_golden_tests(module_name: str) -> tuple[int, int, str]:
    """Run golden tests for a module, return (passed, failed, output)."""
    selector = TEST_SELECTOR.get(module_name, "TestSimHashGolden")
    cmd = [
        ".venv/bin/python",
        "-m",
        "pytest",
        "backend/tests/test_characterization_golden.py",
        "-k",
        selector,
        "--tb=no",
        "-q",
        "--no-header",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, cwd="/Users/duke/Documents/hotspot")
    output = result.stdout + result.stderr
    # 只解析最末尾的 summary 行 (===== N failed, M passed ... =====)
    # 避免从 "M passed, N deselected" 等中间行误取
    import re
    passed = 0
    failed = 0
    summary_line = None
    for line in output.splitlines():
        # pytest summary 行模式: "=== N failed, M passed ... ===" 或 "M passed ..."
        if "passed" in line and ("warning in" in line or "==" in line):
            summary_line = line
    if summary_line:
        m_pass = re.search(r"(\d+)\s+passed", summary_line)
        m_fail = re.search(r"(\d+)\s+failed", summary_line)
        if m_pass:
            passed = int(m_pass.group(1))
        if m_fail:
            failed = int(m_fail.group(1))
    return passed, failed, output


def main() -> int:
    print("=" * 70)
    print("P1-4 Mutation Test — 验证 golden test 能否 catch bug")
    print("=" * 70)
    print(f"共 {len(MUTATIONS)} 个变异\n")

    caught = 0
    survived = 0
    results: list[tuple[str, str, bool, int, int]] = []

    for module_name, func_name, original, mutated, desc in MUTATIONS:
        print(f"\n[{func_name}] {desc}")
        if not apply_mutation(module_name, func_name, original, mutated):
            survived += 1
            results.append((func_name, desc, False, 0, 0))
            continue
        try:
            passed, failed, output = run_golden_tests(module_name)
            # mutation caught = at least one test failed
            is_caught = failed > 0
            if is_caught:
                caught += 1
                marker = "✅ CAUGHT"
            else:
                survived += 1
                marker = "⚠️  SURVIVED (盲点!)"
            print(f"  {marker} — {passed} passed, {failed} failed")
            if not is_caught:
                print("  输出片段:", output.splitlines()[-3] if output else "(empty)")
            results.append((func_name, desc, is_caught, passed, failed))
        finally:
            revert_mutation(module_name, func_name, original, mutated)

    # 汇总
    print("\n" + "=" * 70)
    print("汇总")
    print("=" * 70)
    total = len(MUTATIONS)
    score = caught / total * 100
    print(f"总数: {total}")
    print(f"被 catch: {caught} ({score:.1f}%)")
    print(f"漏掉 (盲点): {survived}")

    print("\n详细:")
    for func_name, desc, is_caught, passed, failed in results:
        status = "✅" if is_caught else "⚠️"
        print(f"  {status} [{func_name}] {desc}  ({passed}P/{failed}F)")

    # mutation score threshold
    print(f"\nMutation Score: {score:.1f}%")
    if score >= 80.0:
        print("PASS — golden test 真能 catch bug (≥80%)")
        return 0
    else:
        print("FAIL — golden test 有盲点 (<80%), 需要补测试")
        return 1


if __name__ == "__main__":
    sys.exit(main())
