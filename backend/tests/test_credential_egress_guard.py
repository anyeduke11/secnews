"""P0-11 (E2/F4-1) AI 层凭据出站门禁 — AST 守卫 + 运行时不外泄验证。

硬规则①来源: PRD §4.1 / 审计 FIRST_PRINCIPLES_REDESIGN_2026-10-02 §4.4
"只有 gateway 能带凭据出站"; PRD P0-11 验收: 带凭据出站路径 5/5 过
``check_credential_egress``, 新增裸 httpx 带 key 调用 CI 红。

两层验证:
1. **AST 扫描** ``backend/services/ai_hub/`` 全部生产代码: 任何实际携带凭据
   (Authorization / x-api-key 头、Bearer 串、api_key= kwarg) 的 HTTP 请求,
   其所在语句块必须**先**调用 ``check_credential_egress`` (同块或外层块,
   行号在前)。ollama 路径不附凭据头, 扫描器按"调用点是否真传凭据"判定,
   天然不报 —— 没有文件/函数级豁免清单, 也就没有豁免膨胀面。
2. **运行时**: base_url 被篡改成非白名单主机时, image/sensenova 路径必须抛
   ``EgressNotAllowedError``, 且一个 HTTP client 都不许构造 (凭据不外发)。

作用域刻意限定 ai_hub (LLM provider key 域): OAuth client_secret / GitHub
PAT / WebDAV / secrets 页用户自输 base_url 的连通性测试属不同信任域,
LLM 主机白名单语义不适用, 不属本守卫。
"""
from __future__ import annotations

import ast
import asyncio
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from backend.services.ai_hub.egress import EgressNotAllowedError

BACKEND = Path(__file__).resolve().parent.parent
AI_HUB = BACKEND / "services" / "ai_hub"

# HTTP 动词方法 (任意接收者的 client.post/get/... 均算; dict.get 无凭据
# kwarg, 在凭据判定环节天然被滤掉, 不会误报)。
_REQUEST_METHODS = {"get", "post", "put", "delete", "patch", "head", "request"}
_CLIENT_CTORS = {"Client", "AsyncClient", "ClientSession"}
_LIB_ROOTS = {"httpx", "requests", "aiohttp"}
_CRED_HEADER_KEYS = {"authorization", "x-api-key"}
_GUARD_NAME = "check_credential_egress"


# ═══════════════════════════════════════════════════════════════
# AST 扫描器
# ═══════════════════════════════════════════════════════════════

def _iter_owned(fn: ast.AST):
    """fn 的直属后代节点 (不进入嵌套函数体 —— 嵌套函数独立分析)。"""
    stack = list(getattr(fn, "body", []))
    while stack:
        node = stack.pop()
        yield node
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        stack.extend(ast.iter_child_nodes(node))


def _docstring_id(fn: ast.AST) -> set[int]:
    body = getattr(fn, "body", [])
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        return {id(body[0].value)}
    return set()


def _expr_bears_credential(node: ast.AST) -> bool:
    """表达式里是否出现凭据头键 / Bearer 串 (覆盖 f-string 与内联 dict)。"""
    for sub in ast.walk(node):
        if isinstance(sub, ast.Dict):
            for key in sub.keys:
                if (
                    isinstance(key, ast.Constant)
                    and isinstance(key.value, str)
                    and key.value.lower() in _CRED_HEADER_KEYS
                ):
                    return True
        elif isinstance(sub, ast.Constant) and isinstance(sub.value, str):
            if "bearer " in sub.value.lower():
                return True
    return False


def _root_name(func: ast.expr) -> str | None:
    cur = func
    while isinstance(cur, ast.Attribute):
        cur = cur.value
    return cur.id if isinstance(cur, ast.Name) else None


def _call_func_name(call: ast.Call) -> str:
    func = call.func
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return ""


def _is_http_call(call: ast.Call) -> bool:
    func = call.func
    if not isinstance(func, ast.Attribute):
        return False
    if func.attr in _REQUEST_METHODS:
        return True
    return _root_name(func) in _LIB_ROOTS and func.attr in _CLIENT_CTORS


