"""
Shared fixtures for hotspot backend tests.

Every test uses ``tmp_path``-isolated SQLite so no test ever touches
the real ``backend/hotspot.db``.

Two fixture families
--------------------
1. **temp_db** — replaces ``config.db_path`` with a temporary path and
   calls ``db.init_db()`` to create the full schema.  Ideal for repository
   and service-layer tests that need ``backend.repository.db.get_connection()``
   to work normally.

2. **e2e_app(router, migrations, ...)** — creates a standalone ``FastAPI``
   instance + ``TestClient`` without launching the lifespan.  Used by e2e
   tests that need a specific subset of routers and migrations.

Usage
-----
.. code-block:: python

    # In any test file under backend/tests/:
    def test_something(temp_db):
        from backend.repository.hotspot_repo import HotspotRepository
        repo = HotspotRepository()
        # ... uses temp_db via config.db_path monkeypatch

    # Or for e2e:
    def test_api_flow(e2e_api_client):
        resp = e2e_api_client.get("/api/health")
        assert resp.status_code == 200

Markers
-------
- ``pytest.mark.unit`` — pure unit, no DB or network
- ``pytest.mark.integration`` — DB + multiple layers
- ``pytest.mark.e2e`` — full workflow across routers + DB
"""
from __future__ import annotations

import os
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# ===========================================================================
# v1.0 T01: 会话级数据根隔离 (必须在任何 backend 模块导入 / _ENV_SNAPSHOT 之前)
# ===========================================================================
# 修复 F13: 此前未申请 temp_db 的测试 (agent_bridge 观测写入等) 会把记录写进
# 真实 backend/hotspot.db (agent_runs id=315..321)。这里在 pytest collection
# 之前强制 HOTSPOT_* 数据路径指向会话级临时根:
# - pydantic env_prefix=HOTSPOT_ → 字段级 env 在 backend.config 导入前生效;
# - wiki_fs.paths 的 *DIR 常量 import 时冻结 → env 必须先于其导入;
# - 强制覆盖 (非 setdefault): 测试不得依赖用户机器 .env 的真实数据路径;
# - 子进程自动继承 os.environ → subprocess 内的脚本同样被隔离。
# 生产路径哨兵: audit hook 拒绝测试进程对真实数据根的连接/写入/出网。
# 逃逸口: HOTSPOT_TEST_UNGUARDED=1 (仅 soak/live 手动场景, 普通测试禁止)。
_ISOLATION_GUARDED = os.environ.get("HOTSPOT_TEST_UNGUARDED") != "1"
# 单一真相源 = env 本身: conftest 可能被 pytest 与包路径 (backend.tests.conftest)
# 双重导入, mkdtemp 只在首次执行 — 后续身份从 HOTSPOT_DB_PATH 反推根并复用。
_existing_iso = os.environ.get("HOTSPOT_DB_PATH", "")
if _ISOLATION_GUARDED and "hotspot-test-iso-" in _existing_iso:
    _ISOLATION_ROOT = Path(_existing_iso).parent
elif _ISOLATION_GUARDED:
    _ISOLATION_ROOT = Path(tempfile.mkdtemp(prefix="hotspot-test-iso-"))

if _ISOLATION_GUARDED:
    os.environ["HOTSPOT_DB_PATH"] = str(_ISOLATION_ROOT / "hotspot.db")
    os.environ["HOTSPOT_WARM_DB_PATH"] = str(_ISOLATION_ROOT / "hotspot-warm.db")
    os.environ["HOTSPOT_COLD_DB_PATH"] = str(_ISOLATION_ROOT / "hotspot-cold.db")
    os.environ["HOTSPOT_LOG_DIR"] = str(_ISOLATION_ROOT / "logs")
    os.environ["HOTSPOT_BACKUP_DIR"] = str(_ISOLATION_ROOT / "backups")
    os.environ["HOTSPOT_DATA_DIR"] = str(_ISOLATION_ROOT / "data")
    os.environ["HOTSPOT_WIKI_ROOT"] = str(_ISOLATION_ROOT / "llm-wiki-2.0")

