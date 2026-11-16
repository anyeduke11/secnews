"""C5-1 L3 系统层 — sandbox profile 生成 / ulimit 生效 / 越界告警落表。

「为什么」: P4 把边界做成了**声明级** (enforcer 校验 argv + 路径合法性),
但声明不等于强制 — 一个合法 argv 仍可在运行时写 workspace 外的文件、读
凭据、联网。本组测试锁死三件事:

1. **profile 内容正确** — 写只放行 plan.writable_paths、读收窄到
   readable_paths、凭据载体 deny、出网 deny (更严不放松)。
2. **系统层真的拦得住** — 真跑 sandbox-exec, 证明越界写/读被内核拒绝
   (PermissionError), 而非仅"profile 里写了一行字"。
3. **ulimit 真的传到最终进程** — launcher exec 后目标进程自身
   getrlimit 可见收紧值; 超 CPU 限额被杀 (SIGXCPU)。

macOS-only 的用例在非 macOS (CI ubuntu) 自动 skip — L3 不可用时的降级
语义由 test_sandbox_degrades_gracefully_when_unsupported 覆盖。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from backend.services.execution_runner import sandbox as sb
from backend.services.execution_runner.sandbox import (
    SandboxSpec,
    build_limited_argv,
    build_sandbox_profile,
    ensure_writable_dirs,
    limits_spec,
    run_with_limits,
    sandbox_supported,
)

macos_only = pytest.mark.skipif(
    not sandbox_supported(), reason="sandbox-exec 仅 macOS 可用"
)


@pytest.fixture
def ws(tmp_path) -> str:
    """workspace 锁定根 (realpath — Seatbelt 匹配 realpath)。"""
    root = tmp_path / "codegarden" / "demo"
    (root / "out").mkdir(parents=True)
    (root / "src").mkdir(parents=True)
    (root / "src" / "a.txt").write_text("hello", encoding="utf-8")
    return str(root.resolve())


def _spec(ws: str, **kw) -> SandboxSpec:
    return SandboxSpec(
        workspace=ws,
        writable_paths=kw.get("writable_paths", ("out",)),
        readable_paths=kw.get("readable_paths", ("src",)),
        network=kw.get("network", ()),
        max_cpu_seconds=kw.get("max_cpu_seconds", 30),
        max_file_bytes=kw.get("max_file_bytes", 1024 * 1024),
        max_open_files=kw.get("max_open_files", 256),
        repo_root=kw.get("repo_root"),
    )


# ---------------------------------------------------------------------------
# profile 生成 (纯函数, 无平台依赖)
# ---------------------------------------------------------------------------
def test_profile_is_default_deny():
    """基线必须是 deny default — 默认拒绝, 不靠 allow default 兜底。"""
    profile = build_sandbox_profile(_spec("/tmp/ws"))
    assert profile.startswith("(version 1)")
    assert "(deny default)" in profile
    assert "(allow default)" not in profile


def test_profile_denies_all_writes_then_allows_only_declared():
    """写只放行 plan.writable_paths (deny default 已禁其余)。"""
    ws = os.path.realpath("/tmp/ws")
    profile = build_sandbox_profile(_spec(ws, writable_paths=("out",)))
    writes = [ln for ln in profile.splitlines() if ln.startswith("(allow file-write*")]
    assert len(writes) == 1 and f"{ws}/out" in writes[0]
    # workspace 根本身未被放行 (plan 未声明 → 不可写)
    assert not any(f'(subpath "{ws}")' in ln for ln in writes)


def test_profile_write_allowlist_is_exactly_declared_paths():
    ws = os.path.realpath("/tmp/ws")
    profile = build_sandbox_profile(_spec(ws, writable_paths=("out",)))
    writes = [ln for ln in profile.splitlines() if ln.startswith("(allow file-write*")]
    assert len(writes) == 1 and f"{ws}/out" in writes[0]
    assert not any(f'(subpath "{ws}")' in ln for ln in writes)


def test_profile_denies_network_outbound_and_inbound():
    """出站控制底线 — plan.network 非空也不放行 (macOS 不支持 host 级白名单)。"""
    for net in ((), ("example.com",)):
        profile = build_sandbox_profile(_spec("/tmp/ws", network=net))
        assert "(deny network-outbound)" in profile
        assert "(deny network-inbound)" in profile
        assert "network-outbound" not in profile.replace("(deny network-outbound)", "")


def test_profile_denies_credential_files():
    """凭据载体禁读 — env 剥离挡不住直接读 .db / .env。"""
    profile = build_sandbox_profile(_spec("/tmp/ws"))
    assert "(deny file-read*" in profile
    # 仓库根的 .env / .db 被显式 deny
    assert any(".env" in ln or ".db" in ln for ln in profile.splitlines()
               if ln.startswith("(deny file-read*"))


def test_profile_read_allowlist_matches_declared_paths():
    """声明的 readable 子目录被放行 (blanket allow 之外)。"""
    ws = os.path.realpath("/tmp/ws")
    profile = build_sandbox_profile(_spec(ws, readable_paths=("src",)))
    reads = [ln for ln in profile.splitlines()
             if ln.startswith("(allow file-read*") and "subpath" in ln]
    assert len(reads) == 1 and f"{ws}/src" in reads[0]


def test_profile_deny_repo_root_precedes_read_allow():
    """仓库级收窄顺序: deny 仓库根 → deny workspace → allow 声明子目录。

    last-match-wins: 放行必须排在两条 deny 之后, 否则声明内也不可读;
    反之若两条 deny 排在放行之后, 声明外仍可读 — 边界形同虚设。
    """
    ws = os.path.realpath("/tmp/repo/codegarden/demo")
    repo = os.path.realpath("/tmp/repo")
    profile = build_sandbox_profile(
        _spec(ws, readable_paths=("src",), repo_root=repo))
    deny_repo = profile.index(f'(deny file-read* (subpath "{repo}"))')
    deny_ws = profile.index(f'(deny file-read* (subpath "{ws}"))')
    allow_src = profile.index(f'(allow file-read* (subpath "{ws}/src"))')
    assert deny_repo < deny_ws < allow_src


def test_profile_skips_repo_deny_when_repo_is_workspace():
    """workspace == 仓库根时不能 deny 自己 — 否则全盘不可读。"""
    ws = os.path.realpath("/tmp/repo")
    profile = build_sandbox_profile(_spec(ws, readable_paths=("src",), repo_root=ws))
    # 仅一条 deny file-read* subpath (workspace 自身), 不重复 deny
    denies = [ln for ln in profile.splitlines()
              if ln.startswith("(deny file-read*") and "subpath" in ln]
    assert len([d for d in denies if f'"{ws}")' in d]) == 1


def test_profile_uses_realpath_not_symlink_path(tmp_path):
    """Seatbelt 匹配 realpath — /tmp/x 实为 /private/tmp/x, 不用 realpath 会失效。"""
    root = tmp_path / "codegarden" / "demo"
    root.mkdir(parents=True)
    profile = build_sandbox_profile(_spec(str(root)))
    assert os.path.realpath(str(root)) in profile


# ---------------------------------------------------------------------------
# ulimit 规格串
# ---------------------------------------------------------------------------
def test_limits_spec_format():
    spec = _spec("/tmp/ws", max_cpu_seconds=7, max_file_bytes=1234, max_open_files=9)
    parsed = dict(
        part.split("=") for part in limits_spec(spec).split(",")
    )
    assert parsed["RLIMIT_CPU"] == "7:7"
    assert parsed["RLIMIT_FSIZE"] == "1234:1234"
    assert parsed["RLIMIT_NOFILE"] == "9:9"


def test_limited_argv_keeps_original_argv_at_tail():
    """包装层不得篡改 argv — L4 留痕的 argv 必须与 plan 一致。"""
    spec = _spec("/tmp/ws")
    argv = [sys.executable, "-c", "print(1)"]
    limited = build_limited_argv(argv, spec)
    # 尾部 = limits 规格串 + 原 argv (launcher 内 execvp 的是原 argv)
    assert limited[-len(argv):] == argv
    assert limited[-len(argv) - 1] == limits_spec(spec)


# ---------------------------------------------------------------------------
# L3 降级语义 (无 sandbox-exec 的平台)
# ---------------------------------------------------------------------------
def test_sandbox_degrades_gracefully_when_unsupported(monkeypatch):
    """无 sandbox-exec → 仍套 ulimit launcher, 但不假称有沙箱。"""
    monkeypatch.setattr(sb, "sandbox_supported", lambda: False)
    spec = _spec("/tmp/ws")
    limited = build_limited_argv(["/bin/echo", "x"], spec)
    assert "/usr/bin/sandbox-exec" not in limited
    assert "/bin/echo" in limited  # ulimit launcher 仍在
    described = sb.describe_limits(spec)
    assert described["sandbox"] == "unavailable"


# ---------------------------------------------------------------------------
# 系统层真拦 (macOS)
# ---------------------------------------------------------------------------
@macos_only
def test_sandbox_blocks_write_outside_declared_paths(ws):
    """声明外的写入被内核拒绝 (PermissionError) — 非仅 profile 文本。"""
    spec = _spec(ws)
    ensure_writable_dirs(spec)
    proc = run_with_limits(
        [sys.executable, "-c", "open('escape.txt','w').write('x')"],
        spec, capture_output=True, text=True,
    )
    assert proc.returncode != 0
    assert "PermissionError" in proc.stderr or "Operation not permitted" in proc.stderr
    assert not (Path(ws) / "escape.txt").exists()


@macos_only
def test_sandbox_allows_write_in_declared_path(ws):
    """声明内的写入必须成功 — 否则隔离过头等于功能瘫。"""
    spec = _spec(ws)
    ensure_writable_dirs(spec)
    proc = run_with_limits(
        [sys.executable, "-c", "open('out/ok.txt','w').write('x'); print('WROTE')"],
        spec, capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert "WROTE" in proc.stdout
    assert (Path(ws) / "out" / "ok.txt").exists()


@macos_only
def test_sandbox_allows_read_in_declared_path(ws):
    spec = _spec(ws)
    proc = run_with_limits(
        [sys.executable, "-c", "print(open('src/a.txt').read())"],
        spec, capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert "hello" in proc.stdout


@macos_only
def test_sandbox_blocks_read_outside_declared_paths(ws):
    """声明外读取被拒 — 含 workspace 内未声明的目录。"""
    spec = _spec(ws)
    (Path(ws) / "secret.txt").write_text("leak", encoding="utf-8")
    proc = run_with_limits(
        [sys.executable, "-c", "print(open('secret.txt').read())"],
        spec, capture_output=True, text=True,
    )
    assert proc.returncode != 0
    assert "leak" not in proc.stdout


@macos_only
def test_sandbox_blocks_credential_file_read(ws, tmp_path, monkeypatch):
    """凭据载体 (含 .env) 在沙箱内不可读 — env 剥离挡不住直接读文件。"""
    repo = tmp_path / "repo"
    (repo / "backend").mkdir(parents=True)
    (repo / ".env").write_text("MASTER_KEY=leak-me\n", encoding="utf-8")
    (repo / "hotspot.db").write_text("secret-db", encoding="utf-8")
    work = repo / "codegarden" / "demo"
    work.mkdir(parents=True)
    (work / "src").mkdir()
    (work / "src" / "a.txt").write_text("ok", encoding="utf-8")
    monkeypatch.chdir(repo)

    spec = SandboxSpec(
        workspace=str(work.resolve()),
        writable_paths=(), readable_paths=("src",), network=(),
        repo_root=str(repo.resolve()),
    )
    for secret in (".env", "hotspot.db"):
        proc = run_with_limits(
            [sys.executable, "-c", f"print(open('{secret}').read())"],
            spec, capture_output=True, text=True,
        )
        assert proc.returncode != 0, f"{secret} 不应可读"
        assert "leak" not in proc.stdout


@macos_only
def test_sandbox_blocks_network(ws):
    """出网被系统层阻断 (声明为空 = 全禁)。"""
    spec = _spec(ws)
    code = (
        "import socket\n"
        "try:\n"
        "    socket.create_connection(('example.com', 80), timeout=3)\n"
        "    print('NET-OK')\n"
        "except Exception as e:\n"
        "    print('NET-BLOCKED', type(e).__name__)\n"
    )
    proc = run_with_limits([sys.executable, "-c", code], spec, capture_output=True, text=True)
    assert "NET-BLOCKED" in proc.stdout


@macos_only
def test_ulimit_reaches_final_process(ws):
    """ulimit 经 launcher 传递到**最终进程** (exec 后仍可见)。"""
    spec = _spec(ws, max_cpu_seconds=7, max_file_bytes=1234, max_open_files=9)
    code = (
        "import resource\n"
        "print(resource.getrlimit(resource.RLIMIT_CPU))\n"
        "print(resource.getrlimit(resource.RLIMIT_FSIZE))\n"
        "print(resource.getrlimit(resource.RLIMIT_NOFILE))\n"
    )
    proc = run_with_limits([sys.executable, "-c", code], spec, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    assert "(7, 7)" in proc.stdout
    assert "(1234, 1234)" in proc.stdout
    assert "(9, 9)" in proc.stdout


@macos_only
def test_cpu_limit_kills_runaway_process(ws):
    """CPU 超限 → 内核 SIGXCPU 杀进程 (rc=-24), 不是超时兜底。"""
    spec = _spec(ws, max_cpu_seconds=1)
    proc = run_with_limits(
        [sys.executable, "-c", "x=0\nwhile True:\n    x+=1"],
        spec, capture_output=True, text=True,
    )
    assert proc.returncode == -24


@macos_only
def test_file_size_limit_blocks_oversized_write(ws):
    """单文件超限 → Errno 27 (File too large), 磁盘不被撑爆。"""
    spec = _spec(ws, max_file_bytes=1024)
    ensure_writable_dirs(spec)
    proc = run_with_limits(
        [sys.executable, "-c", "open('out/big.bin','wb').write(b'x'*100000)"],
        spec, capture_output=True, text=True,
    )
    assert "File too large" in proc.stderr