def _call_carries_credential(call: ast.Call, cred_vars: set[str]) -> bool:
    """该 HTTP 调用点是否真的把凭据传了出去 (headers/auth/api_key)。"""
    for kw in call.keywords:
        # **some_headers 展开: 若该变量在本函数被赋过凭据头, 按携带算
        if kw.arg is None:
            if isinstance(kw.value, ast.Name) and kw.value.id in cred_vars:
                return True
            continue
        if kw.arg in ("headers", "auth"):
            if isinstance(kw.value, ast.Name) and kw.value.id in cred_vars:
                return True
            if _expr_bears_credential(kw.value):
                return True
        elif kw.arg == "api_key":
            return True
    return False


def _analyze_function(fn: ast.AST) -> list[int]:
    """返回函数内"携凭据但无前置 egress 守卫"的 HTTP 调用行号列表。"""
    owned = list(_iter_owned(fn))
    doc_ids = _docstring_id(fn)

    parent: dict[int, ast.AST] = {}
    for node in owned:
        for child in ast.iter_child_nodes(node):
            parent[id(child)] = node

    # 先收集"凭据变量": headers = {"Authorization": f"Bearer {key}"} 等
    cred_vars: set[str] = set()
    for node in owned:
        if id(node) in doc_ids:
            continue
        value = None
        targets: list[ast.expr] = []
        if isinstance(node, ast.Assign):
            value, targets = node.value, list(node.targets)
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            value, targets = node.value, [node.target]
        if value is not None and _expr_bears_credential(value):
            cred_vars.update(t.id for t in targets if isinstance(t, ast.Name))

    guards = [
        n for n in owned
        if isinstance(n, ast.Call) and _call_func_name(n) == _GUARD_NAME
    ]

    def enclosing_blocks(target: ast.AST) -> tuple[int, ...]:
        """target 的嵌套块链 (不含直接包含它的那条语句)。

        例: ``if x:`` 块内 ``with:`` 里的调用 → (if_id, with_id);
        函数体顶层的守卫语句 → ()。用于判定守卫与调用是否在同一分支。
        """
        blocks: list[int] = []
        cur = id(target)
        direct_stmt_skipped = False
        while cur in parent:
            nxt = parent[cur]
            if isinstance(nxt, ast.stmt):
                if not direct_stmt_skipped:
                    direct_stmt_skipped = True  # 直接包含语句本身不计
                else:
                    blocks.append(id(nxt))
            cur = id(nxt)
        return tuple(reversed(blocks))

    violations: list[int] = []
    for node in owned:
        if not isinstance(node, ast.Call):
            continue
        if not _is_http_call(node) or not _call_carries_credential(node, cred_vars):
            continue
        call_blocks = enclosing_blocks(node)
        covered = any(
            guard.lineno <= node.lineno
            and call_blocks[: len(guard_blocks)] == guard_blocks
            for guard in guards
            for guard_blocks in [enclosing_blocks(guard)]
        )
        if not covered:
            violations.append(node.lineno)
    return violations


def _scan_src(src: str) -> list[int]:
    tree = ast.parse(src)
    fn = next(
        n for n in tree.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    )
    return _analyze_function(fn)


def _iter_ai_hub_files():
    for path in sorted(AI_HUB.rglob("*.py")):
        if "__pycache__" not in path.parts:
            yield path


def _credential_functions_in(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and _function_has_credential_http(node)
    }


def _function_has_credential_http(fn: ast.AST) -> bool:
    """完整凭据判定 (含 headers 变量形态) — 供可见性清单使用。"""
    owned = list(_iter_owned(fn))
    cred_vars: set[str] = set()
    for node in owned:
        value = None
        targets: list[ast.expr] = []
        if isinstance(node, ast.Assign):
            value, targets = node.value, list(node.targets)
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            value, targets = node.value, [node.target]
        if value is not None and _expr_bears_credential(value):
            cred_vars.update(t.id for t in targets if isinstance(t, ast.Name))
    return any(
        isinstance(n, ast.Call)
        and _is_http_call(n)
        and _call_carries_credential(n, cred_vars)
        for n in owned
    )


# ═══════════════════════════════════════════════════════════════
# 1) 包级门禁: ai_hub 全部携凭据 HTTP 调用必须先过 egress 守卫
# ═══════════════════════════════════════════════════════════════

