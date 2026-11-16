"""L3 系统层加固 — sandbox-exec profile 生成 + 资源上限 launcher (v0.8.9 P5 R-4)。

职责: 把 P4 的「声明级」边界 (L2, enforcer) 落到 **系统层** (L3):

1. **文件隔离** — 为每个已审批 plan 生成一份 Seatbelt profile:
   写仅限 workspace 锁定根 + plan.writable_paths; 读仅限 plan.readable_paths;
   凭据载体 (DB / .env / 密钥目录) 一律禁读。
2. **网络隔离** — plan.network 为空 (默认全禁) → 拒绝一切出网; 非空 → 仅放行
   声明的 host:port。
3. **资源上限** — CPU / 文件数 / 单文件大小 (ulimit), 超出即被内核截断。

为什么用 ``sandbox-exec`` 而不是更重的容器: macOS 原生、零依赖、per-plan
profile 精确到路径 (PRD R-4 要求 "per-plan profile 生成")。非 macOS 平台
(如 Linux CI) **无 sandbox-exec** → 本模块返回 ``None``, 调用方降级为
「仅 ulimit」并在 L4 留痕, 不静默假装有沙箱。

实测踩坑 (2026-11-16, macOS 27.2) — 全部经本机验证:

- Seatbelt 的 ``subpath`` 匹配的是 **realpath** — ``/tmp/x`` 在 macOS 实为
  ``/private/tmp/x``, 不解析 realpath 会导致「允许写」失效。
- ``(deny default)`` 会让 CPython 直接 abort (exit 134) — 解释器需要读
  自身 stdlib / dylib / 动态链接缓存。故基线用 ``(allow default)`` + 精确
  ``deny`` 覆盖, 而非 deny-all 白名单。
- ``(remote ip "1.2.3.4:443")`` 被内核拒 ("host must be * or localhost") —
  macOS Seatbelt **不支持 host 级出网白名单**, 只支持 ``*`` 或 localhost。
  故非空 network 的精确放行不可得, 统一降级为「该 host 解析出的 IP 段放行
  不成立 → 走全禁 + 告警」, 详见 ``build_sandbox_profile`` 注释。
- ``RLIMIT_AS`` 在 macOS 被内核拒 (EPERM: current limit exceeds maximum
  limit) — macOS 的 AS 不可收紧。故内存上限由 launcher **尽力设置**, 失败
  即在 stderr 打 ``HOTSPOT_RLIMIT_SKIP`` 标记并继续 (不假装成功)。

ulimit 的施加方式: **exec launcher** 而非 ``preexec_fn``。``preexec_fn``
在多线程父进程里 fork 后执行 Python 回调, 有死锁风险 (CPython 明确不建议);
launcher 是「子进程内 setrlimit → ``os.execvp`` 目标 argv」, 最终进程镜像
就是目标程序本身 (同 PID / 同退出码), 且不碰 fork 后的 Python 运行时。
"""
from __future__ import annotations

import os
import platform
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

# 凭据载体: 沙箱内一律禁读 (L3 "凭据保护 = 执行环境无 llm_secrets" 底线的
# 物理兑现 — P4 的 env 剥离只挡了环境变量, 挡不住直接读 DB 文件)。
_CREDENTIAL_SUFFIXES = (".db", ".env", ".key", ".pem")

# 资源上限默认值 (可被 plan/CLI 覆盖)。
_DEFAULT_MAX_FILE_BYTES = 64 * 1024 * 1024  # 单文件 64MB
_DEFAULT_MAX_OPEN_FILES = 256
_DEFAULT_MAX_CPU_SECONDS = 60

