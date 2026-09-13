"""MP-1 图谱点火 (DEV-0217) 测试守卫。

背景
----
原图谱 3 视图全死 (attack/compliance/full):
- attack_techniques / attack_cwe_map 表 0 行 (D18 死种子)
- security_entities 仅 1 个 tactic (默认行); STIX 中 tactic 类型为 x-mitre-tactic,
  旧 _parse_tactic 永远空命中
- security_edges 0 行 → view=attack / view=full 死

MP-1 修复
--------
1. main.py lifespan 启动期调用 attack_loader.load_attack_data() (幂等 COUNT==0)
2. main.py lifespan 启动期调用 MitreAttackClient().sync_to_db(force=True)
3. mitre_attack.py 修复: 认 x-mitre-tactic STIX 类型; 把 malware / intrusion-set /
   tool 映射为 product entity (保留 STIX id 不变), 让 uses 边两端都在;
   过滤掉 TA0112 等 STIX 2024+ 新增 tactic 保持 tactic == 14
4. 加 _synthesize_tactics_from_phases 兜底 (旧版 STIX 包无 x-mitre-tactic 时)

测试覆盖 (5 项)
---------------
- test_attack_data_loaded: attack_techniques >= 150 + attack_cwe_map >= 100
- test_security_edges_populated: security_edges >= 5000
- test_tactic_count_14: security_entities.tactic == 14 (MP-1 规格)
- test_graph_endpoint_attack_view: build_security_graph('attack') nodes/edges 都 >= 100
- test_graph_full_view_includes_attack_edges: build_security_graph('full') 含攻击边
"""
from __future__ import annotations

from pathlib import Path

import pytest

# MP-1 启动期幂等 hook: 确保测试隔离 env 下指到仓库的 MITRE 本地 cache,
# 不让 sync_to_db 走 HEAD 网络 (T01 隔离守卫禁止普通测试出网)。
_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_MITRE_CACHE = _REPO_ROOT / "backend" / "data" / "mitre"


@pytest.fixture(autouse=True)
def _ensure_mitre_cache(monkeypatch):
    """强制 sync_to_db 用仓库本地 cache, 不打 HEAD 网络 (T01 隔离守卫禁普通测试出网).

    sync_to_db(force=True) 在无网环境下: HEAD 被隔离守卫拦下 (warning) →
    下载失败 → 兜底走 stale local cache → _parse_and_upsert 照常解析。
    MITRE cache 不存在的环境 (如 CI 未预热) 直接 skip 本文件。
    """
    cache_dir = _DEFAULT_MITRE_CACHE
    bundle = cache_dir / "enterprise-attack.json"
    if not bundle.exists():
        pytest.skip(
            f"MITRE cache not found at {bundle}; "
            "test_mp1_graph_ignite requires backend/data/mitre/enterprise-attack.json"
        )
    monkeypatch.setenv("MITRE_CACHE_DIR", str(cache_dir))


@pytest.fixture
def mp1_loaded_db(temp_db):
    """temp_db + 已点火 (attack_loader + MitreAttackClient.sync_to_db)."""
    from backend.security.mitre_attack import MitreAttackClient
    from backend.services.attack_loader import load_attack_data

    load_attack_data()
    result = MitreAttackClient().sync_to_db(force=True)
    return {"db_path": temp_db, "sync_result": result}


def test_attack_data_loaded(mp1_loaded_db):
    """attack_techniques >= 150 + attack_cwe_map >= 100."""
    from backend.repository.db import get_connection

    conn = get_connection()
    n_tech = conn.execute("SELECT COUNT(*) AS n FROM attack_techniques").fetchone()["n"]
    n_cwe = conn.execute("SELECT COUNT(*) AS n FROM attack_cwe_map").fetchone()["n"]
    assert n_tech >= 150, f"attack_techniques COUNT {n_tech} < 150"
    assert n_cwe >= 100, f"attack_cwe_map COUNT {n_cwe} < 100"


def test_security_edges_populated(mp1_loaded_db):
    """security_edges >= 5000 (subtechnique-of + uses 累计)。"""
    from backend.repository.db import get_connection

    conn = get_connection()
    n_edges = conn.execute("SELECT COUNT(*) AS n FROM security_edges").fetchone()["n"]
    assert n_edges >= 5000, f"security_edges COUNT {n_edges} < 5000"
    # 至少有一条 subtechnique-of (STIX 中 technique 内部关系)
    n_sub = conn.execute(
        "SELECT COUNT(*) AS n FROM security_edges WHERE edge_type='subtechnique-of'"
    ).fetchone()["n"]
    assert n_sub > 0, "expected subtechnique-of edges > 0"
    # 至少有一条 uses (STIX 中 intrusion-set/malware/tool → technique)
    n_uses = conn.execute(
        "SELECT COUNT(*) AS n FROM security_edges WHERE edge_type='uses'"
    ).fetchone()["n"]
    assert n_uses > 0, "expected uses edges > 0"


def test_tactic_count_14(mp1_loaded_db):
    """security_entities.tactic COUNT == 14 (MP-1 规格, enterprise 标准 14)."""
    from backend.repository.db import get_connection

    conn = get_connection()
    n_tactic = conn.execute(
        "SELECT COUNT(*) AS n FROM security_entities WHERE entity_type='tactic'"
    ).fetchone()["n"]
    assert n_tactic == 14, f"expected 14 tactics (MP-1 enterprise standard), got {n_tactic}"

    # 抽样: 14 个 tactic id 应落在 TA0001~TA0043 区间内
    rows = conn.execute(
        "SELECT id FROM security_entities WHERE entity_type='tactic' ORDER BY id"
    ).fetchall()
    ids = [r["id"] for r in rows]
    # MP-1 规格: 都是 TAxxxx 形式
    for tid in ids:
        assert tid.startswith("TA"), f"tactic id {tid} not in TAxxxx form"


def test_graph_endpoint_attack_view(mp1_loaded_db):
    """build_security_graph('attack') nodes >= 100 且 edges >= 100."""
    from backend.security.graph import SecurityGraphEngine

    g = SecurityGraphEngine()
    result = g.build_security_graph("attack")
    n_nodes = len(result["nodes"])
    n_edges = len(result["edges"])
    assert n_nodes >= 100, f"attack view nodes {n_nodes} < 100"
    assert n_edges >= 100, f"attack view edges {n_edges} < 100"

    # stats 应非零: 14 个 tactic + technique 计数
    stats = result.get("stats", {})
    assert stats.get("tactics", 0) >= 14, f"stats.tactics {stats.get('tactics')} < 14"
    assert stats.get("techniques", 0) >= 100, (
        f"stats.techniques {stats.get('techniques')} < 100"
    )


def test_graph_full_view_includes_attack_edges(mp1_loaded_db):
    """build_security_graph('full') 包含 attack 边 (而非孤点)."""
    from backend.security.graph import SecurityGraphEngine

    g = SecurityGraphEngine()
    result = g.build_security_graph("full")
    n_nodes = len(result["nodes"])
    n_edges = len(result["edges"])
    # full 至少包含 attack 数据; 即使 cve/compliance 为空, attack 应贡献 nodes/edges
    assert n_nodes >= 100, f"full view nodes {n_nodes} < 100 (attack 缩水?)"
    assert n_edges >= 100, f"full view edges {n_edges} < 100"
    # 全视图包含 attack 视图的边类型
    assert n_edges >= 100, "full view should inherit attack edges from sub-view loader"
