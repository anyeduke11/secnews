# v1.0 T01 — 测试隔离与守卫策略

> 日期: 2026-09-05; 任务卡 = EXECUTION_GUIDE §4 T01; 修复对象 = V0.8.3_CRITICAL_REVIEW F13。
> 本文是测试隔离的设计说明与使用规则, 不是运行结果; 实际验证见 DEV-0137。

## 1. 分层隔离模型 (四层, 由外到内)

| 层 | 机制 | 生效时机 | 覆盖 |
|---|---|---|---|
| L1 会话强制 env | conftest 导入期(任何 backend 模块导入前)强制 `HOTSPOT_{DB,WARM_DB,COLD_DB,LOG,BACKUP,DATA,WIKI_ROOT}_PATH/DIR` 指向 `tempfile.mkdtemp("hotspot-test-iso-*")` | pytest 进程启动 | 全部默认数据根; 子进程继承 env |
| L2 会话哨兵 | `sys.addaudithook` — 拒绝 `sqlite3.connect` 生产库 / `open` 写生产数据根 / `socket.connect` 非回环 | 进程级, 不可卸载 | 任何绕过 config 的硬编码路径与意外出网 |
| L3 每测 fixture | `temp_db` (db) + `_isolate_temp_dbs` (warm/cold→pytest tmp) + `_isolate_knowledge_dirs` (wiki→pytest tmp + reload) | 每个测试 | 需要库/wiki 的测试各自独占 |
| L4 测试自身 | 显式 mock 模型/子进程 | 每个测试 | 出站行为 |

## 2. 哨兵规则 (L2 细节)

- **目录根** (`backend/{backups,logs,data}` / `llm-wiki-2.0/` / `codegarden/` / `data/` / `~/.pi`): 拒绝 `open(mode 含 wax+ 或 O_WRONLY/WRDWR/APPEND/CREAT/TRUNC)` 写入。
- **文件根** (`backend/hotspot.db` 及 warm/cold / `data/hotspot.db`): `sqlite3.connect` 一律拒绝 (含 `-wal/-shm` 侧车前缀); 读文件不拦。
- **出网**: `socket.connect` 仅放行 127.0.0.1/::1/localhost。DNS 解析不拦。
- 匹配 = raw + abspath 双查 (不 resolve, 防性能与软链歧义)。
- **逃逸口**: `HOTSPOT_TEST_UNGUARDED=1` 整会话关闭守卫+env 隔离 — 仅限 soak/live 手动场景, 普通测试禁止使用; 未来 `@pytest.mark.live` 若引入, 需走此 env 独立进程, 不做进程内开关 (audit hook 不可卸载)。
- 守卫自身异常静默 (不放大为业务失败); AssertionError 穿透到违规调用点。

## 3. 实现锚点

- `backend/tests/conftest.py` 顶部 (任何 backend import / `_ENV_SNAPSHOT` 之前):
  `_ISOLATION_GUARDED` / `_ISOLATION_ROOT` / 强制 env 块 / `_PROD_{DIR,FILE}_ROOTS` / `_t01_prod_hit` / `_t01_isolation_hook`。
- **单一真相源 = env**: conftest 会被 pytest 与 `backend.tests.conftest` 双重导入,
  第二身份从 `HOTSPOT_DB_PATH` 反推根复用, hook 用 `HOTSPOT_TEST_ISO_HOOKED=1` 幂等。
  (这两个键在 `_ENV_SNAPSHOT` 内, `_protect_hotspot_env` 每测还原后依然成立。)
- 会话 fixture `_t01_isolated_roots` (session/autouse): 断言隔离 + 对会话根 `db.init_db()` —
  未申请 temp_db 的测试由此拿到有 schema 的会话根库 (写入可验证落点, 而非被吞掉)。
- `config.data_dir` 新字段 (env `HOTSPOT_DATA_DIR`): export 缓存原硬编码 `backend/data`
  (测试期间曾写真实 `backend/data/export_cache.etag`), 现单一配置源。

## 4. 已知边界 (诚实记录)

1. audit hook 只护 pytest 进程本身; subprocess 子进程靠 **env 继承**隔离 (L1) — 子进程内无 hook。
2. 会话根 `tempfile.mkdtemp` 不自动清理 (保留作验收证据), 系统重启后由 OS 清理; 目录名前缀 `hotspot-test-iso-`。
3. `HOTSPOT_TEST_UNGUARDED=1` 下本文件全部哨兵测试 skipif 跳过 — 这是唯一的合法 skip 场景, 且普通 CI 不设该 env (零 skip 硬要求不受影响)。
4. 出网拦截对"本地起 socket server 再连接"放行 (回环白名单) — 端口绑定本身未拦。