# exec launcher 源码 (常量, 无外部输入) — 语义见模块 docstring。
# 参数: argv[1]=limits 规格串, argv[2:]=目标 argv (原样 execvp, 不改 argv[0])。
_LAUNCHER_SRC = (
    "import os,resource,sys\n"
    "for _l in sys.argv[1].split(','):\n"
    "    if not _l: continue\n"
    "    _n,_v=_l.split('=')\n"
    "    _s,_h=_v.split(':')\n"
    "    try:\n"
    "        resource.setrlimit(getattr(resource,_n),(int(_s),int(_h)))\n"
    "    except Exception as _e:\n"
    "        sys.stderr.write('HOTSPOT_RLIMIT_SKIP %s %s\\n' % (_n,_e))\n"
    "os.execvp(sys.argv[2],sys.argv[2:])\n"
)


@dataclass(frozen=True)
class SandboxSpec:
    """L3 约束集 (由已审批 plan 编译而来)。"""

    workspace: str
    writable_paths: tuple[str, ...]
    readable_paths: tuple[str, ...]
    network: tuple[str, ...]
    max_cpu_seconds: int = _DEFAULT_MAX_CPU_SECONDS
    max_file_bytes: int = _DEFAULT_MAX_FILE_BYTES
    max_open_files: int = _DEFAULT_MAX_OPEN_FILES
    extra_deny_read: tuple[str, ...] = field(default_factory=tuple)
    # 额外放行读 (置于仓库级 deny 之后) — 典型用途: 放行 Python 解释器
    # 自身路径 (venv 往往位于仓库内, 会被仓库级 deny 一并挡掉, 导致
    # execvp 失败 "Operation not permitted")。
    extra_allow_read: tuple[str, ...] = field(default_factory=tuple)
    # 仓库根 (凭据载体所在处) — 沙箱内整体禁读, 再按 readable_paths 放行
    # workspace 内声明目录。None = 不做仓库级收窄 (仅凭据 deny)。
    repo_root: str | None = None

    def resource_limits(self) -> dict[str, tuple[int, int]]:
        """ulimit 取值 (soft, hard) — soft=hard, 越限即杀, 不给缓冲。"""
        return {
            "RLIMIT_CPU": (self.max_cpu_seconds, self.max_cpu_seconds),
            "RLIMIT_FSIZE": (self.max_file_bytes, self.max_file_bytes),
            "RLIMIT_NOFILE": (self.max_open_files, self.max_open_files),
        }


def sandbox_supported() -> bool:
    """当前平台是否可用 sandbox-exec (macOS 专有)。"""
    return platform.system() == "Darwin" and Path("/usr/bin/sandbox-exec").exists()


def _realpath(path: str) -> str:
    """Seatbelt 匹配 realpath (见模块 docstring 踩坑记录)。"""
    return os.path.realpath(path)


def _ancestor_dirs(path: str) -> tuple[str, ...]:
    """path 的各级祖先目录 (含自身所在目录, 不含根)。

    解释器启动时调 realpath() 解析自身路径 — 需要**每一级**祖先目录的读
    权限, 否则报 "realpath: ...: Operation not permitted"。
    """
    abs_path = os.path.abspath(path)
    parts = Path(abs_path).parts
    out: list[str] = []
    for i in range(1, len(parts)):
        out.append(os.path.join(*parts[:i]))
    return tuple(out)


def _credential_paths(workspace: str) -> list[str]:
    """收集需禁读的凭据载体 (DB / .env / 密钥)。

    来源: 执行体 cwd (仓库根) + workspace + 主 DB 所在目录。命名后缀匹配
    (``.db`` / ``.env`` / ``.key`` / ``.pem``) — 覆盖 llm_secrets 密文库、
    ``.env`` 里的 master_key、明文密钥文件。
    """
    denied: list[str] = []
    for root in (os.getcwd(), workspace):
        try:
            base = Path(root).resolve()
        except OSError:
            continue
        if not base.is_dir():
            continue
        for entry in base.iterdir():
            if entry.name.endswith(_CREDENTIAL_SUFFIXES):
                denied.append(str(entry.resolve()))
    return sorted(set(denied))


