"""MITRE ATT&CK STIX data fetching + parsing for security knowledge graph.

Design
------
- Fetches the MITRE ATT&CK enterprise-attack STIX bundle from GitHub raw.
- Parses attack-patterns → techniques, tactics, and relationships.
- Upserts into security_entities + security_edges via SecurityRepository.

Phase 2: minimal viable sync (tactics + techniques + uses/subtechnique-of edges).
"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

from backend.domain.security_models import SecurityEntity, SecurityEdge, _now_iso
from backend.repository.security_repo import SecurityRepository
from backend.logging_config import logger

MITRE_RAW_BASE = (
    "https://raw.githubusercontent.com/mitre/cti/master/enterprise-attack"
)
DEFAULT_BUNDLE_URL = (
    f"{MITRE_RAW_BASE}/enterprise-attack.json"
)


class MitreAttackClient:
    """Fetch + sync MITRE ATT&CK STIX data into local security_* tables."""

    def __init__(self, repo: Optional[SecurityRepository] = None):
        self._repo = repo or SecurityRepository()
        self._log = logging.getLogger("hotspot.security.mitre_attack")

    def sync_to_db(self, clear: bool = False) -> int:
        """Sync MITRE ATT&CK STIX bundle to security_entities + security_edges.

        Args:
            clear: if True, delete all existing ATT&CK rows before syncing.

        Returns:
            Number of entities upserted.
        """
        try:
            import urllib.request
        except ImportError:
            self._log.error("urllib not available, cannot fetch MITRE STIX")
            return 0

        self._log.info("fetching MITRE ATT&CK STIX bundle", extra={"url": DEFAULT_BUNDLE_URL})
        try:
            with urllib.request.urlopen(DEFAULT_BUNDLE_URL, timeout=60) as resp:
                raw = resp.read().decode("utf-8")
        except Exception as e:
            self._log.error(f"failed to fetch MITRE STIX bundle: {e}")
            return 0

        try:
            bundle = json.loads(raw)
        except json.JSONDecodeError as e:
            self._log.error(f"failed to parse MITRE STIX bundle: {e}")
            return 0

        objects = bundle.get("objects", [])
        self._log.info(f"loaded {len(objects)} STIX objects")

        if clear:
            self._log.info("clearing existing ATT&CK entities/edges")
            from backend.repository.db import get_connection
            conn = get_connection()
            conn.execute("DELETE FROM security_edges WHERE source_id IN (SELECT id FROM security_entities WHERE entity_type IN ('tactic','technique','cwe','product','cpe'))")
            conn.execute("DELETE FROM security_entities WHERE entity_type IN ('tactic','technique','cwe','product','cpe')")

        count = 0
        for obj in objects:
            stix_type = obj.get("type", "")
            if stix_type == "attack-pattern":
                entity = self._parse_technique(obj)
                if entity:
                    self._repo.upsert_entity(entity)
                    count += 1
            elif stix_type == "tactic":
                entity = self._parse_tactic(obj)
                if entity:
                    self._repo.upsert_entity(entity)
                    count += 1
            elif stix_type == "relationship":
                edge = self._parse_relationship(obj)
                if edge:
                    self._repo.upsert_edge(edge)

        self._log.info(f"MITRE sync completed", extra={"entities": count})
        return count

    def _parse_technique(self, obj: dict) -> Optional[SecurityEntity]:
        """Parse a STIX attack-pattern into SecurityEntity."""
        ext_refs = obj.get("external_references", [])
        external_ref = ""
        for ref in ext_refs:
            if ref.get("source_name") == "mitre-attack":
                external_ref = ref.get("url", "")
                break

        return SecurityEntity(
            id=obj.get("id", ""),
            entity_type="technique",
            name=obj.get("name", ""),
            description=obj.get("description", "")[:500] if obj.get("description") else None,
            external_ref=external_ref,
            metadata={
                "stix_type": "attack-pattern",
                "kill_chain_phases": [
                    kp.get("phase_name") for kp in obj.get("kill_chain_phases", [])
                ],
            },
            created_at=_now_iso(),
            updated_at=_now_iso(),
        )

    def _parse_tactic(self, obj: dict) -> Optional[SecurityEntity]:
        """Parse a STIX tactic into SecurityEntity."""
        ext_refs = obj.get("external_references", [])
        external_ref = ""
        for ref in ext_refs:
            if ref.get("source_name") == "mitre-attack":
                external_ref = ref.get("url", "")
                break

        return SecurityEntity(
            id=obj.get("id", ""),
            entity_type="tactic",
            name=obj.get("name", ""),
            description=obj.get("description", "")[:500] if obj.get("description") else None,
            external_ref=external_ref,
            metadata={"stix_type": "tactic"},
            created_at=_now_iso(),
            updated_at=_now_iso(),
        )

    def _parse_relationship(self, obj: dict) -> Optional[SecurityEdge]:
        """Parse a STIX relationship into SecurityEdge."""
        rel_type = obj.get("relationship_type", "")
        edge_type_map = {
            "uses": "uses",
            "subtechnique-of": "subtechnique-of",
            "mitigates": "mitigates",
            "related-to": "related-to",
        }
        edge_type = edge_type_map.get(rel_type)
        if not edge_type:
            return None

        return SecurityEdge(
            source_id=obj.get("source_ref", ""),
            target_id=obj.get("target_ref", ""),
            edge_type=edge_type,
            weight=1.0,
            metadata={"stix_id": obj.get("id", "")},
            created_at=_now_iso(),
        )


__all__ = ["MitreAttackClient", "MITRE_RAW_BASE", "DEFAULT_BUNDLE_URL"]
