"""Phase 2b CodeGarden 服务网格业务层.

职责
----
- 服务 CRUD (委托 repo)
- scan_local_services: 调 lsof / docker ps / pm2 list 扫描本机服务, upsert 到 cg_services
- restart_service: 创建 knowledge_tasks (task_type=service_restart)
- get_logs: 调 docker logs / tail -n N 获取日志
- get_metrics: 调 psutil 获取 CPU/内存
- get_topology: 组装 nodes + edges 给前端 React Flow 渲染
"""
from __future__ import annotations

import asyncio
import json
import re
import shutil
import subprocess
from typing import Optional

from backend.exceptions import InternalException
from backend.logging_config import logger
from backend.repository.codegarden_orchestration_repo import (
    CodegardenDependencyRepository,
)
from backend.repository.codegarden_service_repo import CodegardenServiceRepository
from backend.repository.db import get_connection


# lsof -i :PORT 输出中, 第 2 列是 PID, 第 9 列是 name (如 *:3000)
_LSOF_PORT_RE = re.compile(r":(\d{2,5})\b")


class CodegardenServiceService:
    """服务网格业务逻辑层."""

    def __init__(self) -> None:
        self.repo = CodegardenServiceRepository()
        self.dep_repo = CodegardenDependencyRepository()

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------
    def create_service(self, **kwargs) -> dict:
        return self.repo.create(**kwargs)

    def get_service(self, service_id: str) -> Optional[dict]:
        return self.repo.get(service_id)

    def list_services(self, **filters) -> tuple[list[dict], int]:
        return self.repo.list(**filters)

    def update_service(self, service_id: str, **fields) -> dict:
        return self.repo.update(service_id, **fields)

    def delete_service(self, service_id: str) -> bool:
        return self.repo.delete(service_id)

    def set_status(self, service_id: str, status: str) -> dict:
        return self.repo.set_status(service_id, status)

    # ------------------------------------------------------------------
    # 自动发现 — scan_local_services
    # ------------------------------------------------------------------
    def scan_local_services(self) -> dict:
        """扫描本机服务: lsof + docker ps + pm2 list, 合并后 upsert.

        Returns: {"scanned": N, "created": N, "updated": N}
        """
        lsof_svcs = self._scan_lsof()
        docker_svcs = self._scan_docker()
        pm2_svcs = self._scan_pm2()

        all_svcs = lsof_svcs + docker_svcs + pm2_svcs
        created = 0
        updated = 0
        for svc in all_svcs:
            try:
                _, is_new = self.repo.upsert_from_scan(**svc)
                if is_new:
                    created += 1
                else:
                    updated += 1
            except Exception as e:
                logger.warning(f"scan upsert failed for {svc.get('name')}: {e}")

        logger.info(
            f"scan_local_services: lsof={len(lsof_svcs)} docker={len(docker_svcs)} "
            f"pm2={len(pm2_svcs)} → created={created} updated={updated}"
        )
        return {
            "scanned": len(all_svcs),
            "created": created,
            "updated": updated,
        }

    def _scan_lsof(self) -> list[dict]:
        """扫描 lsof -i -P -n 输出, 提取监听 TCP 端口的进程.

        Returns: [{name, type, runtime, status, endpoint_host, endpoint_port}]
        """
        if not shutil.which("lsof"):
            return []
        try:
            proc = subprocess.run(
                ["lsof", "-i", "-P", "-n"],
                capture_output=True, timeout=10,
            )
            # 用 errors='replace' 处理非 UTF-8 字节 (进程名可能含特殊字符)
            stdout = proc.stdout.decode("utf-8", errors="replace") if proc.stdout else ""
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            logger.warning(f"_scan_lsof failed: {e}")
            return []

        services: list[dict] = []
        seen: set[tuple[str, int]] = set()
        for line in stdout.splitlines()[1:]:  # 跳过 header
            parts = line.split()
            if len(parts) < 9:
                continue
            # 只看 LISTEN 状态
            if "LISTEN" not in line:
                continue
            cmd_name = parts[0]
            name_col = parts[8]  # 形如 *:3000 或 127.0.0.1:3000
            port_match = _LSOF_PORT_RE.search(name_col)
            if not port_match:
                continue
            port = int(port_match.group(1))
            host = "127.0.0.1" if name_col.startswith("*") else name_col.split(":")[0]

            key = (cmd_name, port)
            if key in seen:
                continue
            seen.add(key)

            services.append({
                "name": cmd_name,
                "type": "http",  # 默认 http, 无法精确判断
                "runtime": "bare",
                "status": "running",
                "endpoint_host": host,
                "endpoint_port": port,
            })
        return services

    def _scan_docker(self) -> list[dict]:
        """扫描 docker ps 输出, 提取运行中容器.

        Returns: [{name, type, runtime, status, endpoint_port, namespace}]
        """
        if not shutil.which("docker"):
            return []
        try:
            proc = subprocess.run(
                ["docker", "ps", "--format", "{{.Names}}\t{{.Ports}}\t{{.Status}}"],
                capture_output=True, text=True, timeout=10,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            logger.warning(f"_scan_docker failed: {e}")
            return []

        services: list[dict] = []
        for line in proc.stdout.splitlines():
            parts = line.split("\t")
            if len(parts) < 3:
                continue
            name, ports_str, status_str = parts[0], parts[1], parts[2]
            # ports_str 形如 "0.0.0.0:3000->3000/tcp, 0.0.0.0:5432->5432/tcp"
            port_matches = re.findall(r":(\d{2,5})->(\d{2,5})/tcp", ports_str)
            status = "running" if "Up" in status_str else "stopped"
            if not port_matches:
                # 容器无端口映射也记录
                services.append({
                    "name": name,
                    "type": "http",
                    "runtime": "docker",
                    "status": status,
                    "namespace": "docker",
                })
                continue
            for host_port, _container_port in port_matches:
                services.append({
                    "name": name,
                    "type": "http",
                    "runtime": "docker",
                    "status": status,
                    "endpoint_port": int(host_port),
                    "endpoint_host": "0.0.0.0",
                    "namespace": "docker",
                })
        return services

    def _scan_pm2(self) -> list[dict]:
        """扫描 pm2 list 输出 (JSON 格式).

        Returns: [{name, type, runtime, status}]
        """
        if not shutil.which("pm2"):
            return []
        try:
            proc = subprocess.run(
                ["pm2", "jlist"],
                capture_output=True, text=True, timeout=10,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            logger.warning(f"_scan_pm2 failed: {e}")
            return []

        try:
            procs = json.loads(proc.stdout)
        except json.JSONDecodeError as e:
            logger.warning(f"_scan_pm2 json parse failed: {e}")
            return []

        services: list[dict] = []
        for p in procs:
            name = p.get("name")
            if not name:
                continue
            pm2_env = p.get("pm2_env", {}) or {}
            status = "running" if pm2_env.get("status") == "online" else "stopped"
            services.append({
                "name": name,
                "type": "http",
                "runtime": "pm2",
                "status": status,
                "namespace": "pm2",
            })
        return services

    # ------------------------------------------------------------------
    # restart — 创建 knowledge_tasks
    # ------------------------------------------------------------------
    def restart_service(self, service_id: str) -> dict:
        """创建服务重启任务 (task_type=service_restart)."""
        from datetime import datetime, timezone

        svc = self.repo.get(service_id)
        if svc is None:
            raise InternalException(f"service {service_id} 不存在")

        now = datetime.now(timezone.utc).isoformat()
        conn = get_connection()
        try:
            conn.execute("BEGIN")
            cur = conn.execute(
                """
                INSERT INTO knowledge_tasks (task_type, status, params, created_at, updated_at)
                VALUES (?, 'pending', ?, ?, ?)
                """,
                (
                    "service_restart",
                    json.dumps({"service_id": service_id, "action": "restart"}),
                    now, now,
                ),
            )
            task_id = int(cur.lastrowid)
            conn.execute("COMMIT")
        except Exception as e:
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass
            raise InternalException(f"create restart task failed: {e}") from e

        logger.info(f"created service_restart task {task_id} for service {service_id}")
        return {"task_id": task_id, "service_id": service_id, "status": "pending"}

    # ------------------------------------------------------------------
    # get_logs — 调 docker logs / tail
    # ------------------------------------------------------------------
    def get_logs(self, service_id: str, tail: int = 100) -> dict:
        """获取服务日志. 优先 docker logs, 其次 tail -n N local_path."""
        svc = self.repo.get(service_id)
        if svc is None:
            raise InternalException(f"service {service_id} 不存在")

        runtime = svc.get("runtime")
        name = svc.get("name")
        lines: list[str] = []

        if runtime == "docker" and shutil.which("docker"):
            try:
                proc = subprocess.run(
                    ["docker", "logs", "--tail", str(tail), name],
                    capture_output=True, text=True, timeout=15,
                )
                # docker logs 同时有 stdout 和 stderr, 合并
                output = (proc.stdout or "") + (proc.stderr or "")
                lines = output.splitlines()
            except (subprocess.TimeoutExpired, FileNotFoundError) as e:
                logger.warning(f"docker logs {name} failed: {e}")
                return {"lines": [], "error": f"docker logs failed: {e}"}
        else:
            # bare/pm2/system: 暂不支持, 返回空
            return {"lines": [], "error": f"runtime={runtime} 日志暂不支持 (仅 docker)"}

        return {"lines": lines[-tail:], "source": "docker"}

    # ------------------------------------------------------------------
    # get_metrics — 调 psutil
    # ------------------------------------------------------------------
    def get_metrics(self, service_id: str) -> dict:
        """获取服务指标 (CPU/内存). docker runtime 用 docker stats, 其他返回 unknown."""
        svc = self.repo.get(service_id)
        if svc is None:
            raise InternalException(f"service {service_id} 不存在")

        runtime = svc.get("runtime")
        name = svc.get("name")

        if runtime == "docker" and shutil.which("docker"):
            try:
                proc = subprocess.run(
                    ["docker", "stats", "--no-stream", "--format",
                     "{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}",
                     name],
                    capture_output=True, text=True, timeout=15,
                )
                line = proc.stdout.strip()
                if line:
                    parts = line.split("\t")
                    if len(parts) >= 3:
                        return {
                            "cpu_percent": parts[0].strip().rstrip("%"),
                            "mem_usage": parts[1].strip(),
                            "mem_percent": parts[2].strip().rstrip("%"),
                            "source": "docker_stats",
                        }
            except (subprocess.TimeoutExpired, FileNotFoundError) as e:
                logger.warning(f"docker stats {name} failed: {e}")
                return {"error": f"docker stats failed: {e}"}

        return {"error": f"runtime={runtime} metrics 暂不支持 (仅 docker)"}

    # ------------------------------------------------------------------
    # get_topology — 组装 nodes + edges
    # ------------------------------------------------------------------
    def get_topology(self) -> dict:
        """返回 {nodes: [...], edges: [...]} 供 React Flow 渲染."""
        services, _ = self.repo.list(limit=500)
        deps, _ = self.dep_repo.list(limit=500)

        # 按服务类型分色 (与 spec G6 一致)
        runtime_colors = {
            "docker": "#2496ed",  # docker 蓝
            "pm2": "#61dafb",     # react 青
            "system": "#94a3b8",  # 灰
            "bare": "#6b7280",    # 深灰
        }
        status_colors = {
            "running": "#10b981",  # 绿
            "stopped": "#9ca3af",  # 灰
            "error": "#ef4444",    # 红
            "unknown": "#fbbf24",  # 黄
        }

        nodes = [
            {
                "id": f"svc:{s['id']}",
                "type": "serviceNode",
                "position": {"x": i * 200, "y": 100},  # 简单线性布局, React Flow 会自动 layout
                "data": {
                    "label": s["name"],
                    "service_id": s["id"],
                    "runtime": s["runtime"],
                    "status": s["status"],
                    "endpoint_port": s.get("endpoint_port"),
                    "runtime_color": runtime_colors.get(s["runtime"], "#6b7280"),
                    "status_color": status_colors.get(s["status"], "#fbbf24"),
                },
            }
            for i, s in enumerate(services)
        ]

        edges = []
        for d in deps:
            if d["source_type"] == "service" and d["target_type"] == "service":
                edges.append({
                    "id": f"edge:{d['id']}",
                    "source": f"svc:{d['source_id']}",
                    "target": f"svc:{d['target_id']}",
                    "label": d["dep_type"],
                    "data": {"dep_type": d["dep_type"]},
                })

        return {"nodes": nodes, "edges": edges}


__all__ = ["CodegardenServiceService"]
