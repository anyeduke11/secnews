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

import json
import re
import shutil
import subprocess

from backend.exceptions import InternalException
from backend.logging_config import logger
from backend.repository.codegarden_orchestration_repo import (
    CodegardenDependencyRepository,
)
from backend.repository.codegarden_service_repo import CodegardenServiceRepository
from backend.repository.db import get_connection

# lsof -i :PORT 输出中, 第 2 列是 PID, 第 9 列是 name (如 *:3000)
_LSOF_PORT_RE = re.compile(r":(\d{2,5})\b")

# P0: 系统/GUI 进程黑名单 (规范化小写, 子串匹配以兼容 macOS comm 名截断,
# 如 "Code Helper" → "code ...")。lsof 会把整台 Mac 的监听进程全部扫出,
# 这些 GUI/系统进程并非用户自建服务, 跳过不入库, 避免 cg_services 被
# 噪音淹没 (历史 1300 条几乎全是 Electron/sandbox-c/UURemote/Trae 等)。
# 如需放行/新增, 直接增删此集合即可。
#
# P0-2 (2026-08-15): 依据实库 cg_services 噪音画像扩表 — 新增 IDE/AI Agent/
# 聊天工具/编辑器/系统守护类进程 (Lingma/QwenWorkC/Tutti/OpenCode/CodeBuddy/
# AutoClaw/WeChat/Logseq/Cursor/Video/kilo/com.docke/O+Connect/NarraCat 等)。
# 原则: 只收录「监听端口的用户自建服务」; IDE/AI 助手/聊天/编辑器/媒体类
# 应用一律视为噪音 (即便含端口监听, 也不属于服务网格管理对象)。
_SYSTEM_PROCESS_BLACKLIST = frozenset({
    # --- 既有: 系统/GUI 守护 ---
    "electron",      # Electron 壳 (Electron Helper 等)
    "rapportd",      # macOS 附近共享 / Handoff 守护进程
    "controlcenter", # macOS 控制中心
    "sandbox",       # 沙盒容器进程 (sandbox-c / sandboxd)
    "trae",          # Trae IDE
    "uuremote",      # UURemote (远程协助类工具, 历史噪音之一)
    "wps",           # WPS Office
    "chrome",        # Google Chrome / Chrome Helper
    "code",          # VS Code / Code Helper (注意: 也会命中 code-server)
    "safari",        # Safari 浏览器
    "finder",        # Finder 文件管理
    "sharingd",      # AirDrop / Handoff 守护
    "cloudd",        # iCloud 同步守护
    "nsurlsessiond", # macOS URL 会话守护
    "usernoted",     # 通知中心
    "homed",         # HomeKit
    "symptomsd",     # 系统诊断
    "corespotlight", # 聚焦索引
    "mediaremoted",  # 媒体远程控制
    # --- P0-2 新增: IDE / AI Agent / 聊天 / 编辑器 / 媒体 / 杂项应用 ---
    "lingma",        # 通义灵码 IDE 插件
    "qwenworkc",     # Qwen Code (通义千问编程助手)
    "tutti",         # Tutti (桌面应用套件)
    "opencode",      # OpenCode (AI CLI agent, 非服务)
    "codebuddy",     # CodeBuddy AI 编程助手
    "autoclaw",      # AutoClaw (AI agent 工具)
    "video",         # Video 类媒体应用
    "logseq",        # Logseq 笔记
    "cursor",        # Cursor IDE
    "kilo",          # Kilo 相关应用
    "docke",         # com.docker (Docker Desktop 自身, 非容器)
    "o+connect",     # O+Connect
    "narracat",      # NarraCat (录屏/演示类工具)
    "wechat",        # 微信
    "qq",            # QQ
    "dingtalk",      # 钉钉
    "feishu",        # 飞书
    "lark",          # Lark (飞书国际版)
    "obsidian",      # Obsidian 笔记 (监听 sync 端口, 非服务)
    "notion",        # Notion
    "onedrive",      # OneDrive 同步
    "dropbox",       # Dropbox 同步
    "tim",           # TIM
    "youdao",        # 有道词典
    "baidunetdisk",  # 百度网盘
    "cloudmusic",    # 网易云音乐
    "neteasemusic",  # 网易云音乐 (备选名)
    "spotify",       # Spotify
    "iina",          # IINA 播放器
    "vlc",           # VLC 播放器
    "sohu",          # 搜狐视频
    "youku",         # 优酷
    "qqmusic",       # QQ 音乐
    "kugou",         # 酷狗
    # --- P0-2 第二轮: 依据剩余噪音画像 (AI 客户端/编辑器/同步盘/代理/杂项) ---
    "ardot",         # Ardot
    "catpaw",        # CatPaw (AI 助手)
    "chatgpt",       # ChatGPT 桌面端
    "cherry",        # Cherry Studio (AI 客户端)
    "chromium",      # Chromium 浏览器
    "coze",          # 扣子 Coze 桌面端
    "doubao",        # 豆包桌面端
    "extension",     # 通用 extension 进程
    "google",        # Google 系应用
    "lxmachelp",     # LxMacHelp
    "marvis",        # Marvis (AI 助手族)
    "minimax",       # MiniMax 桌面端
    "nutstore",      # 坚果云同步盘
    "qclaw",         # QClaw (AI agent 工具)
    "qoder",         # Qoder IDE
    "quark",         # 夸克浏览器
    "upedit",        # UPEdit 编辑器
    "windclaw",      # WindClaw (AI agent 工具)
    "workbuddy",     # WorkBuddy
    "opensquil",     # OpenSquil
    "openworke",     # OpenWorks
    "vmark",         # VMark
    "cc-switch",     # CC Switch (Claude Code 切换工具)
    "clash",         # Clash 代理客户端 (clash-ver 等)
    "verge",         # Clash Verge / mihomo
    "mihomo",        # mihomo 代理内核
    "netdisk",       # 网盘类 (netdisk_s)
    "font-help",     # 字体助手
    "buzz",          # Buzz (buzz-desk)
    "editor_sd",     # editor daemon
})