# 哨兵对象 = 真实数据根 (与上方 env 无关, 永远指向仓库实际位置)。
# 目录根: p == root 或 p 前缀 = root + sep; 文件根: p == root 或 p 前缀 = root
# (文件根不带 sep — 否则 ".../hotspot.db/" 永远匹配不上, 且可覆盖 -wal/-shm 侧车)。
_REPO_ROOT = Path(__file__).resolve().parents[2]
_PROD_DIR_ROOTS = tuple(
    str(p)
    for p in (
        _REPO_ROOT / "backend" / "backups",
        _REPO_ROOT / "backend" / "logs",
        _REPO_ROOT / "backend" / "data",
        _REPO_ROOT / "llm-wiki-2.0",
        _REPO_ROOT / "codegarden",
        _REPO_ROOT / "data",
        Path.home() / ".pi",
    )
)
_PROD_FILE_ROOTS = tuple(
    str(p)
    for p in (
        _REPO_ROOT / "backend" / "hotspot.db",
        _REPO_ROOT / "backend" / "hotspot-warm.db",
        _REPO_ROOT / "backend" / "hotspot-cold.db",
        _REPO_ROOT / "data" / "hotspot.db",
    )
)


def _t01_prod_hit(path: object) -> str | None:
    """路径是否落在生产数据根内 (raw + abspath 双查; 只做前缀比较, 不 resolve)。"""
    p = str(path) if path is not None else ""
    if not p:
        return None
    for probe in (p, os.path.abspath(p)):
        for root in _PROD_FILE_ROOTS:
            if probe == root or probe.startswith(root):
                return root
        for root in _PROD_DIR_ROOTS:
            if probe == root or probe.startswith(root + os.sep):
                return root
    return None


def _t01_isolation_hook(event, args):
    if not _ISOLATION_GUARDED:
        return
    try:
        if event == "sqlite3.connect":
            hit = _t01_prod_hit(args[0] if args else None)
            if hit:
                raise AssertionError(
                    f"T01 隔离守卫: 测试连接生产数据库 {args[0]!r} (root={hit}); "
                    "测试必须走会话隔离根/temp_db"
                )
        elif event == "open":
            path = args[0] if args else None
            mode = args[1] if len(args) > 1 and args[1] else ""
            flags = args[2] if len(args) > 2 else 0
            write_intent = any(c in mode for c in "wax+") or (
                isinstance(flags, int)
                and flags & (os.O_WRONLY | os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_TRUNC)
            )
            if write_intent:
                hit = _t01_prod_hit(path)
                if hit:
                    raise AssertionError(
                        f"T01 隔离守卫: 测试写生产数据文件 {path!r} (root={hit})"
                    )
        elif event == "socket.connect":
            addr = args[1] if len(args) > 1 else None
            host = addr[0] if isinstance(addr, tuple) and addr else None
            if isinstance(host, bytes):
                host = host.decode("idna")
            if host is not None and str(host) not in ("127.0.0.1", "::1", "localhost"):
                raise AssertionError(
                    f"T01 隔离守卫: 普通测试默认禁止出网 ({addr!r}); "
                    "live/soak 场景用 HOTSPOT_TEST_UNGUARDED=1 独立运行"
                )
    except AssertionError:
        raise
    except Exception:
        pass  # 守卫自身异常不放大; AssertionError 必须穿透到调用点


if _ISOLATION_GUARDED and os.environ.get("HOTSPOT_TEST_ISO_HOOKED") != "1":
    sys.addaudithook(_t01_isolation_hook)
    os.environ["HOTSPOT_TEST_ISO_HOOKED"] = "1"  # 双重导入只装一次 hook


# 模块级快照 — 必须在 conftest import 时取值, 不能放 fixture 里。
# 测试模块在 collection 阶段就执行顶层 import (test_crawl4ai_client →
# backend.utils.crawl4ai_client → crawl4ai/config.py 顶层 load_dotenv()),
# 会把项目根 .env 的 HOTSPOT_HOST=0.0.0.0 写进 os.environ; 若等 fixture
# 运行才快照, 快照本身已被毒化, 还原等于没还。
_ENV_SNAPSHOT = {k: v for k, v in os.environ.items() if k.startswith("HOTSPOT_")}

