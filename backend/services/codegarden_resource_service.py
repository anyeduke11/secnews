"""Phase 2b CodeGarden 资源中枢业务层.

职责
----
- 资源 CRUD (委托 repo)
- allocate_port: 智能分配端口 (避开 cg_resources 已分配 + lsof 实时占用 + 8898 保护)
- release_port: 8898 受保护返回 403 (由 API 层捕获 InternalException 转 HTTP 403)
- encrypt_env_template / decrypt_env_template: 复用 secrets_service Fernet 加密敏感字段
"""
from __future__ import annotations

import re
import subprocess
from typing import Any, Optional

from backend.exceptions import InternalException
from backend.logging_config import logger
from backend.repository.codegarden_resource_repo import (
    PORT_RANGE_END,
    PORT_RANGE_START,
    PROTECTED_PORTS,
    CodegardenResourceRepository,
)


# 环境变量模板中需加密的字段名关键词 (大小写不敏感)
_SENSITIVE_KEY_PATTERNS = re.compile(
    r"(password|secret|token|api_key|apikey|access_key|private_key)",
    re.IGNORECASE,
)


class CodegardenResourceService:
    """资源中枢业务逻辑层."""

    def __init__(self) -> None:
        self.repo = CodegardenResourceRepository()

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------
    def create_resource(self, **kwargs) -> dict:
        return self.repo.create(**kwargs)

    def get_resource(self, resource_id: str) -> Optional[dict]:
        return self.repo.get(resource_id)

    def list_resources(self, **filters) -> tuple[list[dict], int]:
        return self.repo.list(**filters)

    def update_resource(self, resource_id: str, **fields) -> dict:
        return self.repo.update(resource_id, **fields)

    def delete_resource(self, resource_id: str) -> bool:
        return self.repo.delete(resource_id)

    # ------------------------------------------------------------------
    # 端口分配 — 实时占用扫描
    # ------------------------------------------------------------------
    def _get_lsof_occupied_ports(self) -> set[int]:
        """调 lsof 获取当前本机已占用的 TCP 端口集合."""
        import shutil
        if not shutil.which("lsof"):
            return set()
        try:
            proc = subprocess.run(
                ["lsof", "-i", "-P", "-n"],
                capture_output=True, timeout=10,
            )
            stdout = proc.stdout.decode("utf-8", errors="replace") if proc.stdout else ""
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            logger.warning(f"_get_lsof_occupied_ports failed: {e}")
            return set()

        ports: set[int] = set()
        for line in stdout.splitlines()[1:]:
            if "LISTEN" not in line:
                continue
            parts = line.split()
            if len(parts) < 9:
                continue
            # name 列 (第 9 个) 形如 *:3000 或 127.0.0.1:5432
            name_col = parts[8]
            # 提取最后一个 :后的数字
            if ":" in name_col:
                port_str = name_col.rsplit(":", 1)[-1]
                if port_str.isdigit():
                    ports.add(int(port_str))
        return ports

    def allocate_port(
        self,
        *,
        owner_service_id: Optional[str] = None,
        owner_project_id: Optional[str] = None,
        preferred_port: Optional[int] = None,
        metadata: Optional[dict] = None,
    ) -> dict:
        """智能分配端口.

        优先级:
        1. 若 preferred_port 指定且可用, 分配它
        2. 否则查找 cg_resources 表内 + lsof 实时占用 之外的最小可用端口

        Args:
            preferred_port: 期望端口号 (可选)
        Returns: 分配后的 cg_resources 记录
        Raises: InternalException (8898 保护 / 范围外 / 已分配)
        """
        # 实时占用端口
        lsof_ports = self._get_lsof_occupied_ports()

        if preferred_port is not None:
            if preferred_port in PROTECTED_PORTS:
                raise InternalException(
                    f"端口 {preferred_port} 受保护, 禁止分配 (hotspot 自身端口)"
                )
            if not (PORT_RANGE_START <= preferred_port <= PORT_RANGE_END):
                raise InternalException(
                    f"端口 {preferred_port} 超出允许范围 [{PORT_RANGE_START}, {PORT_RANGE_END}]"
                )
            # 检查表内是否已分配
            existing = self.repo.get_by_value("port", str(preferred_port))
            if existing and existing["status"] == "allocated":
                raise InternalException(f"端口 {preferred_port} 已被分配 (cg_resources)")
            if preferred_port in lsof_ports:
                raise InternalException(
                    f"端口 {preferred_port} 当前已被本机进程占用 (lsof)"
                )
            return self.repo.allocate_port(
                preferred_port,
                owner_service_id=owner_service_id,
                owner_project_id=owner_project_id,
                metadata=metadata,
            )

        # 自动查找最小可用端口
        port = self.repo.find_free_port(exclude_ports=lsof_ports)
        if port is None:
            raise InternalException(
                f"无可用端口 (范围 [{PORT_RANGE_START}, {PORT_RANGE_END}] 已满)"
            )
        return self.repo.allocate_port(
            port,
            owner_service_id=owner_service_id,
            owner_project_id=owner_project_id,
            metadata=metadata,
        )

    def release_port(self, port: int) -> dict:
        """释放端口. 8898 受保护 (由 API 层捕获 InternalException 转 403)."""
        if port in PROTECTED_PORTS:
            raise InternalException(
                f"端口 {port} 受保护, 禁止释放 (hotspot 自身端口 8898)"
            )
        return self.repo.release_port(port)

    # ------------------------------------------------------------------
    # 环境变量模板 — 敏感字段加密
    # ------------------------------------------------------------------
    def save_env_template(
        self,
        *,
        name: str,
        env_vars: dict,
        owner_project_id: Optional[str] = None,
    ) -> dict:
        """保存环境变量模板. 敏感字段 (password/secret/token/api_key 等) 用 Fernet 加密.

        Args:
            name: 模板名 (如 "production" / "development")
            env_vars: 环境变量字典 {KEY: VALUE}
            owner_project_id: 归属项目
        Returns: cg_resources 记录 (type=env_template, value=name)
        """
        encrypted_vars = self._encrypt_env_template(env_vars)
        # metadata 存加密后的 env_vars (JSON)
        return self.repo.create(
            type="env_template",
            value=name,
            status="allocated",
            owner_project_id=owner_project_id,
            metadata={"env_vars": encrypted_vars, "encrypted": True},
        )

    def load_env_template(self, resource_id: str) -> dict:
        """加载并解密环境变量模板.

        Returns: {name: str, env_vars: dict, owner_project_id: Optional[str]}
        """
        r = self.repo.get(resource_id)
        if r is None:
            raise InternalException(f"resource {resource_id} 不存在")
        if r["type"] != "env_template":
            raise InternalException(f"resource {resource_id} 不是 env_template 类型")
        meta = r.get("metadata") or {}
        encrypted_vars = meta.get("env_vars", {})
        env_vars = self._decrypt_env_template(encrypted_vars)
        return {
            "name": r["value"],
            "env_vars": env_vars,
            "owner_project_id": r.get("owner_project_id"),
        }

    def _encrypt_env_template(self, env_vars: dict) -> dict:
        """对 env_vars 中敏感 key 的 value 做 Fernet 加密.

        Returns: {"KEY": {"ciphertext": "...", "encrypted": true} | "plain_value"}
        """
        from backend.crypto import encrypt_api_key
        from backend.repository.encryption_keys_repo import EncryptionKeyRepository

        ek_row = EncryptionKeyRepository().get_default()
        if ek_row is None:
            # 无加密密钥, 全部以明文保存 (开发模式)
            logger.warning("save_env_template: 无 encryption_key, 明文保存")
            return {k: v for k, v in env_vars.items()}

        result: dict[str, Any] = {}
        for k, v in env_vars.items():
            if _SENSITIVE_KEY_PATTERNS.search(k):
                try:
                    cipher = encrypt_api_key(str(v), ek_row.id)
                    result[k] = {"ciphertext": cipher, "encrypted": True}
                except Exception as e:
                    logger.warning(f"encrypt env var {k} failed: {e}, 明文保存")
                    result[k] = v
            else:
                result[k] = v
        return result

    def _decrypt_env_template(self, encrypted_vars: dict) -> dict:
        """解密 env_template 中的敏感字段."""
        from backend.crypto import decrypt_api_key
        from backend.repository.encryption_keys_repo import EncryptionKeyRepository
        from backend.services.secrets_service import _is_unlocked, _unlock_state

        ek_row = EncryptionKeyRepository().get_default()
        if ek_row is None:
            return encrypted_vars  # 无加密

        fernet_key = None
        if _is_unlocked(ek_row.id):
            fernet_key = _unlock_state[ek_row.id]["fernet_key"]
        if fernet_key is None:
            # 未解锁, 返回脱敏值
            result: dict[str, Any] = {}
            for k, v in encrypted_vars.items():
                if isinstance(v, dict) and v.get("encrypted"):
                    result[k] = "******"  # 脱敏
                else:
                    result[k] = v
            return result

        result = {}
        for k, v in encrypted_vars.items():
            if isinstance(v, dict) and v.get("encrypted"):
                try:
                    plain = decrypt_api_key(v["ciphertext"], fernet_key)
                    result[k] = plain
                except Exception as e:
                    logger.warning(f"decrypt env var {k} failed: {e}")
                    result[k] = "******"
            else:
                result[k] = v
        return result

    # ------------------------------------------------------------------
    # 域名映射 / 卷
    # ------------------------------------------------------------------
    def list_domains(self) -> list[dict]:
        return self.repo.list(type="domain")[0]

    def create_domain(
        self,
        *,
        domain: str,
        target: str,
        owner_service_id: Optional[str] = None,
        owner_project_id: Optional[str] = None,
    ) -> dict:
        """创建域名映射记录. metadata.target 存后端地址 (如 localhost:3000)."""
        return self.repo.create(
            type="domain", value=domain, status="allocated",
            owner_service_id=owner_service_id, owner_project_id=owner_project_id,
            metadata={"target": target},
        )

    def list_volumes(self) -> list[dict]:
        """列出存储卷 (cg_resources.type=volume)."""
        return self.repo.list(type="volume")[0]

    def list_env_templates(self) -> list[dict]:
        """列出环境变量模板 (cg_resources.type=env_template)."""
        return self.repo.list(type="env_template")[0]


__all__ = ["CodegardenResourceService"]