# P0-2: 系统二进制精确匹配集合 — 这类进程名 (awk/tail/bsk 等) 是系统工具
# 而非服务, 但用子串匹配会误伤合法进程 (如 "tail" 会命中 "tailscale"),
# 因此只做精确匹配。
_SYSTEM_BINARY_EXACT = frozenset({
    "awk",
    "tail",
    "bsk",
    "sh",
    "bash",
    "zsh",
    "fish",
    "sleep",
    "cat",
    "grep",
    "sed",
    "top",
    "ps",
})

# P0-2: 泛运行时进程名 — lsof 扫描到的裸运行时进程 (node/python/java 等)
# 在「未关联任何 cg_project」时无法判断是否为用户服务, 一律视为噪音不入库;
# 用户真实的 node/python 服务应通过「项目 → 服务」手动登记或挂到项目下。
# (docker/pm2 扫描结果不受此限制 — 它们有明确的容器/进程管理语义。)
_GENERIC_RUNTIME_BLACKLIST = frozenset({
    "node",       # node 裸进程 (无项目上下文)
    "nodejs",     # nodejs 别名
    "python",     # python / python3 / python3.1 等
    "java",       # java 裸进程
    "ruby",
    "go",
    "rust",
    "deno",
    "bun",
    "php",
    "perl",
    "dotnet",
    "sh",
    "bash",
    "zsh",
    "fish",
})

# UTF-8 mojibake 标记字符 (lsof 进程名编码损坏时的典型产物)
_MOJIBAKE_CHARS = frozenset("ï¿½ÃÂ")


def _is_blacklisted_process(name: str) -> bool:
    """判断进程名是否命中系统进程黑名单 (大小写不敏感).

    双向子串匹配:
    - 黑名单 token 是进程名子串 (如 "Code Helper" 含 "code")
    - 进程名是黑名单 token 的子串 — 兼容 macOS comm 名截断
      (lsof COMMAND 列常见 8/16 字符截断, 如 "ControlCenter" → "ControlC")
    """
    normalized = name.lower()
    if not normalized:
        return True  # 空进程名直接跳过
    return any(token in normalized or normalized in token for token in _SYSTEM_PROCESS_BLACKLIST)


def _is_generic_runtime(name: str) -> bool:
    """判断进程名是否命中泛运行时黑名单 (裸 node/python 等, 无项目上下文).

    匹配规则 (避免误伤 "share"/"shadow" 之类以 sh 开头的合法进程名):
    - 精确匹配: python / node / bash ...
    - 版本后缀: python3 / python3.1 / nodejs18 / java17 ...
      (token 后紧跟数字或 . - _ 视为版本后缀)
    """
    normalized = name.lower().strip()
    if not normalized:
        return False
    for token in _GENERIC_RUNTIME_BLACKLIST:
        if normalized == token:
            return True
        if normalized.startswith(token) and len(normalized) > len(token):
            rest = normalized[len(token):]
            if rest[0].isdigit() or rest[0] in ".-_":
                return True
    return False