# ---------------------------------------------------------------------------
# 注册期 gate 快照 (根治 test_dsh_api 404, 2026-08-30)
# register_routers(app) 在 backend.main **import 时** (即 pytest collection
# 阶段) 读一次 feature gate; autouse fixture 运行晚于 collection, 无力回天。
# P1-2 把 TOML dsh 翻成 false 后, dsh 路由在测试进程里从未注册过 —
# test_dsh_api 4 用例 404 (S4 批次的"全量通过"声明未覆盖此点)。
# 这里在 backend.main 被 import 前铺好"测试全开" env, 与下方 autouse
# fixture 语义一致 (setdefault 尊重外部显式覆盖, 如 CI core-only job)。
# ---------------------------------------------------------------------------
os.environ.setdefault(
    "HOTSPOT_FEATURE_GATES",
    '{"extensions": {"codegarden": true, "codegarden_phase2b": true, '
    '"mcp": true, "sync": true, "tech_stack": true, "security_graph": true, '
    '"dsh": true}}',
)

# v0.8.1 Day 0: graceful drain 默认 0s — 否则每个 TestClient lifespan 关闭
# 都会 sleep HOTSPOT_GRACEFUL_TIMEOUT (默认 30s), 测试套件直接爆炸。
os.environ.setdefault("HOTSPOT_GRACEFUL_TIMEOUT", "0")


@pytest.fixture(autouse=True)
def _reset_provider_health_singleton():
    """v0.8.1 Day 3 起 ProviderHealth 模块级单例跨测试残留 (全量跑 image_service
    ×5 失败的根因: 前序文件 record 的 sensenova 失败把 breaker 判 OPEN)。
    每测前后复位 — 与 _protect_hotspot_env 同模式。"""
    from backend.services.ai_hub.provider_health import reset_provider_health

    reset_provider_health()
    yield
    reset_provider_health()


@pytest.fixture(autouse=True)
def _protect_hotspot_env() -> Iterator[None]:
    """阻断 crawl4ai load_dotenv() 对 os.environ 的跨测试污染.

    crawl4ai/config.py 模块顶层执行 ``load_dotenv()``, import 时把项目根
    .env 写入 os.environ 且永不还原 — 之后同进程内 ``Settings()`` 读到
    被污染的默认值, test_config::test_default_values 因此单跑通过、全量失败。
    本 fixture 在每个测试结束后把全部 HOTSPOT_ 前缀变量恢复到 conftest
    import 时的快照 (声明在最前 → LIFO 最后一个还原)。

    只覆盖 HOTSPOT_ 前缀 — pydantic env_prefix 决定只有这些变量能影响
    Settings 字段, 不越界清理无关环境变量。
    """
    prefix = "HOTSPOT_"
    yield
    polluted = {k: v for k, v in os.environ.items() if k.startswith(prefix)}
    for k in polluted.keys() - _ENV_SNAPSHOT.keys():
        del os.environ[k]
    for k, v in _ENV_SNAPSHOT.items():
        if polluted.get(k) != v:
            os.environ[k] = v