def test_all_credential_http_calls_go_through_egress_guard():
    """E2/F4-1: 新增裸 httpx/requests/aiohttp 带 key 调用即 CI 红。"""
    violations: list[str] = []
    for path in _iter_ai_hub_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for lineno in _analyze_function(node):
                    rel = path.relative_to(BACKEND)
                    violations.append(
                        f"{rel}:{lineno} {node.name} — 携凭据 HTTP 调用缺少"
                        "前置 check_credential_egress (PRD §4.1 硬规则①)"
                    )
    assert not violations, (
        "E2/F4-1 egress 门禁违规 — 凭据只能发往代码侧白名单主机:\n  "
        + "\n  ".join(sorted(violations))
    )


def test_scanner_is_not_blind_to_known_paths():
    """防"扫描器什么都看不见所以永远绿": 8 个已知携凭据函数必须被扫到。

    审计快照"5 条路径"的现态全量 = gateway 3 (openai chat / openai /
    anthropic ×2 分支在同一函数内) + image 2 + sensenova legacy 2 +
    pool 探测 1。
    """
    expected = {
        "gateway.py": {"_call_provider_chat", "_call_openai", "_call_anthropic"},
        "image_service.py": {"generate", "understand"},
        "service.py": {"_call_sensenova_eval", "_call_sensenova_detect"},
        "pool.py": {"probe_platform"},
    }
    for rel, names in expected.items():
        found = _credential_functions_in(AI_HUB / rel)
        missing = names - found
        assert not missing, (
            f"扫描器对 {rel} 失明: 未识别携凭据函数 {missing} — 门禁形同虚设"
        )


# ═══════════════════════════════════════════════════════════════
# 2) 扫描器元测试 (反例/正例, 参照 test_repo_write_guard 模式)
# ═══════════════════════════════════════════════════════════════

def test_scanner_flags_naked_bearer_httpx(tmp_path):
    src = (
        "import httpx\n"
        "async def f(base, key):\n"
        "    url = base + '/chat/completions'\n"
        "    headers = {'Authorization': f'Bearer {key}'}\n"
        "    async with httpx.AsyncClient(timeout=5) as client:\n"
        "        await client.post(url, json={}, headers=headers)\n"
    )
    assert _scan_src(src) == [6], "裸 Bearer + httpx 必须被标记在请求行"


def test_scanner_flags_inline_credential_header():
    src = (
        "import httpx\n"
        "def f(url, key):\n"
        "    return httpx.get(url, headers={'x-api-key': key}, timeout=5)\n"
    )
    assert _scan_src(src) == [3]


def test_scanner_passes_guarded_call():
    src = (
        "import httpx\n"
        "async def f(base, key):\n"
        "    check_credential_egress(base)\n"
        "    url = base + '/chat/completions'\n"
        "    headers = {'Authorization': f'Bearer {key}'}\n"
        "    async with httpx.AsyncClient(timeout=5) as client:\n"
        "        await client.post(url, json={}, headers=headers)\n"
    )
    assert _scan_src(src) == []


def test_scanner_ignores_keyless_ollama_style_call():
    """无凭据头的本机调用 (ollama) 不需要 egress 守卫。"""
    src = (
        "import httpx\n"
        "async def f(base):\n"
        "    url = base + '/api/chat'\n"
        "    async with httpx.AsyncClient(timeout=5) as client:\n"
        "        await client.post(url, json={'model': 'qwen'})\n"
    )
    assert _scan_src(src) == []


def test_scanner_rejects_guard_placed_after_request():
    """守卫在请求之后 = 凭据已发出, 不算覆盖。"""
    src = (
        "import httpx\n"
        "def f(base, key):\n"
        "    url = base + '/m'\n"
        "    headers = {'Authorization': f'Bearer {key}'}\n"
        "    with httpx.Client(timeout=5) as c:\n"
        "        c.post(url, headers=headers)\n"
        "    check_credential_egress(base)\n"
    )
    assert _scan_src(src) == [6]


def test_scanner_rejects_guard_in_other_branch():
    """守卫在另一 if 分支不能覆盖本分支的凭据请求。"""
    src = (
        "import httpx\n"
        "def f(cfg_type, base, key):\n"
        "    if cfg_type == 'openai':\n"
        "        check_credential_egress(base)\n"
        "    if cfg_type == 'anthropic':\n"
        "        url = base + '/messages'\n"
        "        headers = {'x-api-key': key}\n"
        "        with httpx.Client(timeout=5) as c:\n"
        "            c.post(url, headers=headers)\n"
    )
    assert _scan_src(src), "不同分支的守卫不得算作覆盖"


