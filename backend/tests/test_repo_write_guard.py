"""R2 守卫 — 一表一 repo 一 writer（档 A 冻结增量）。

规则来源: ``docs/FEATURE_DECOMPOSITION_2026-09-12.md`` R2 — 任何表要么有唯一
repository writer，要么在豁免清单显式登记。本测试 AST 扫描 **整个 backend/**
（Batch 3 P1-2 扩面; 排除 ``api/`` — R3 守卫已封死 api 层直连 SQL、``tests/``、
``migrations/``、``__pycache__``），收集全部 INSERT/UPDATE/DELETE/REPLACE INTO
语句（含 f-string 与隐式拼接的多行字符串）→ 「写入方直写表」集合。

断言:
1. **写表必须 ∈ repo 治理表 ∪ ``_EXEMPT_TABLES``**（repo 治理表 =
   ``backend/repository/**`` 中的静态写表）。不在任一集合的新表写入即失败
   —— 这就是「冻结增量」语义: 存量违规被豁免清单显式登记，新代码/新表
   必须走 repo。
2. **动态 SQL 命中文件必须 ⊆ ``_DYNAMIC_SQL_FILES``**（Batch 3 P1-1）。
   扫描器对 f-string 中 "写关键字后直接跟插值" 的语句置 dynamic 标志;
   未登记的动态 SQL 文件即失败 —— 杜绝 ``f"DELETE FROM {var}"`` 静默逃逸。
   唯一豁免的插值模式是 blessed accessor ``{knowledge_items_table()}``:
   其返回值静态可知（``knowledge_items`` / ``warm.knowledge_items``），
   扫描器按静态表 ``knowledge_items`` 处理，不算动态。

豁免清单纪律（docstring 即契约）:
- ``_EXEMPT_TABLES`` 只许收缩不许扩张（2026-09-12 P1-2 扫面扩到全 backend
  是冻结增量的正常扩面: 新纳入目录的存量直写表如实登记，不是放松）。
  每张表标注宿主文件；收缩路径 = 后续批次逐表补 repo 后同步删除条目。
- ``_DYNAMIC_SQL_FILES`` 文件级豁免: 该文件整体跳过表级扫描，因此其中
  新增的静态写语句同样不被守卫覆盖 —— 收敛该文件时一并删除豁免。
- 注释 / docstring 不参与扫描（docstring 按 AST docstring 位置剔除，
  注释本就不进 AST），纯文本中的 SQL 字样不误报。
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent

# 写语句: 关键字必须位于行首（SQL 字符串的习惯排版），后跟表名。
# 行首锚定 + 表名捕获保证 docstring/普通文本中的 "update the ..." 不误报。
_WRITE_LINE_RE = re.compile(
    r"(?im)^[ \t]*(?:INSERT\s+OR\s+(?:REPLACE|IGNORE)\s+INTO"
    r"|INSERT\s+INTO|REPLACE\s+INTO|UPDATE|DELETE\s+FROM)"
    r"\s+([A-Za-z_][A-Za-z0-9_.]*)"
)

# 动态表名: f-string 字面片段在写关键字后直接结束（表名来自下一个插值），
# 如 f"DELETE FROM {table} WHERE ..."。仅对 f-string 的字面部分生效 ——
# 独立字符串常量（事件名 "update" 等）不触发。
_DYNAMIC_TAIL_RE = re.compile(
    r"(?im)^[ \t]*(?:INSERT\s+OR\s+\w+\s+INTO|INSERT\s+INTO"
    r"|REPLACE\s+INTO|UPDATE|DELETE\s+FROM)\s*$"
)

# writer 扫描排除的 backend 顶层目录:
# - api/: api 层直连 SQL 由 R3 守卫 (test_api_layer_guard.py) 封死, 不归本守卫
# - tests/: 测试夹具自建临时表, 非生产写路径
# - migrations/: schema DDL, 非业务写路径
# - repository/: repo 即治理源 — repo 写的表按定义 ∈ governed 集合, 把 repo
#   当 writer 扫不产生任何约束增量; repo 内部的 f"{self.TABLE}" 注入属 repo
#   实现细节, 不参与 dynamic 判定。
_WRITER_SCAN_EXCLUDE_TOP = {"api", "tests", "migrations", "repository"}

# ---------------------------------------------------------------------------
# 豁免清单（冻结快照 2026-09-12, Batch 3 档 A; P1-2 扫面扩到全 backend 后
# 按新扫描结果如实扩面 + 修正宿主标注）— 只许收缩不许扩张。
# 每张表标注宿主文件（多个宿主全部列出）。
# ---------------------------------------------------------------------------
_EXEMPT_TABLES: dict[str, str] = {
    # admission_*: v1 准入域 (Batch 3+ 计划并入 repo 化 v1_evidence 域)
    "admission_label": "services/v1_admission_service.py",
    "admission_log": "services/v1_admission_service.py",
    "admission_set": "services/v1_admission_service.py",
    "admission_set_items": "services/v1_admission_service.py",
    # agent_memory 子包
    "agent_preferences": "services/agent_memory/miner.py",
    "feedback_log": "services/agent_memory/memory.py",
    # 告警域
    "alert_deliveries": "services/alert_dispatcher.py",
    "alert_events": "services/alert_engine.py, services/alert_service.py",
    # 安全图谱域 (ATT&CK 加载器)
    "attack_cwe_map": "services/attack_loader.py",
    "attack_techniques": "services/attack_loader.py",
    # attention_events: P1-2 扩面补登宿主 scheduler/jobs/maintenance.py (TTL 清理)
    "attention_events": (
        "services/attention_events_service.py, scheduler/jobs/maintenance.py"
    ),
    # 审计 / worker 协调 (P1-2: 修正宿主标注失真 — audit_log 真实宿主还
    # 包括 backend 根 observability_records.py, 此前只列了 services 侧)
    "audit_log": (
        "observability_records.py, services/legacy_hold_service.py, "
        "services/worker_coordinator.py"
    ),
    "dead_letter": "services/worker_coordinator.py",
    "worker_runs": "services/worker_coordinator.py",
    # CodeGarden drift (P1 病灶, 见规格 §2)
    "cg_drift_assessments": "services/codegarden_drift.py",
    # 采集域 (P1-2 扩面补登宿主 scheduler/jobs/collect.py)
    # Batch 4 Task C (2026-09-12): collection_service 拆 facade, 写语句随宿主
    # 搬至 collection_dedup (content_fingerprints) / collection_pipeline
    # (collection_runs/crawler_runs/raw_items); 表集合不变, 仅宿主标注同步。
    "collect_validations": "services/collect_validator.py",
    "collection_runs": "services/collection_pipeline.py, scheduler/jobs/collect.py",
    "content_fingerprints": "services/collection_dedup.py",
    "crawler_runs": "services/collection_pipeline.py",
    "raw_items": "services/collection_pipeline.py",
    # info_filter gate
    "info_filter_rules": "services/info_filter_service.py",
    # 知识域
    "knowledge_chunks": "services/chunk_service.py",
    "knowledge_graph": "services/graph_builder.py",
    "knowledge_links": "services/knowledge_service.py, services/triggers/t2_refine_to_link.py",
    "v1_knowledge_adoptions": "services/knowledge_service.py",
    # ai_hub 域 (R6 红线: 未裁决不动, 收缩须 owner 授权)
    "llm_cache": "services/ai_hub/cache.py",
    "llm_usage_log": "services/ai_hub/usage.py",
    # agent_loop
    "loop_checkpoints": "services/agent_loop/checkpoint.py",
    # 观测域 (P1-2 扩面补登宿主 scheduler/jobs/maintenance.py)
    "observability_alerts": (
        "services/observability_query_service.py, scheduler/jobs/maintenance.py"
    ),
    # planning 域
    "planning_action_log": "services/planning_service.py",
    "planning_actions": "services/planning_service.py",
    # playbook 域
    "playbook_runs": "services/playbook_engine/scheduler.py",
    "playbook_schedules": "services/playbook_engine/scheduler.py",
    # skill 域
    "skill_runs": "services/skill_runner/result.py",
    "user_skills": "services/skill_builder/core.py",
    # trigger_gate 域 (queue.py 表名是显式字面量; legacy_hold_service 同表;
    # P1-2 扩面补登宿主 scheduler/jobs/worker_pump.py)
    "trigger_tickets": (
        "services/legacy_hold_service.py, services/trigger_gate/queue.py, "
        "scheduler/jobs/worker_pump.py"
    ),
    # v1 证据域 (case_service 的 materials 快照表)
    "v1_case_materials": "services/case_service.py",
    # legacy 迁移 (一次性迁移服务, 证据写入 v1_legacy_*)
    "v1_legacy_mapping": "services/legacy_migrate_v1.py",
    "v1_legacy_promote_log": "services/legacy_migrate_v1.py",
    # maintenance_service 的两个静态写 (该文件的动态 DELETE 另见 _DYNAMIC_SQL_FILES)
    "export_cache": "services/maintenance_service.py",
    "quality_check_logs_archive": "services/maintenance_service.py",
    # ------------------------------------------------------------------
    # P1-2 扩面新增 (扫到全 backend 后新纳入的存量直写表, 逐条标注宿主)
    # ------------------------------------------------------------------
    # 观测记录域 (backend 根 observability_records.py: job/agent/api/process
    # 生命周期 + 审计写入; 与 services 层无依赖方向冲突, 直写为既定设计)
    "agent_runs": "observability_records.py",
    "api_events": "observability_records.py",
    "job_runs": "observability_records.py",
    "process_events": "observability_records.py",
    # kl_pipeline 队列域 (queue 自管生命周期, 表名显式字面量)
    "kl_queue": "kl_pipeline/queue.py",
    # kl_pipeline token 账本
    "token_ledger": "kl_pipeline/obs/ledger.py",
    # security 富化 job 的 item↔entity 桥接表写入
    "item_entities": "scheduler/jobs/security.py",
    # collectors 质量钩子的拒绝日志
    "quality_rejection_log": "collectors/quality_hook.py",
    # FTS5 维护 (INSERT INTO x(x) VALUES('rebuild') 是 FTS5 命令语法, 非业务行写入)
    "unified_fts": "scheduler/jobs/maintenance.py",
    "wiki_items_fts": "scheduler/jobs/maintenance.py, wiki_fs/store.py",
    "hotspots_trigram_fts": "secnews_dashboard.py",
    # 定时聚合表 (scheduler/jobs/maintenance.py 每小时 rollup)
    "api_metrics_hourly": "scheduler/jobs/maintenance.py",
    # 已知误报登记: quality/jobs.py 的日志字符串 "update item quality failed"
    # 被行首锚定正则识别为 `UPDATE item`; 非真实写表。登记以免守卫误报,
    # 收敛正则后从清单删除。
    "item": "quality/jobs.py (regex 误报: 日志字符串, 非写表)",
}

# 动态 SQL 文件级豁免 — 文件整体跳过表级扫描 (但 dynamic 命中仍须登记在此)。
_DYNAMIC_SQL_FILES: dict[str, str] = {
    # 表名来自局部变量的参数化 DELETE (f"DELETE FROM {var}"):
    # {sh}=sync_history, {table}=collection_history/hotspot_history,
    # {qcl}=quality_check_logs, {ki}=knowledge_items — 无静态表名字面量,
    # 无法逐表登记; Batch 3+ 该文件收敛到 repo 时一并删除本豁免。
    "services/maintenance_service.py": (
        "表名参数化 DELETE (sync_history/collection_history/hotspot_history/"
        "quality_check_logs/knowledge_items), 无静态表名字面量"
    ),
    # P1-2 扩面新增: 同款参数化 TTL 清理 f"DELETE FROM {table} WHERE {col} < ?"
    # (表/列对来自本文件常量表: attention_events/audit_log/api_events/…,
    # 无静态表名字面量); 收敛到统一 retention repo 时删除本豁免。
    "scheduler/jobs/maintenance.py": (
        "表名参数化 TTL DELETE (attention_events/audit_log/api_events 等), "
        "无静态表名字面量"
    ),
}


def _docstring_node_ids(tree: ast.AST) -> set[int]:
    """Collect ids of module/class/function docstring string constants."""
    ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = node.body
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                ids.add(id(body[0].value))
    return ids


def _interp_table_name(expr: ast.expr) -> str | None:
    """Resolve an f-string interpolation to a statically-known table name.

    Only the blessed accessor pattern resolves: an interpolation of
    ``knowledge_items_table()`` (direct call, bare name or attribute) whose
    value is statically ``knowledge_items`` / ``warm.knowledge_items``
    (see ``backend/repository/db.py``). Any other interpolation after a
    write keyword leaves the statement dynamically-tabled.
    """
    target: ast.expr = expr
    if isinstance(target, ast.Call):
        target = target.func
    if isinstance(target, ast.Name):
        name = target.id
    elif isinstance(target, ast.Attribute):
        name = target.attr
    else:
        return None
    return "knowledge_items" if name == "knowledge_items_table" else None


def _scan_write_tables(path: Path) -> tuple[set[str], bool]:
    """Return (tables written by static SQL, has dynamic-table SQL)."""
    tables: set[str] = set()
    dynamic = False
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    docstrings = _docstring_node_ids(tree)
    for node in ast.walk(tree):
        if id(node) in docstrings:
            continue
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            for m in _WRITE_LINE_RE.finditer(node.value):
                tables.add(m.group(1).lower())
        elif isinstance(node, ast.JoinedStr):
            parts = node.values
            for i, part in enumerate(parts):
                if not (isinstance(part, ast.Constant) and isinstance(part.value, str)):
                    continue
                if _DYNAMIC_TAIL_RE.search(part.value):
                    # 写关键字后直接跟插值 → 动态表名, 除非插值是 blessed
                    # accessor (knowledge_items_table()), 其返回值静态可知。
                    nxt = parts[i + 1] if i + 1 < len(parts) else None
                    resolved = (
                        _interp_table_name(nxt.value)
                        if isinstance(nxt, ast.FormattedValue)
                        else None
                    )
                    if resolved is None:
                        dynamic = True
                    else:
                        tables.add(resolved)
                for m in _WRITE_LINE_RE.finditer(part.value):
                    tables.add(m.group(1).lower())
    return tables, dynamic


def _iter_py(root: Path):
    yield from sorted(root.rglob("*.py"))


def _writer_scope_files():
    """Yield (relpath, Path) for every backend .py in the writer scan scope."""
    for path in _iter_py(BACKEND):
        rel = path.relative_to(BACKEND).as_posix()
        parts = rel.split("/")
        if any(seg == "__pycache__" for seg in parts):
            continue
        if parts[0] in _WRITER_SCAN_EXCLUDE_TOP:
            continue
        yield rel, path


def _repo_governed_tables() -> set[str]:
    """Tables with an INSERT/UPDATE/DELETE/REPLACE in backend/repository/**."""
    governed: set[str] = set()
    for path in _iter_py(BACKEND / "repository"):
        tables, _ = _scan_write_tables(path)
        governed |= tables
    return governed


def test_backend_writes_only_governed_or_exempt_tables():
    """backend 全域写入的表必须 ∈ repo 治理表 ∪ 豁免清单（R2 冻结增量）."""
    governed = _repo_governed_tables()
    assert governed, "repository 扫描结果为空 — 守卫自身失效"

    dynamic_unregistered: list[str] = []
    violations: list[str] = []
    for rel, path in _writer_scope_files():
        tables, dynamic = _scan_write_tables(path)
        if dynamic and rel not in _DYNAMIC_SQL_FILES:
            dynamic_unregistered.append(rel)
        if rel in _DYNAMIC_SQL_FILES:
            continue  # 文件级豁免: 表名参数化, 无法静态解析
        for table in sorted(tables):
            if table not in governed and table not in _EXEMPT_TABLES:
                violations.append(f"{rel}: 写表 {table!r} — 无 repo 且不在豁免清单")

    assert not dynamic_unregistered, (
        "R2 违规 (P1-1): 以下文件含动态表名写语句 (f-string 插值表名),\n"
        "既未列入 _DYNAMIC_SQL_FILES 也非 blessed accessor "
        "{knowledge_items_table()} 模式。\n"
        "新代码必须走 backend/repository/*_repo.py 或使用静态表名;\n"
        "确属存量动态 SQL 时在 _DYNAMIC_SQL_FILES 登记文件并注释原因:\n  "
        + "\n  ".join(dynamic_unregistered)
    )
    assert not violations, (
        "R2 违规 (一表一 repo 一 writer): backend 出现无 repo 且未豁免的表写入。\n"
        "新代码/新表必须走 backend/repository/*_repo.py；如确属存量表遗漏登记，\n"
        "先核对该表是否真的无 repo writer，再决定补 repo 还是登记豁免"
        "（豁免清单只许收缩不许扩张）:\n  " + "\n  ".join(violations)
    )


def test_dynamic_sql_exemptions_point_to_real_files():
    """_DYNAMIC_SQL_FILES 中的路径必须真实存在（防止重构后豁免失效悬空）."""
    for rel in _DYNAMIC_SQL_FILES:
        assert (BACKEND / rel).exists(), f"动态 SQL 豁免指向不存在的文件: {rel}"


def test_dynamic_table_write_is_flagged(tmp_path):
    """P1-1 反例: f"DELETE FROM {var}" 必须被判为动态 SQL, 不许静默通过."""
    src = tmp_path / "rogue_service.py"
    src.write_text(
        "def purge(conn, table):\n"
        '    conn.execute(f"DELETE FROM {table} WHERE id = 1")\n',
        encoding="utf-8",
    )
    tables, dynamic = _scan_write_tables(src)
    assert dynamic, "动态写语句未被识别 — 守卫检测失效 (P1-1 回归)"
    assert not tables, f"动态写语句不应产出静态表名: {tables}"


def test_blessed_table_accessor_interpolation_is_static(tmp_path):
    """blessed 模式: {knowledge_items_table()} 按静态表 knowledge_items 处理,
    不触发 dynamic 标志 — knowledge_repo 等经单一真相源注入的写路径不误伤."""
    src = tmp_path / "repo_writer.py"
    src.write_text(
        "from backend.repository.db import knowledge_items_table\n"
        "def purge(conn, item_id):\n"
        '    conn.execute(f"DELETE FROM {knowledge_items_table()} WHERE id = ?", (item_id,))\n',
        encoding="utf-8",
    )
    tables, dynamic = _scan_write_tables(src)
    assert not dynamic
    assert tables == {"knowledge_items"}