def _is_system_binary(name: str) -> bool:
    """判断进程名是否命中系统二进制精确匹配集合 (awk/tail 等)."""
    return (name or "").lower().strip() in _SYSTEM_BINARY_EXACT


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

    def get_service(self, service_id: str) -> dict | None:
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

        P0-2: 扫描前先清理历史噪音 (黑名单/泛运行时/乱码/重复行),
        避免 cg_services 被历史残留噪音淹没 (曾达 1347 条几乎全为噪音).

        Returns: {"scanned": N, "created": N, "updated": N}
        """
        cleaned = self.cleanup_noise_services()
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
            f"scan_local_services: cleaned={cleaned['deleted']} "
            f"lsof={len(lsof_svcs)} docker={len(docker_svcs)} "
            f"pm2={len(pm2_svcs)} → created={created} updated={updated}"
        )
        return {
            "scanned": len(all_svcs),
            "created": created,
            "updated": updated,
            "cleaned": cleaned["deleted"],
        }

    def cleanup_noise_services(self) -> dict:
        """清理 cg_services 中的历史噪音行 (幂等, 可重复调用).

        删除条件 (全部限定 runtime='bare' 且 project_id IS NULL, 绝不触碰
        用户手动登记或挂到项目下的服务):
        1. 进程名命中系统/GUI 黑名单 (_SYSTEM_PROCESS_BLACKLIST)
        2. 进程名命中泛运行时黑名单 (_GENERIC_RUNTIME_BLACKLIST, node/python 等)
        3. 进程名含乱码/不可打印字符
        4. 空进程名
        5. 重复行: 同 (name, endpoint_port) 仅保留最早一条 (无 project_id 时)

        Returns: {"deleted": N, "duplicates_removed": M}
        """
        conn = get_connection()
        deleted = 0
        duplicates_removed = 0

        # 1-4: 按黑名单/乱码/空名删除 (仅限自动发现的 bare 行)
        try:
            cur = conn.execute(
                """
                DELETE FROM cg_services
                WHERE runtime = 'bare'
                  AND project_id IS NULL
                  AND (
                        trim(name) = ''
                     OR name NOT GLOB '*[A-Za-z]*'
                  )
                """
            )
            deleted += cur.rowcount
        except Exception as e:
            logger.warning(f"cleanup_noise_services (empty/non-alpha) failed: {e}")

        # 黑名单/泛运行时/乱码 — 逐行判定 (逻辑在 Python 侧, 便于复用判定函数)
        try:
            rows = conn.execute(
                "SELECT id, name FROM cg_services WHERE runtime = 'bare' AND project_id IS NULL"
            ).fetchall()
            ids_to_delete = []
            for row in rows:
                name = row["name"] or ""
                if (
                    _is_blacklisted_process(name)
                    or _is_generic_runtime(name)
                    or _is_system_binary(name)
                    or "\ufffd" in name
                    or not name.isprintable()
                    or any(c in _MOJIBAKE_CHARS for c in name)
                ):
                    ids_to_delete.append(row["id"])
            if ids_to_delete:
                cur = conn.executemany(
                    "DELETE FROM cg_services WHERE id = ?",
                    [(i,) for i in ids_to_delete],
                )
                deleted += cur.rowcount
        except Exception as e:
            logger.warning(f"cleanup_noise_services (blacklist) failed: {e}")

        # 5: 重复行清理 — 同 (name, endpoint_port) 保留最早 id
        try:
            dup_rows = conn.execute(
                """
                SELECT MIN(id) AS keep_id, name, endpoint_port, COUNT(*) AS cnt
                FROM cg_services
                WHERE project_id IS NULL
                GROUP BY name, COALESCE(endpoint_port, -1)
                HAVING cnt > 1
                """
            ).fetchall()
            for dup in dup_rows:
                cur = conn.execute(
                    "DELETE FROM cg_services WHERE name = ? "
                    "AND COALESCE(endpoint_port, -1) = ? AND id != ?",
                    (dup["name"], dup["endpoint_port"] if dup["endpoint_port"] is not None else -1, dup["keep_id"]),
                )
                duplicates_removed += cur.rowcount
        except Exception as e:
            logger.warning(f"cleanup_noise_services (duplicates) failed: {e}")

        conn.commit()
        if deleted or duplicates_removed:
            logger.info(
                f"cleanup_noise_services: deleted={deleted} duplicates_removed={duplicates_removed}"
            )
        return {"deleted": deleted, "duplicates_removed": duplicates_removed}

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
            # P0 过滤 1: 跳过系统/GUI 噪音进程 (electron/rapportd/...)
            if _is_blacklisted_process(cmd_name):
                continue
            # P0-2 过滤: 跳过裸运行时进程 (node/python/java — 无项目上下文,
            # 无法判断是否为用户服务; 用户服务应挂到项目下或手动登记)
            if _is_generic_runtime(cmd_name):
                continue
            # P0-2 过滤: 跳过系统二进制精确匹配 (awk/tail 等)
            if _is_system_binary(cmd_name):
                continue
            # P0 过滤 2: 跳过含乱码/编码损坏的进程名 — lsof 输出经
            # errors='replace' 解码后损坏字节变成 U+FFFD; 经典 UTF-8
            # mojibake 标记字符 (ï/¿/½/Ã/Â) 与不可打印控制字符同样跳过
            if (
                "\ufffd" in cmd_name
                or not cmd_name.isprintable()
                or any(c in _MOJIBAKE_CHARS for c in cmd_name)
            ):
                continue
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
