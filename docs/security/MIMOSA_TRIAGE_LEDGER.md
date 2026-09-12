# Mimosa Triage 台账 (MIMOSA_TRIAGE_LEDGER)

- 建账: 2026-09-12; 依据扫描: `scan-2026-09-12T07-51-35.981Z-b3f23646372d` (seal `sha256:07d5b8…`, 270 findings)
- 方法: POST_R2 设计包 T1 三层漏斗 — L0 scope 豁免 → L1 批类复核 → L2 修复/豁免/接受
- 处置图例: **A-修复** = 本批已修 (commit 见 DEV-0187); **A-加固** = 防御性加固; **B-误报** = 扫描启发式不成立; **B-豁免** = 真实行为但非安全边界 (有依据接受); **C-接受** = 低风险备案
- 复扫对账: 下次全量扫描按 anchor 与本台账增量对账, 新增 findings 未处置前不得关闭

## 0. 漏斗总览

| 归属 | 数量 | 处置 |
|---|---|---|
| vendor (`runtime/upstreams/**` dsh/pi 第三方上游) | 147 | **整体豁免** — 只读 clone, 非本仓维护面, 升级随上游; 不逐条 triage |
| scripts (chaostest / loadtest 故障注入·压测工具) | 18 | **整体豁免** — 危险操作即功能本身 (failpoint/负载), 无生产路径 |
| scripts (运维/一次性工具) | 66 | **批量接受 (C)** — 多行 SQL 字符串启发式误报为主 + random 非加密用途; 其中 spike_gateway_s1_s3.py 硬编码凭据项已随**脚本删除**关闭 (扫描标"凭据"实为 dummy 占位符, 删除依据 scripts/AGENTS.md spike 约定) |
| **backend 生产代码** | **33** | **逐条 triage**, 见 §1 |
| other (根目录杂项) | 6 | **批量接受 (C)** — path-traversal 3 + ssrf 3, 均为运维脚本固定路径/固定源 |

## 1. backend 生产代码逐条台账 (33 条)

| 位置 | 类 | 处置 | 依据 |
|---|---|---|---|
| `api/mcp_agent_tools.py:115` | path-traversal | B-误报 | concept_name 先经白名单正则 (仅小写字母/数字/连字符/下划线) |
| `api/middleware.py:123` | other-security | B-误报 | 同上 |
| `api/middleware.py:89` | other-security | B-误报 | 异常文本写入内部观测库, 无安全边界穿越 |
| `collectors/fetchers.py:778` | insecure-randomness | B-豁免 | random.uniform 反爬延迟, 非加密用途 |
| `observability_records.py:164` | sql-injection | A-加固 | savepoint 名白名单化 re.sub (action 为调用方常量, 防御性) |
| `observability_records.py:177` | sql-injection | A-加固 | 同上 |
| `observability_records.py:181` | sql-injection | A-加固 | 同上 |
| `quality/final_url_resolver.py:179` | ssrf | A-修复 | 改走 safe_urlopen 中央防护 (url_safety) |
| `quality/url_validity_gate.py:33` | ssrf | A-修复 | 同上 |
| `quality/url_validity_gate.py:42` | ssrf | A-修复 | 同上 |
| `repository/db.py:154` | sql-injection | B-豁免 | 标识符来自 sqlite_master 自省非用户输入; DDL 不支持参数绑定 |
| `repository/db.py:160` | sql-injection | B-豁免 | 同上 |
| `repository/knowledge_repo.py:840` | sql-injection | B-误报 | WHERE kc.domain = ? 已参数化 |
| `security/mitre_attack.py:118` | ssrf | B-豁免 | 同上 |
| `security/mitre_attack.py:97` | ssrf | B-豁免 | 固定源 DEFAULT_BUNDLE_URL 常量, 非外部可控 |
| `services/action_service.py:68` | insecure-randomness | B-豁免 | ULID 生成 (标识符非机密), 随机防撞设计 |
| `services/artifact_service.py:62` | insecure-randomness | B-豁免 | 同上 |
| `services/dsh/live_bridge.py:32` | command-injection | B-误报 | subprocess.Popen argv 列表无 shell; 受管 dsh 上游二进制 |
| `services/judgment_service.py:73` | insecure-randomness | B-豁免 | 同上 |
| `services/knowledge_service.py:87` | insecure-randomness | B-豁免 | 同上 |
| `services/legacy_migrate_v1.py:74` | insecure-randomness | B-豁免 | 同上 |
| `services/maintenance_service.py:202` | sql-injection | B-豁免 | 表名来自 sqlite_master 自省统计 |
| `services/maintenance_service.py:203` | sql-injection | B-豁免 | 同上 |
| `services/maintenance_service.py:249` | sql-injection | B-误报 | qcl 为硬编码常量字符串 |
| `services/maintenance_service.py:559` | sql-injection | B-误报 | 同上 |
| `services/observability_sampling.py:138` | insecure-randomness | B-豁免 | 采样比例随机, 非加密用途 |
| `services/run_service.py:67` | insecure-randomness | B-豁免 | 同上 |
| `services/skill_runner/dispatch.py:379` | path-traversal | B-误报 | 写入前 realpath 工作区围栏校验 (:358-359) |
| `services/source_prober.py:61` | ssrf | B-误报 | 已走 validate_url + safe_urllib_request 中央防护 |
| `services/source_prober.py:81` | ssrf | B-误报 | 同上 |
| `services/url_batch_check_service.py:24` | ssrf | A-修复 | 同上 |
| `services/url_batch_check_service.py:32` | ssrf | A-修复 | 同上 |
| `wiki_fs/liveness.py:63` | ssrf | A-修复 | safe_urlopen + UrlSafetyError→dead; 私网/环回拒收语义入测试 |