@pytest.fixture(autouse=True)
def _proxy_off_for_tests(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """cadence 修正批 T5: 代理默认开启 (builtin 127.0.0.1:7897) 后, 测试环境必须
    显式关闭, 否则触达 ProxySession / BackendSession 的用例会真的往本机代理出网。

    通过 env 覆盖 (proxy_config 的最高优先级) 而非 monkeypatch 函数, 让全部消费点
    (fetchers._proxy_retry / bid 第 3 步 / github / sogou / BackendSession) 一致直连。
    需要验证代理行为的测试自行 ``monkeypatch.setenv("HOTSPOT_PROXY_MODE", ...)``
    或 patch ``should_use_proxy`` / ``get_proxy_url``。熔断器状态每测试归零。
    """
    from backend import proxy_config as _pc

    monkeypatch.setenv("HOTSPOT_PROXY_MODE", "off")
    _pc.invalidate_settings_cache()
    _pc.reset_proxy_health()
    yield
    _pc.invalidate_settings_cache()
    _pc.reset_proxy_health()


@pytest.fixture(scope="session", autouse=True)
def _t01_isolated_roots() -> Iterator[Path]:
    """T01 会话级隔离断言 + 会话根 schema 初始化。

    - 断言 config 的三库/日志/备份/数据目录与 Wiki 根全部落在会话临时根
      (来自本模块顶部强制 env; 每个测试看得到的"测试数据写到哪"就是这个目录);
    - 对会话根跑一次 db.init_db() — 未申请 temp_db 的测试 (agent_bridge 观测
      写入等) 由此拿到有 schema 的会话根库, 其写入落会话根而非真实库。
    会话根不自动清理 (tempfile.mkdtemp), 作为验收证据可事后检查。
    """
    from backend.config import config
    from backend.repository import db
    from backend.wiki_fs.paths import wiki_root

    if not _ISOLATION_GUARDED:
        yield _ISOLATION_ROOT
        return

    root = str(_ISOLATION_ROOT) + os.sep
    for name, p in (
        ("db_path", config.db_path),
        ("warm_db_path", config.warm_db_path),
        ("cold_db_path", config.cold_db_path),
        ("log_dir", config.log_dir),
        ("backup_dir", config.backup_dir),
        ("data_dir", config.data_dir),
        ("wiki_root", wiki_root()),
    ):
        assert str(p).startswith(root), f"T01 隔离失效: {name}={p} 不在会话根 {root}"
    db.init_db()
    yield _ISOLATION_ROOT


@pytest.fixture(autouse=True)
def _crawl4ai_disabled_for_tests(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> Iterator[None]:
    """测试环境统一禁用 crawl4ai (gateway 方案 §3.1 ③).

    生产 ``crawl_config.yaml`` 默认 ``enabled: true``; 若不隔离, 装了
    crawl4ai + Chromium 的环境里任何触发 crawl4ai 路径的测试都会尝试
    启动真实浏览器。本 fixture 把 ``crawl4ai_client._config_path`` 指向
    一个 disabled 的 tmp yaml → ``is_available()=False`` → 全部走 aiohttp
    路径。crawl4ai 专属测试 (test_crawl4ai_client / test_crawl4ai_parser)
    自行写 tmp yaml 重新启用。
    """
    from backend.utils import crawl4ai_client

    cfg = tmp_path / "crawl_config_disabled.yaml"
    cfg.write_text("crawl4ai:\n  enabled: false\n")
    monkeypatch.setattr(crawl4ai_client, "_config_path", cfg)
    yield


@pytest.fixture(autouse=True)
def _disable_startup_catchup(monkeypatch: pytest.MonkeyPatch) -> None:
    """v1.8: 全局禁用 lifespan 的启动自动追抓 (真实全网抓取).

    main.py lifespan 在 TestClient(app) 启动时会 enqueue 一次「本周一 → 现在」
    的真实网络抓取, 导致测试挂起/极慢。所有测试一律关闭, 单测 catchup 逻辑请
    直接调用 catchup_service 的函数。
    """
    from backend.config import config
    monkeypatch.setattr(config, "catchup_on_startup", False)


@pytest.fixture(autouse=True)
def _feature_gates_all_on_for_tests() -> None:
    """v0.4.3: 测试环境默认全部扩展开启。

    分层重构后路由/job 注册受 feature_gates.toml 控制, 而生产默认
    codegarden/mcp/tech_stack/security_graph=false。既有功能测试假设这些
    功能在线, 因此测试环境通过 HOTSPOT_FEATURE_GATES env 全开。
    组合矩阵 (core-only / all-on / mixed) 由 test_feature_gates.py
    和 CI backend-core-only job 专门覆盖。
    """
    import os

    from backend.extensions import reset_gates

    prev = os.environ.get("HOTSPOT_FEATURE_GATES")
    # P1.6: 测试环境也全开 codegarden_phase2b (M2/M3/M4) 保证既有功能测试在线
    # v0.6.3: 补 dsh — 动态 gate 读数 (per-request) 与注册期快照保持一致
    os.environ["HOTSPOT_FEATURE_GATES"] = (
        '{"extensions": {"codegarden": true, "codegarden_phase2b": true, '
        '"mcp": true, "sync": true, '
        '"tech_stack": true, "security_graph": true, "dsh": true}}'
    )
    reset_gates()
    yield
    if prev is None:
        os.environ.pop("HOTSPOT_FEATURE_GATES", None)
    else:
        os.environ["HOTSPOT_FEATURE_GATES"] = prev
    reset_gates()


@pytest.fixture(autouse=True)
def _oauth_provider_mock(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """D1 (Batch ⑧): 测试环境强制走 MockOAuthProvider + 重置单例。

    任何测试若 import oauth_provider, 默认拿到 mock 而非 CloudBase 真身。
    集成测试 (需真身) 在子 fixture 里再 ``monkeypatch.setenv("HOTSPOT_OAUTH_PROVIDER", "cloudbase")``。
    """
    monkeypatch.setenv("HOTSPOT_OAUTH_PROVIDER", "mock")
    monkeypatch.delenv("HOTSPOT_OAUTH_CLIENT_ID", raising=False)
    monkeypatch.delenv("HOTSPOT_OAUTH_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("HOTSPOT_OAUTH_REDIRECT_URI", raising=False)
    monkeypatch.delenv("HOTSPOT_OAUTH_AUTHORIZE_URL", raising=False)
    from backend.services import oauth_provider
    oauth_provider.reset_oauth_provider()
    yield
    oauth_provider.reset_oauth_provider()


@pytest.fixture(autouse=True)
def _api_sampling_disabled_in_tests(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """D4 (Batch ⑧): 测试环境强制 success/error/slow 全 100%, 锁住"必落表"语义.

    否则 D4 引入的 10% success_rate 会让 test_api_observability 等单次断言
    不可靠 (status=400 路径被随机丢弃); 集成测试应改用 ``monkeypatch.setenv``
    显式注入 0% 验证 sampling 行为本身 (见 test_observability_sampling.py).
    """
    monkeypatch.setenv("HOTSPOT_API_SAMPLING_SUCCESS_RATE_PCT", "100")
    monkeypatch.setenv("HOTSPOT_API_SAMPLING_ERROR_RATE_PCT", "100")
    monkeypatch.setenv("HOTSPOT_API_SAMPLING_SLOW_RATE_PCT", "100")
    monkeypatch.setenv("HOTSPOT_API_SAMPLING_SLOW_THRESHOLD_MS", "2000")
    yield


@pytest.fixture(autouse=True)
def _isolate_knowledge_dirs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """P1: 所有测试强制隔离 wiki 根目录 — 根治测试污染真实知识库.

    此前全量测试会改写真实 ``llm-wiki-2.0/items/*.md`` 的 ingested_at
    (每次跑完 17+ 个文件被污染) 并重写 ``llm-wiki-2.0/_MAP.md``
    (4008 items → 3), 需要每次手动 git checkout 恢复。v0.6.3 P3-4 收官
    后 wiki 唯一根已切到 llm-wiki-2.0, 本 fixture 改用 ``HOTSPOT_WIKI_ROOT``
    env 一次设到 tmp_path, ``backend.wiki_fs.paths`` 的所有 *DIR 常量
    (ITEMS_DIR / CONCEPTS_DIR / DRAFTS_DIR / LEARNING_*DIR / SUMMARIES_DIR
    / GRAPH_PATH / SOUL_PATH / CALENDAR_PATH) 都基于 ``resolve_wiki_root()``
    动态推导, 因此无须逐个 monkeypatch — 一次性 env 重定向即生效。

    仍保留对各 service 模块顶层导出 ``ITEMS_DIR / KNOWLEDGE_DIR /
    SOUL_PATH`` 等符号的 monkeypatch, 是为了兼容测试自身或下游模块
    已经持有对这些符号的引用 (例如 ``from backend.services.X import
    ITEMS_DIR`` 在 fixture 之前 import)。
    """
    import importlib

    # 1) 通过 env 让所有 wiki_fs/paths.* 派生常量自动跟随 tmp_path
    monkeypatch.setenv("HOTSPOT_WIKI_ROOT", str(tmp_path / "wiki"))

    # 2) 重新加载 wiki_fs.paths, 让模块级 *DIR 常量按当前 env 重新绑定
    from backend.wiki_fs import paths as wiki_paths
    importlib.reload(wiki_paths)

    kdir = tmp_path / "wiki"
    redirect = {
        "KNOWLEDGE_DIR": kdir,
        "ITEMS_DIR": kdir / "items",
        "CONCEPTS_DIR": kdir / "concepts",
        "DRAFTS_DIR": kdir / "content" / "drafts",
        "PENDING_DIR": kdir / "learning" / "tasks" / "pending",
        "DONE_DIR": kdir / "learning" / "tasks" / "done",
        "FAILED_DIR": kdir / "learning" / "tasks" / "failed",
        "MAP_PATH": kdir / "_MAP.md",
        "SOUL_PATH": kdir / "soul.md",
    }
    modules = (
        "backend.services.bookmark_sync",
        "backend.services.compiler",
        "backend.services.concept_linker",
        "backend.services.content_service",
        "backend.services.cubox_sync",
        "backend.services.federation_service",
        "backend.services.history_import",
        "backend.services.knowledge_sync",
        "backend.services.learning_service",
        "backend.services.map_updater",
        "backend.services.soul_service",
    )
    for mod_name in modules:
        mod = importlib.import_module(mod_name)
        for attr, val in redirect.items():
            if hasattr(mod, attr):
                monkeypatch.setattr(mod, attr, val)
        # 让模块顶层 from … import 进来的 wiki_fs/paths 符号也跟随新 env
        if hasattr(mod, "wiki_paths"):
            importlib.reload(mod.wiki_paths)
    # 重新加载依赖 wiki_fs/paths 的具体 service 模块, 让它们的内部
    # ``from backend.wiki_fs.paths import X`` 拿到的也是新的 Path 对象
    for mod_name in modules:
        importlib.reload(importlib.import_module(mod_name))


@pytest.fixture(autouse=True)
def _isolate_temp_dbs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """M2-T6 方案 A: 隔离 warm/cold 库路径 — 根治测试写生产 warm.db.

    config.warm_db_path 默认指向 backend/hotspot-warm.db, 若不隔离,
    测试经 get_connection() 的 ATTACH 逻辑会挂上生产 warm.db,
    INSERT INTO warm.x 类写入直接污染真实数据。本 fixture 把三个
    库路径全部重定向到 tmp_path, 与 temp_db 的 db_path 隔离对齐。
    """
    from backend.config import config

    monkeypatch.setattr(config, "warm_db_path", tmp_path / "test-warm.db")
    monkeypatch.setattr(config, "cold_db_path", tmp_path / "test-cold.db")
    monkeypatch.setattr(config, "cold_db_key", "")


@pytest.fixture
def temp_db(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Redirect config.db_path to a temporary SQLite file with full schema.

    Replaces ``backend.config.config.db_path``, closes any previously
    cached thread-local connection, then runs ``init_db()``.
    """
    from backend.config import config
    from backend.repository import db

    test_db = tmp_path / "test.db"
    # P1: db_path 必须是 Path (repository/db.py get_connection 调用
    # db_path.parent.mkdir, str 会 AttributeError — 此前未被触发的隐性 bug)
    monkeypatch.setattr(config, "db_path", test_db)
    db.close_db()
    db.init_db()
    yield test_db
    db.close_db()


@pytest.fixture
def e2e_api_client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[TestClient]:
    """Standalone FastAPI + TestClient with an isolated temp DB.

    Injects the full set of API routers but does **not** start the
    lifespan (no scheduler / collector).  The DB at ``tmp_path/test.db``
    has all migrations applied via ``init_db()``.
    """
    from backend.api import register_routers
    from backend.api.middleware import TraceIDMiddleware
    from backend.config import config
    from backend.exceptions import register_exception_handlers
    from backend.repository import db

    test_db = tmp_path / "test.db"
    # P1: db_path 必须是 Path (见 temp_db 注释)
    monkeypatch.setattr(config, "db_path", test_db)
    # M2-T6: warm/cold 同样隔离 (_isolate_temp_dbs 是 autouse, 但 e2e
    # 不依赖 temp_db fixture, 显式再设一次防御性对齐 — 幂等无害)
    monkeypatch.setattr(config, "warm_db_path", tmp_path / "test-warm.db")
    monkeypatch.setattr(config, "cold_db_path", tmp_path / "test-cold.db")
    monkeypatch.setattr(config, "cold_db_key", "")

    db.close_db()
    db.init_db()

    app = FastAPI()
    app.add_middleware(TraceIDMiddleware)
    register_exception_handlers(app)
    register_routers(app)

    yield TestClient(app)

    db.close_db()