# ═══════════════════════════════════════════════════════════════
# 3) 运行时: 篡改 base_url → 凭据一个都不许出 (image/sensenova)
# ═══════════════════════════════════════════════════════════════

_EVIL_BASE = "https://evil.example.net/v1"


def _evil_ai():
    ai = MagicMock()
    ai._resolve_api_key.return_value = "sk-must-not-leave"
    ai._key_source.return_value = "env"
    ai._base_url.return_value = _EVIL_BASE
    return ai


class _BoomAsyncClient:
    def __init__(self, *a, **k):
        raise AssertionError("egress 守卫失效: 向恶意主机构造了 HTTP client")

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _BoomClient:
    def __init__(self, *a, **k):
        raise AssertionError("egress 守卫失效: 向恶意主机构造了 HTTP client")


@pytest.mark.parametrize("method,args", [
    ("generate", ("a cat",)),
    ("understand", ("aGVsbG8=", "描述这张图")),
])
def test_image_paths_block_credentials_to_evil_host(method, args, monkeypatch):
    from backend.services.ai_hub import image_service as img

    monkeypatch.delenv("HOTSPOT_LLM_ALLOWED_HOSTS", raising=False)
    monkeypatch.setattr(img.httpx, "AsyncClient", _BoomAsyncClient)
    svc = img.ImageGenerationService()
    with patch.object(svc, "_ai", _evil_ai()):
        with pytest.raises(EgressNotAllowedError, match=r"evil\.example\.net"):
            asyncio.run(getattr(svc, method)(*args))


@pytest.mark.parametrize("method", ["_call_sensenova_eval", "_call_sensenova_detect"])
def test_aiservice_sensenova_paths_block_credentials_to_evil_host(
    method, monkeypatch
):
    from backend.services.ai_hub import service as svc_mod

    monkeypatch.delenv("HOTSPOT_LLM_ALLOWED_HOSTS", raising=False)
    monkeypatch.setattr(
        svc_mod.AIService, "_base_url",
        classmethod(lambda cls, provider: _EVIL_BASE),
    )
    monkeypatch.setattr(svc_mod.httpx, "Client", _BoomClient)
    svc = svc_mod.AIService.__new__(svc_mod.AIService)
    with pytest.raises(EgressNotAllowedError, match=r"evil\.example\.net"):
        if method == "_call_sensenova_eval":
            svc._call_sensenova_eval("title", "content", "sk-must-not-leave", 5.0)
        else:
            svc._call_sensenova_detect("title", "summary", "sk-must-not-leave", 5.0)


def test_aiservice_eval_whitelisted_host_still_fires(monkeypatch):
    """白名单主机不得被误伤: 守卫通过, 请求照常携 Bearer 发出。"""
    from backend.services.ai_hub import service as svc_mod

    recorded: list[tuple[str, dict]] = []

    class _Resp:
        def raise_for_status(self):
            pass

        @staticmethod
        def json():
            return {"choices": [{"message": {"content": (
                '{"score": 8, "verdict": "ok", "summary": "s", "key_points": []}'
            )}}]}

    class _Client:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def post(self, url, json=None, headers=None):
            recorded.append((url, dict(headers or {})))
            return _Resp()

    monkeypatch.delenv("HOTSPOT_LLM_ALLOWED_HOSTS", raising=False)
    monkeypatch.setattr(svc_mod.httpx, "Client", _Client)
    monkeypatch.setattr(
        svc_mod.AIService, "_base_url",
        classmethod(lambda cls, provider: "https://token.sensenova.cn/v1"),
    )
    svc = svc_mod.AIService.__new__(svc_mod.AIService)
    out = svc._call_sensenova_eval("title", "content", "sk-real-key", 5.0)
    assert out["quality_score"] == 8
    assert recorded, "白名单主机请求未发出 — 守卫误伤"
    assert recorded[0][0] == "https://token.sensenova.cn/v1/chat/completions"
    assert recorded[0][1]["Authorization"] == "Bearer sk-real-key"