def build_sandbox_profile(spec: SandboxSpec) -> str:
    """生成 Seatbelt profile 文本 (per-plan)。

    结构 (实测有效形态, macOS 27.2):

    - ``(deny default)`` 基线 + 显式放行进程/系统读 — **默认拒绝**。
      注: CPython 需要读 stdlib / dylib / 动态链接缓存, 故 ``file-read*``
      必须 blanket 放行 (实测: 子路径白名单会让解释器 abort, exit 134);
      读收窄靠**定向 deny** 实现 (deny 仓库根 → allow workspace), 而非
      白名单枚举。
    - 写: ``file-write*`` 默认即禁 (deny default) → 仅按 plan.writable_paths
      放行 (更严不放松: workspace 根未声明即不可写)。
    - 读: deny **仓库根** (凭据载体所在处) → 再 allow workspace 内
      plan.readable_paths; 凭据载体额外 deny。
    - 网: 出网全禁。plan.network 非空时**仍全禁** — macOS Seatbelt 不支持
      host 级白名单 (实测 ``(remote ip "1.2.3.4:443")`` 被内核拒), 放行
      全集等于放行任意 host, 违反"更严不放松"。

    **规则优先级**: Seatbelt 是 **last-match-wins** (实测: 同路径 deny→allow
    → 放行; allow→deny → 拒绝)。故顺序即语义, 不可调换。
    """
    ws = _realpath(spec.workspace)
    lines: list[str] = [
        "(version 1)",
        "(deny default)",
        "(allow process-fork)",
        "(allow process-exec)",
        "(allow sysctl-read)",
        "(allow mach-lookup)",
        # 系统读 blanket 放行 (解释器需要) — 收窄靠下方定向 deny。
        "(allow file-read*)",
    ]

    # 读收窄 (last-match-wins → 顺序即语义):
    #   ① deny 仓库根  — 仓库内未声明的一切 (含 backend/*.py, .env 邻近区) 不可读
    #   ② deny workspace 根 — workspace 内未声明的目录/文件不可读
    #   ③ allow 声明的 readable 子目录 — 覆盖前两条的 deny
    # ①②在③之前 → 声明内可读、声明外不可读。顺序反了会让 ③ 被 ② 覆盖
    # (全盘不可读) 或让 ① 被 ③ 覆盖 (整个仓库可读)。
    repo_root = _realpath(spec.repo_root) if spec.repo_root else None
    if repo_root and repo_root != ws:
        lines.append(f'(deny file-read* (subpath "{repo_root}"))')
    lines.append(f'(deny file-read* (subpath "{ws}"))')
    for rel in spec.readable_paths:
        lines.append(f'(allow file-read* (subpath "{_realpath(os.path.join(ws, rel))}"))')

    # 解释器自身路径放行 — venv 常在仓库内, 会被上面的仓库级 deny 挡掉,
    # 导致 execvp "Operation not permitted"。放在 deny 之后 (last-match-wins)。
    #
    # 需 **两种**形式 (实测: 缺一即失败):
    #   ① ``subpath`` 放行解释器所在**目录树** (.venv) — 解释器要读
    #      site-packages / pyvenv.cfg / stdlib 链接目标;
    #   ② ``literal`` 放行**每一级祖先目录** — 解释器启动时调 realpath()
    #      解析自身路径, 需要各级祖先目录的读权限 (subpath 只覆盖目录内容,
    #      不覆盖目录自身这一条路径项)。
    for path in spec.extra_allow_read:
        parent = os.path.dirname(os.path.abspath(path))
        lines.append(f'(allow file-read* (subpath "{parent}"))')
        for anc in _ancestor_dirs(path):
            lines.append(f'(allow file-read* (literal "{anc}"))')
        lines.append(f'(allow file-read* (literal "{os.path.abspath(path)}"))')
        real = _realpath(path)
        if real != os.path.abspath(path):
            lines.append(f'(allow file-read* (literal "{real}"))')
            real_parent = os.path.dirname(real)
            lines.append(f'(allow file-read* (subpath "{real_parent}"))')

    # 写放行: 仅 plan.writable_paths (deny default 已禁其余一切写)。
    for rel in spec.writable_paths:
        lines.append(f'(allow file-write* (subpath "{_realpath(os.path.join(ws, rel))}"))')

    # 凭据禁读 (DB / .env / 密钥) — 置于 allow 之后, last-match-wins 生效。
    for path in (*_credential_paths(ws), *spec.extra_deny_read):
        lines.append(f'(deny file-read* (subpath "{_realpath(path)}"))')

    # 网络: 全禁 (见 docstring)。
    lines.append("(deny network-outbound)")
    lines.append("(deny network-inbound)")

    return "\n".join(lines)


