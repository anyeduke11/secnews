"""cve_enrich_service — CVE 空壳条目回源富化 (DEV-0300)。

第一性原理: CVE 条目的原语 = 「编号 (寻址) + 结构化漏洞事实 (内容)」。
编号本身零信息量 — 只有编号的 knowledge 条目 (enricher 从标题提取写入)
被 wiki 检索到后, 深读拿空原文 → LLM 幻觉或拒绝 → 浪费算力且输出无据。

本服务补「事实」半边: NVD 2.0 API 公开回源 (免 key, 限流 5/30s 足够单机),
解析为奇安信 TI 漏洞通告同构的结构化事实 (描述/CVSS/厂商产品/影响版本/
利用状态/参考链接), 缓存进 security_entities (id="cve:{编号}", metadata=JSON)。

- ``is_cve_shell(topic)``: 空壳判定 (topic 只是编号或极短提及, 无实质内容)
- ``fetch_cve_facts(cve_id)``: 回源 → 结构化事实 dict (缓存命中免出站)
- ``compose_cve_brief(facts)``: 事实 → 中文结构化原文 (深读 LLM 的输入,
  骨架对齐 ti.qianxin.com 漏洞通告: 漏洞信息/威胁评估/影响版本/参考链接)
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from backend.logging_config import logger

_CVE_RE = re.compile(r"CVE-\d{4}-\d{4,}", re.IGNORECASE)
_NVD_API = "https://services.nvd.nist.gov/rest/json/cves/2.0?cveId={cve_id}"
_CACHE_DAYS = 30
_TIMEOUT_S = 20

# 空壳判定: 去掉 CVE 编号与分隔符后剩余实质字符 < 40 → 无分析价值
_SHELL_MIN_CONTENT_CHARS = 40


def extract_cve_id(text: str) -> str | None:
    """从文本提取首个 CVE 编号 (无则 None)。"""
    m = _CVE_RE.search(text or "")
    return m.group(0).upper() if m else None


def is_cve_shell(topic: str | None) -> bool:
    """空壳判定: 提取编号后剩余实质内容不足 → 该条目只是编号登记。

    「CVE-2026-21589 漏洞」→ shell; 「CVE-2026-21589: Atlassian 双重
    URL 解码致任意文件读取, 已有 PoC」→ 非空壳 (有实质描述)。
    """
    t = (topic or "").strip()
    if not t:
        return False
    if not _CVE_RE.search(t):
        return False
    residue = _CVE_RE.sub("", t)
    residue = re.sub(r"[\s\-—–_,.。:：;；()（）\[\]【】\\/&+#|]|CVE|编号|漏洞", "", residue)
    return len(residue) < _SHELL_MIN_CONTENT_CHARS


def get_cached_facts(cve_id: str) -> dict[str, Any] | None:
    """security_entities 缓存读取 (CACHE_DAYS 内有效)。"""
    from backend.repository.db import get_connection

    row = get_connection().execute(
        "SELECT metadata, updated_at FROM security_entities WHERE id = ?",
        (f"cve:{cve_id.upper()}",),
    ).fetchone()
    if not row:
        return None
    try:
        meta = json.loads(row["metadata"] or "{}")
    except Exception:
        return None
    if not isinstance(meta, dict) or "facts" not in meta:
        return None
    try:
        updated = datetime.fromisoformat(row["updated_at"])
        if updated.tzinfo is None:
            updated = updated.replace(tzinfo=timezone.utc)  # SQL datetime('now') 是 naive UTC
        age = datetime.now(timezone.utc) - updated
        if age > timedelta(days=_CACHE_DAYS):
            return None
    except Exception:
        return None
    return meta["facts"] if isinstance(meta["facts"], dict) else None


def _cache_facts(cve_id: str, facts: dict[str, Any]) -> None:
    """事实写 security_entities (upsert, metadata.facts 承载缓存)。"""
    from backend.repository.db import get_connection

    conn = get_connection()
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO security_entities (id, entity_type, name, description, "
        "external_ref, metadata, created_at, updated_at) "
        "VALUES (?, 'cve', ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(id) DO UPDATE SET description=excluded.description, "
        "external_ref=excluded.external_ref, metadata=excluded.metadata, "
        "updated_at=excluded.updated_at",
        (f"cve:{cve_id.upper()}", cve_id.upper(),
         facts.get("description_en", "")[:500],
         facts.get("nvd_url", ""),
         json.dumps({"facts": facts}, ensure_ascii=False), now, now),
    )
    conn.commit()


def fetch_cve_facts(cve_id: str, *, force: bool = False) -> dict[str, Any] | None:
    """CVE → 结构化事实 (NVD 2.0 回源, 缓存优先)。

    Returns:
        facts dict 或 None (NVD 无此编号 / 出站失败 — 调用方诚实拒绝深读)。
    """
    cve_id = (cve_id or "").upper()
    if not cve_id:
        return None
    if not force:
        cached = get_cached_facts(cve_id)
        if cached:
            return cached

    import urllib.request

    try:
        req = urllib.request.Request(
            _NVD_API.format(cve_id=cve_id),
            headers={"User-Agent": "hotspot-workstation/0.8 (local; security research)"},
        )
        with urllib.request.urlopen(req, timeout=_TIMEOUT_S) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        logger.warning(f"cve_enrich: NVD fetch failed {cve_id}: {e}")
        return None

    vulns = data.get("vulnerabilities") or []
    if not vulns:
        return None
    cve = vulns[0].get("cve") or {}

    desc_en = ""
    for d in cve.get("descriptions") or []:
        if d.get("lang") == "en":
            desc_en = str(d.get("value") or "")
            break

    # CVSS 3.1 优先, 退 2.0
    score, vector, severity = None, "", ""
    for key in ("cvssMetricV31", "cvssMetricV30", "cvssMetricV2"):
        metrics = cve.get("metrics", {}).get(key) or []
        if metrics:
            cvss = metrics[0].get("cvssData") or {}
            score = cvss.get("baseScore")
            vector = str(cvss.get("vectorString") or "")
            severity = str(cvss.get("baseSeverity") or metrics[0].get("baseSeverity") or "")
            break

    # CPE → 受影响厂商/产品摘要 (去重, 前 12 条)
    vendors: list[str] = []
    for conf in cve.get("configurations") or []:
        for node in conf.get("nodes") or []:
            for cpe in node.get("cpeMatch") or []:
                criteria = str(cpe.get("criteria") or "")
                parts = criteria.split(":")
                if len(parts) >= 5:
                    entry = f"{parts[3]} {parts[4]}"
                    if entry not in vendors:
                        vendors.append(entry)

    refs = [
        str(r.get("url") or "")
        for r in cve.get("references") or []
        if r.get("url")
    ][:8]

    facts: dict[str, Any] = {
        "cve_id": cve_id,
        "description_en": desc_en,
        "cvss_score": score,
        "cvss_vector": vector,
        "severity": severity,
        "published": str(cve.get("published") or "")[:10],
        "last_modified": str(cve.get("lastModified") or "")[:10],
        "vuln_status": str(cve.get("vulnStatus") or ""),
        "affected_vendors": vendors[:12],
        "references": refs,
        "nvd_url": f"https://nvd.nist.gov/vuln/detail/{cve_id}",
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }
    _cache_facts(cve_id, facts)
    return facts


def compose_cve_brief(facts: dict[str, Any]) -> str:
    """事实 → 中文结构化原文 (深读 LLM 输入; 骨架对齐奇安信 TI 漏洞通告)。

    英文描述原样保留 (LLM 具备跨语能力, 不做机翻避免二次失真),
    骨架标签全部中文化 — 模型按模板输出中文结构化总结。
    """
    lines = [
        f"# 漏洞情报简报 {facts.get('cve_id', '')}",
        "",
        "## 漏洞描述 (NVD 原文)",
        facts.get("description_en") or "(NVD 无描述)",
        "",
        "## 威胁评估",
        f"- CVSS: {facts.get('cvss_score') or '未评级'} ({facts.get('severity') or 'N/A'})",
        f"- CVSS 向量: {facts.get('cvss_vector') or 'N/A'}",
        f"- NVD 状态: {facts.get('vuln_status') or 'N/A'}",
        f"- 公开时间: {facts.get('published') or 'N/A'} / 最后更新: {facts.get('last_modified') or 'N/A'}",
        "",
        "## 受影响厂商与产品 (CPE 摘要)",
    ]
    vendors = facts.get("affected_vendors") or []
    lines += [f"- {v}" for v in vendors] if vendors else ["- (NVD 未收录配置信息)"]
    lines += [
        "",
        "## 参考链接",
    ]
    refs = facts.get("references") or []
    lines += [f"- {u}" for u in refs] if refs else ["- (无)"]
    lines += [
        "",
        f"NVD 详情页: {facts.get('nvd_url', '')}",
        "",
        "以上为 NVD 回源的结构化事实。请基于这些事实 (不要外推事实之外的内容) "
        "按分节模板输出中文结构化漏洞总结。",
    ]
    return "\n".join(lines)


__all__ = [
    "compose_cve_brief",
    "extract_cve_id",
    "fetch_cve_facts",
    "get_cached_facts",
    "is_cve_shell",
]