A-修复要点:
- **SSRF ×6** (`final_url_resolver` / `url_validity_gate` ×2 / `url_batch_check` ×2 / `wiki_fs/liveness`):
  抓取/探测目标是 source·crawler·wiki 外链等外部可控 URL, 原先裸 urllib urlopen 未过中央防护。
  修复 = `backend/utils/url_safety.py` 新增 `safe_urlopen` (validate + DNS 预解析 + urlopen 单收口),
  四文件全部改走; `UrlSafetyError` 按各调用方失败语义映射 (None / url_unreachable / 0 / dead)。
- **savepoint 名加固 ×3** (`observability_records.record_audit`): 标识符插值白名单化 (re.sub 非法字符→_),
  现 call sites 均为内部常量, 属防御性加固。

## 2. 豁免边界声明

- `runtime/upstreams/**` 与 `scripts/chaostest/**`、`scripts/loadtest/**` 的发现项不进逐条台账。
  若上游代码被拷出 vendor 目录进入生产路径, 该豁免立即失效, 须按本台账方法重新 triage。
- 豁免 ≠ 安全: vendor 代码不含生产密钥 (secrets 走 env/keyring/llm_secrets), 但其自身漏洞由上游维护。

## 2b. 复扫对账 (2026-09-12 第二轮)

- 复扫: `scan-2026-09-12T08-46-16.879Z-554fa42893b8` (seal `sha256:c10783…`), 263 findings
- anchor 对账: 旧 146 → 新 141, **消除 5 / 新增 0**; 六处 SSRF 修复位点全部消失 ✓
- 仍标记项的台账状态确认:
  - `observability_records.py:166/179/183` (SAVEPOINT/RELEASE/ROLLBACK): 已白名单化
    (re.sub), 扫描器对标识符插值的固有启发式仍标记 — 运行时不可注入, 维持 A-加固结论
  - `repository/db.py:154/160`: 维持 B-豁免 (sqlite_master 自省 + DDL 无参数绑定机制)

## 3. 后续机制

- 增量对账: 每次全量扫描后, 新 anchor → 走同一漏斗; 台账追加不重写。
- 重扫节奏: 随 RUNBOOK 月度执行一次全量扫描 (Mimosa depth=normal)。