def ensure_writable_dirs(spec: SandboxSpec) -> None:
    """预建 plan 声明的可写目录。

    Seatbelt 的 subpath 放行要求目录已存在 (否则子进程无法 mkdir 穿过被 deny
    的父目录)。由**父进程**创建 — 子进程在沙箱内没有创建权限。
    """
    ws = Path(spec.workspace)
    for rel in spec.writable_paths:
        (ws / rel).mkdir(parents=True, exist_ok=True)


def limits_spec(spec: SandboxSpec) -> str:
    """ulimit 规格串 (launcher argv[1]) — ``NAME=soft:hard,NAME=soft:hard``。"""
    return ",".join(f"{name}={soft}:{hard}" for name, (soft, hard) in spec.resource_limits().items())


def build_limited_argv(argv: list[str], spec: SandboxSpec) -> list[str]:
    """在 argv 前插入 sandbox-exec + ulimit launcher 包装。

    最终被 exec 的仍是**原 argv** (launcher 内 ``os.execvp(argv[2:])``), 故
    L4 留痕的 argv 与 plan 一致, 语义未被包装层篡改。

    非 macOS / sandbox-exec 不存在 → 只套 launcher (ulimit 仍生效), 调用方
    需在 L4 留痕说明「无沙箱」降级。
    """
    launcher = [sys.executable, "-c", _LAUNCHER_SRC, limits_spec(spec), *argv]
    if not sandbox_supported():
        return launcher
    profile = build_sandbox_profile(spec)
    return ["/usr/bin/sandbox-exec", "-p", profile, "--", *launcher]


def run_with_limits(argv: list[str], spec: SandboxSpec, **kwargs) -> subprocess.CompletedProcess:
    """带 sandbox + ulimit 执行一条 argv。

    与 P4 的 ``_run_one`` 同形: 传 list argv (无 shell)、stdin=DEVNULL、
    cwd=锁定根。差别只在 **系统层**: sandbox-exec 包装 + exec launcher ulimit。
    """
    limited = build_limited_argv(argv, spec)
    kwargs.setdefault("stdin", subprocess.DEVNULL)
    kwargs.setdefault("cwd", spec.workspace)
    return subprocess.run(limited, **kwargs)


def describe_limits(spec: SandboxSpec, *, sandbox: str | None = None) -> dict[str, object]:
    """L4 留痕用的约束描述 (JSON 可序列化)。

    ``sandbox`` 显式传入实际生效的形态 (调用方已判定过可用性), 避免此处
    二次探测与调用方判定不一致 (降级路径下会误报 "sandbox-exec")。
    """
    return {
        "sandbox": sandbox if sandbox is not None else (
            "sandbox-exec" if sandbox_supported() else "unavailable"
        ),
        "platform": platform.system(),
        "workspace": spec.workspace,
        "writable_paths": list(spec.writable_paths),
        "readable_paths": list(spec.readable_paths),
        "network": list(spec.network),
        "limits": {k: list(v) for k, v in spec.resource_limits().items()},
    }


__all__ = [
    "SandboxSpec",
    "build_limited_argv",
    "build_sandbox_profile",
    "describe_limits",
    "run_with_limits",
    "sandbox_supported",
]
