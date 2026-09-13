"""去重与指纹 — simhash 去重判定 + content_fingerprints 指纹写入。

Batch 4 Task C 从 ``collection_service.py`` 物理搬出 (行为零变更);
R2 收缩批 (2026-09-13) 后 ``write_fingerprints`` 的写语句下沉到
``CollectionRepository.insert_fingerprint`` (SQL 逐字一致), 本模块
保留值计算 (canonicalize/simhash/signed-64) / 逐条累加 / commit 点 / 日志:

- ``dedup_items``        — 原 ``CollectionService._dedup_items``: 采集结果
                           upsert 前的 simhash 去重 (URL 精确匹配 + 汉明距离
                           < 5, P1 分桶优化), 判定阶段不写指纹 (P0-5)。
- ``write_fingerprints`` — 原 ``CollectionService._write_fingerprints``:
                           入库成功后补写指纹 (FK 依赖 hotspot 行已存在)。
- ``_to_signed_64`` / ``_from_signed_64`` — SQLite signed-64 ↔ Python
                           unsigned-64 转换 (t1_raw_to_refine 及测试经
                           collection_service re-export 消费)。

线程亲和约定: 两个函数均为同步 sqlite3 操作, 调用方 (collection_service)
必须在 ``asyncio.to_thread`` 工作线程内调用 — ``get_connection`` 的
thread-local 语义依赖这一点。
"""
from collections import defaultdict

from backend.repository.collection_repo import CollectionRepository
from backend.repository.db import get_connection
from backend.services.simhash import (
    canonicalize_url,
    hamming_distance,
    normalize_title,
    simhash,
)

# SQLite BIGINT is signed 64-bit; simhash returns unsigned 64-bit.
_SIGNED_64_MASK = 0xFFFFFFFFFFFFFFFF
_SIGNED_64_OFFSET = 1 << 64


def _to_signed_64(val: int) -> int:
    """Convert unsigned 64-bit integer to signed 64-bit for SQLite storage."""
    return val - _SIGNED_64_OFFSET if val >= (1 << 63) else val


def _from_signed_64(val: int) -> int:
    """Convert signed 64-bit integer back to unsigned 64-bit."""
    return val + _SIGNED_64_OFFSET if val < 0 else val


def dedup_items(items: list, logger) -> list:
    """Deduplicate items using simhash fingerprints.

    For each item, compute a 64-bit simhash from ``title + summary``
    and compare against all existing fingerprints in the
    ``content_fingerprints`` table.  Items whose Hamming distance to
    an existing fingerprint is < 5 are considered duplicates and
    skipped.

    Non-duplicate items are written into ``content_fingerprints``
    immediately so that later items in the same batch see the
    updated fingerprint set (within-batch dedup).

    Parameters
    ----------
    items:
        Raw items returned by a collector, before DB upsert.

    Returns
    -------
    Filtered list with duplicates removed.
    """
    if not items:
        return items

    conn = get_connection()

    # Load existing fingerprints
    existing_rows = conn.execute(
        "SELECT hotspot_id, simhash FROM content_fingerprints"
    ).fetchall()
    # Convert from signed 64-bit (SQLite) to unsigned 64-bit (Python)
    existing = [
        (row[0], _from_signed_64(row[1]))
        for row in existing_rows
    ]

    # P1 性能: simhash 分桶索引 — 64-bit 指纹按 8×8-bit 块建桶。
    # Hamming 距离 < 5 (即 ≤4) 的两个指纹必然在 8 块中至少 4 块相同
    # (抽屉原理), 因此同桶候选集必包含全部真重复, 无需全表线性扫描。
    # 查找从 O(M) (全表) 降为 O(桶内候选数) ≈ O(1), 整体 O(N+M) 替代
    # O(N×M)。此为纯算法优化, 判定结果与全表扫描完全一致。
    _BUCKET_BITS = 8  # 每块 8 bit

    def _simhash_buckets(fp: int) -> list[int]:
        return [(fp >> (8 * i)) & 0xFF for i in range(8)]

    buckets: dict[int, list[tuple[str, int]]] = defaultdict(list)
    for eid, efp in existing:
        for b in set(_simhash_buckets(efp)):
            buckets[b].append((eid, efp))

    # Load existing canonical URLs for fast exact-match check
    existing_urls = {
        row[0]
        for row in conn.execute(
            "SELECT url_canonical FROM content_fingerprints"
        ).fetchall()
    }

    result: list = []
    for item in items:
        url_str = str(item.url)
        url_canonical = canonicalize_url(url_str)
        text = item.title
        if item.summary:
            text += " " + item.summary
        fp = simhash(text)

        # Fast path: exact URL match
        if url_canonical and url_canonical in existing_urls:
            # 降噪 (v085-review F3): 重复 item 每轮重付, info 级每轮刷上千条
            logger.debug(
                f"Dedup skipped {item.id}: URL match {url_canonical}"
            )
            continue

        # Simhash Hamming distance check — 只比较同桶候选 (P1 分桶优化)
        duplicate = False
        candidates: set[tuple[str, int]] = set()
        for b in _simhash_buckets(fp):
            for cand in buckets.get(b, ()):
                candidates.add(cand)
        for existing_id, existing_fp in candidates:
            if hamming_distance(fp, existing_fp) < 5:
                logger.info(
                    f"Dedup skipped {item.id}: duplicate of {existing_id}"
                )
                duplicate = True
                break

        if duplicate:
            continue

        # P0-5: 不在去重阶段写 content_fingerprints — hotspot 行此时尚不存在,
        # FK (hotspot_id REFERENCES hotspots(id)) 必失败, 指纹丢失导致跨轮去重失效。
        # 改为: 入库成功后由 write_fingerprints 补写 (见 run_once/run_one 调用点)。

        # Update in-memory sets for within-batch dedup
        existing.append((item.id, fp))
        for b in set(_simhash_buckets(fp)):
            buckets[b].append((item.id, fp))
        if url_canonical:
            existing_urls.add(url_canonical)

        result.append(item)

    return result


def write_fingerprints(items: list, logger) -> int:
    """P0-5: 入库成功后补写 content_fingerprints 指纹。

    必须在 hotspot 行已 upsert 之后调用 (content_fingerprints.hotspot_id
    有 FK REFERENCES hotspots(id)); 此前在 dedup_items 内提前插入,
    新条目 hotspot 行不存在 → FK 失败被吞 → 指纹丢失 → 跨轮去重失效。
    现在改为入库后补写: FK 满足, 指纹首轮即落库, 同 URL 二次采集被拒。

    Returns: 实际写入的行数。
    """
    if not items:
        return 0
    conn = get_connection()
    # conn 注入 repo (而非 repo 回退 get_connection): 宿主/单测可在
    # collection_dedup 命名空间 patch get_connection, 注入保证写语句
    # 与 commit 落在同一连接 (含测试 mock)。
    repo = CollectionRepository(conn)
    written = 0
    try:
        for item in items:
            url_canonical = canonicalize_url(str(item.url))
            title_norm = normalize_title(item.title)
            text = item.title
            if item.summary:
                text += " " + item.summary
            fp = simhash(text)
            written += repo.insert_fingerprint(
                item.id,
                _to_signed_64(fp),
                url_canonical or "",
                title_norm or "",
            )
        conn.commit()
    except Exception as e:
        # 指纹补写失败不阻塞主流程 (去重是尽力而为, 下次采集会再判重)
        logger.warning(f"_write_fingerprints failed: {e}")
        return 0
    if written:
        logger.info(f"_write_fingerprints: {written} fingerprints written")
    return written
