"""T5 trigger — kl:publish → kl:refine (user-initiated rollback).

Flow:
1. Receive item_id parameter
2. Backup current .md file to knowledge/backups/{id}_{timestamp}.md
3. Mark stale_at = now
4. Update lifecycle = 'kl:refine'
"""
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path

from backend.repository.db import get_connection
from backend.services.kl_state_machine import (
    LIFECYCLE_PUBLISH,
    LIFECYCLE_REFINE,
    can_transition,
)
from backend.services.knowledge_sync import ITEMS_DIR, KNOWLEDGE_DIR

logger = logging.getLogger("hotspot.trigger.t5")


class T5Trigger:
    """T5: kl:publish → kl:refine (user-initiated rollback).

    Flow:
    1. Receive item_id parameter
    2. Backup current .md file to knowledge/backups/{id}_{timestamp}.md
    3. Mark stale_at = now
    4. Update lifecycle = 'kl:refine'
    """

    def rollback(self, item_id: str) -> dict:
        """Execute the publish→refine rollback for the given item.

        Args:
            item_id: Knowledge item ID to rollback.

        Returns:
            Dict with item_id, backup_path, and new_lifecycle.

        Raises:
            ValueError: If item doesn't exist or is not in kl:publish state.
        """
        # Validate current state before any mutation
        current_lifecycle = self._get_item_lifecycle(item_id)
        if current_lifecycle is None:
            raise ValueError(f"Item {item_id} does not exist")
        if current_lifecycle != LIFECYCLE_PUBLISH:
            raise ValueError(
                f"Item {item_id} is in '{current_lifecycle}' state, "
                f"expected '{LIFECYCLE_PUBLISH}'"
            )

        # Rollback steps
        backup_path = self._backup_md(item_id)
        self._mark_stale(item_id)
        self._update_lifecycle(item_id, LIFECYCLE_REFINE)

        return {
            "item_id": item_id,
            "backup_path": str(backup_path),
            "new_lifecycle": LIFECYCLE_REFINE,
        }

    def _backup_md(self, item_id: str) -> Path:
        """Backup the .md file to knowledge/backups/.

        If the .md file doesn't exist, logs a warning and returns the
        backup path anyway (rollback proceeds without file backup).

        Args:
            item_id: Knowledge item ID.

        Returns:
            Path to the backup file (may not exist if source was missing).
        """
        source = ITEMS_DIR / f"{item_id}.md"
        backup_dir = KNOWLEDGE_DIR / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now(timezone.utc).isoformat().replace(":", "-")
        backup_path = backup_dir / f"{item_id}_{timestamp}.md"

        if not source.exists():
            logger.warning(
                "MD file not found for item %s at %s, proceeding with rollback",
                item_id, source,
            )
            return backup_path

        try:
            shutil.copy2(source, backup_path)
            logger.info("Backed up %s → %s", source, backup_path)
        except OSError as exc:
            logger.warning(
                "Backup failed for item %s: %s, proceeding with rollback",
                item_id, exc,
            )

        return backup_path

    def _mark_stale(self, item_id: str) -> None:
        """Set stale_at to now for the given item."""
        conn = get_connection()
        now_iso = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "UPDATE knowledge_items SET stale_at = ? WHERE id = ?",
            (now_iso, item_id),
        )

    def _update_lifecycle(self, item_id: str, stage: str) -> None:
        """Update lifecycle and validate the transition via state machine.

        Args:
            item_id: Knowledge item ID.
            stage: Target lifecycle stage.

        Raises:
            ValueError: If the transition is not allowed by the state machine.
        """
        current = self._get_item_lifecycle(item_id)
        if current is None:
            raise ValueError(f"Item {item_id} does not exist")
        if not can_transition(current, stage):
            raise ValueError(
                f"Cannot transition item {item_id} from '{current}' to '{stage}'"
            )
        conn = get_connection()
        now_iso = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "UPDATE knowledge_items SET lifecycle = ?, updated_at = ? WHERE id = ?",
            (stage, now_iso, item_id),
        )

    @staticmethod
    def _get_item_lifecycle(item_id: str) -> str | None:
        """Return the current lifecycle for the item, or None if not found."""
        conn = get_connection()
        row = conn.execute(
            "SELECT lifecycle FROM knowledge_items WHERE id = ?",
            (item_id,),
        ).fetchone()
        if row is None:
            return None
        return row["lifecycle"]