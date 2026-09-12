"""v1.0 T07 准入域四表仓储 — admission_log / admission_label /
admission_set / admission_set_items (migration 097 schema).

R2 收缩批 (2026-09-13): 覆盖原 v1_admission_service 对这四张表的全部
SELECT / INSERT / UPDATE (裸 SQL 归零), service 层只保留业务编排
(维度校验 / ValueError / OperationalError 兜底 / 异常类型), 语义逐字不变。

  - **事务归调用方**: 本 repo 的写方法**不** commit — commit 点保留在
    v1_admission_service 原位置 (方法尾部一次 commit)。连接经
    ``backend.repository.db.get_connection`` (thread-local, autocommit
    ``isolation_level=None``), 与调用方注入连接 (conftest temp_db / 单测
    ``:memory:``) 二选一; 同线程内两次 ``get_connection()`` 返回同一连接,
    因此 service 侧 commit 与 repo 写入必然落在同一连接上。
  - **OperationalError 不吞**: 表缺失 (migration 097 未跑) 时 repo 原样
    抛 ``sqlite3.OperationalError``, 兜底返 0/[] 的降级语义留在 service 层。
  - ``insert_set`` 的 ``item_count`` 字面量 0、``refresh_set_item_count``
    的 ``COUNT(DISTINCT material_id)`` 子查询、``list_set_items`` 的
    ``ORDER BY si.material_id, al.dimension`` 均与原 service 语句逐字一致。
"""
from __future__ import annotations

import sqlite3
from typing import Any

from backend.repository.db import get_connection


class AdmissionRepository:
    """准入域四表仓储 (审计日志 + 8 维标注 + 标注集 + 集条目).

    所有方法在 ``self._conn or get_connection()`` 上执行, 不 commit —
    事务边界归调用方 (v1_admission_service)。
    """

    def __init__(self, conn: sqlite3.Connection | None = None) -> None:
        self._conn = conn

    def _c(self) -> sqlite3.Connection:
        return self._conn or get_connection()

    # ------------------------------------------------------------------
    # admission_log — quarantine 审计
    # ------------------------------------------------------------------
    def insert_log(
        self,
        material_id: str,
        body_hash: str,
        verdict: str,
        reason: str,
        matched_rule_id: int | None,
        raw_material_json: str,
        created_at: str,
    ) -> int:
        """插入一条准入审计 (allow/neutral/deny 全落, 不可变记录).

        原 v1_admission_service.quarantine 内 INSERT。
        """
        cur = self._c().execute(
            "INSERT INTO admission_log "
            "(material_id, body_hash, verdict, reason, matched_rule_id, "
            " raw_material_json, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                material_id,
                body_hash,
                verdict,
                reason,
                matched_rule_id,
                raw_material_json,
                created_at,
            ),
        )
        return cur.lastrowid or 0

    # ------------------------------------------------------------------
    # admission_label — 8 维标注 (一维一行, 同 material 同维度可多行)
    # ------------------------------------------------------------------
    def insert_label(
        self,
        material_id: str,
        dimension: str,
        value: str,
        annotator: str,
        confidence: float,
        created_at: str,
    ) -> int:
        """插入单维标注, 返回该行主键.

        原 v1_admission_service.label / add_to_set 内 INSERT (两处同语句)。
        """
        cur = self._c().execute(
            "INSERT INTO admission_label "
            "(material_id, dimension, value, annotator, confidence, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (material_id, dimension, value, annotator, confidence, created_at),
        )
        return cur.lastrowid or 0

    # ------------------------------------------------------------------
    # admission_set — 标注集元信息
    # ------------------------------------------------------------------
    def insert_set(self, name: str, schema_version: str, created_at: str) -> int:
        """创建标注集 (item_count 字面量 0, 由 add_to_set 阶段刷新).

        原 v1_admission_service.create_label_set 内 INSERT。
        """
        cur = self._c().execute(
            "INSERT INTO admission_set (name, schema_version, item_count, created_at) "
            "VALUES (?, ?, 0, ?)",
            (name, schema_version, created_at),
        )
        return cur.lastrowid or 0

    def find_set(self, set_id: int) -> sqlite3.Row | None:
        """按主键查标注集 (存在性判定, add_to_set 前置校验输入).

        原 v1_admission_service.add_to_set 内 SELECT。
        """
        return self._c().execute(
            "SELECT id FROM admission_set WHERE id = ?", (set_id,)
        ).fetchone()

    def refresh_set_item_count(self, set_id: int) -> None:
        """item_count 重算为集内 distinct material 数.

        原 v1_admission_service.add_to_set 内 UPDATE。
        """
        self._c().execute(
            "UPDATE admission_set SET item_count = "
            "(SELECT COUNT(DISTINCT material_id) FROM admission_set_items WHERE set_id = ?) "
            "WHERE id = ?",
            (set_id, set_id),
        )

    # ------------------------------------------------------------------
    # admission_set_items — 集-条目多对多
    # ------------------------------------------------------------------
    def insert_set_item(self, set_id: int, material_id: str, label_id: int) -> int:
        """收录 (set, material, label) 三元组 (PK 冲突时忽略).

        返回 rowcount — 0 表示该三元组已存在 (INSERT OR IGNORE 幂等命中)。
        原 v1_admission_service.add_to_set 内 INSERT OR IGNORE。
        """
        cur = self._c().execute(
            "INSERT OR IGNORE INTO admission_set_items "
            "(set_id, material_id, label_id) VALUES (?, ?, ?)",
            (set_id, material_id, label_id),
        )
        return cur.rowcount

    # ------------------------------------------------------------------
    # 只读查询
    # ------------------------------------------------------------------
    def list_set_items(self, set_id: int) -> list[dict[str, Any]]:
        """拉取标注集内所有 (material, label) 记录 — flat 列表.

        JOIN admission_label 展开 label 明细; 排序/键名与原
        v1_admission_service.get_set_items 逐字一致。
        """
        rows = self._c().execute(
            "SELECT si.set_id, si.material_id, si.label_id, "
            "       al.dimension, al.value, al.annotator, al.confidence, al.created_at "
            "FROM admission_set_items si "
            "JOIN admission_label al ON si.label_id = al.id "
            "WHERE si.set_id = ? "
            "ORDER BY si.material_id, al.dimension",
            (set_id,),
        ).fetchall()
        return [
            {
                "set_id": r[0],
                "material_id": r[1],
                "label_id": r[2],
                "dimension": r[3],
                "value": r[4],
                "annotator": r[5],
                "confidence": r[6],
                "created_at": r[7],
            }
            for r in rows
        ]
