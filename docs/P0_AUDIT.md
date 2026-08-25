# P0 代码治理审计报告 (2026-08-24)

> **作用域**: hotspot 后端 Python (backend/) + 前端 API 调用 (frontend/src/)
> **方法**: 静态扫描 + 行为采样 + golden test 固化, 不改实现语义
> **目标**: 给后续 P1+ 治理建立基线和判据, 非一次性大改

## 一、扫描方法

| 工具 | 命令 | 关注点 |
|------|------|--------|
| `ruff check --select F401` | unused imports | 死代码 (import 层面) |
| `ruff check --select F811` | re-imported | 重复定义 |
| `ruff check --select F841` | unused local variables | 局部死变量 |
| `app.openapi()` schema | 后端真路由表 | 路由对账左集 |
| `grep -roh '/api/...' frontend/src/` | 前端 API 调用串 | 路由对账右集 |
| `characterization test` | 实测 golden 数值 | 算法层行为锁 |

## 二、P0-1 死代码清理成果

### 2.1 F401 / F811 (unused imports, re-imports)

| 项 | 修复前 | 修复后 | 净减少 |
|----|--------|--------|--------|
| F401 unused import | ~32 | 0 (含 F841 协同) | -32 行 |
| F811 redefinition | ~3 | 0 | -3 行 |

执行: `.venv/bin/ruff check backend/ --select F401,F811 --fix --exclude tests`
结果: `All checks passed!`

### 2.2 F841 (unused local variables) — 现状 59 个

**决策**: 不批量自动删除。理由:
- 部分是"合理占位" (e.g., `_, _, rid3 = mock.patch(...)` 的中间变量)
- 部分是真死代码 (e.g., `soul_service.py:47-50` 4 个统计变量)
- 部分是函数返回值被忽略但有副作用 (e.g., `record_access → True`)

**已知 dead candidates** (按 review 风险低→高排序):

| 文件 | 行 | 变量 | 风险 | 建议 |
|------|-----|------|------|------|
| backend/services/soul_service.py | 47 | with_domain | 低 (统计, 完全无引用) | 直接删 |
| backend/services/soul_service.py | 48 | with_concepts | 低 | 直接删 |
| backend/services/soul_service.py | 49 | compiled | 低 | 直接删 |
| backend/services/soul_service.py | 50 | orphan_items | 低 (调了 repo 但不用返回值) | 直接删 |
| backend/services/weekly_report_overview_service.py | 50 | end_of_week | 中 (未来可能用) | rename `_end_of_week` |
| backend/services/bookmark_sync.py | 252 | is_dead | 中 (分支标志, 应入 log/return) | rename `_is_dead` |
| backend/services/collection_service.py | 698 | title_norm | 低 (去重流程已用 url) | 直接删 |
| backend/services/collection_service.py | 499 | started_at | 低 (时间未入返回值) | rename `_started_at` |
| backend/services/export_service.py | 314 | summary | 中 (可能喂 UI, 需看 context) | review |
| backend/api/codegarden.py | 436 | head | 中 (注释明示"简化") | rename `_head` |
| backend/api/sync.py | 352 | pk_map | 高 (注释中"同步方向") | ✅ 已删 (方案 A, 附带修 2 处 `state.merged_bundle` dict 属性访问 500 bug + 补 4 表征测试) |
| backend/api/todos.py | 321 | deleted | 低 (返回值未用, 调用方不依赖) | rename `_deleted` |
| backend/quality/jobs.py | 93 | conn_path | 中 (逻辑检查后未消费) | review |
| backend/repository/catchup_checkpoint_repo.py | 128 | sql | 低 (调试残留) | 直接删 |
| backend/repository/todo_repo.py | 336 | total_raw | 低 | 直接删 |
| backend/repository/todo_repo.py | 497 | prev_status | 中 (审计日志未消费) | review |
| backend/services/backup_service.py | 239 | new_seq | 低 | 直接删 |
| backend/services/codegarden_scanner_service.py | 243 | scripts | 低 | 直接删 |
| backend/services/collection_service.py | 361 | merged_source_results | 中 (聚合未消费) | review |
| backend/services/collection_service.py | 366 | result | 中 | review |
| backend/services/maintenance_service.py | 252 | archive_total | 低 | 直接删 |
| backend/services/secrets_service.py | 199 | result | 中 (DELETE 状态) | rename `_result` |
| backend/services/secrets_service.py | 311 | e | 低 (异常分支) | rename `_e` |
| backend/services/secrets_service.py | 669 | cipher | 低 | rename `_cipher` |
| backend/services/triggers/t3_link_to_structure.py | 83 | summary | 低 | 直接删 |
| backend/collectors/bid_collector.py | 639 | used_proxy | 中 (debug 日志意图) | rename + 加 debug |
| backend/collectors/github_collector.py | 225 | used_proxy | 中 | rename + 加 debug |
| backend/collectors/github_collector.py | 249 | used_crawl4ai | 中 | rename + 加 debug |

**总统计**: 59 个 F841, 估 30 个可直接删 / 15 个 rename `_` 前缀 / 14 个需要 review

**执行建议 (P1 task)**: 按风险分三批, 每批一个 commit + 全量测试:
- 批 1 (low, ~30 个): soul_service / collection_service / repository / backup_service / maintenance_service / triggers / collectors 的明显残留
- 批 2 (medium, ~15 个): api/codegarden / api/sync / quality/jobs 的"待消费"中间值, 加 `_` 前缀
- 批 3 (high, ~14 个): sync.py pk_map / todos.py deleted 等业务关键路径, 需配 PR 描述改业务行为

### 2.3 F401 in tests/

测试文件中的 unused imports 共 17 个, 分布在 catchup_phase9 / catchup_repo / catchup_service / catchup_watchdog / cli_contract / collect_validator 等。
**决策**: 不修复。理由: 测试用 fixture 局部 import 居多, 重构后通常直接消失。

## 三、P0-2 API 路由对账

### 3.1 数据

| 集合 | 数量 | 来源 |
|------|------|------|
| 后端真路由 (/api/) | 213 | `app.openapi()` schema |
| 前端调用 (/api/...) | 119 | grep `frontend/src/**/*.{ts,tsx}` |
| **后端独有 (未被前端调用)** | **94** | comm -23 |
| 前端独有 (后端无此路由) | **7** | comm -13 |

### 3.2 前端独有 (需立即修复)

| 路由 | 风险 | 推断原因 |
|------|------|----------|
| `/api/favorites/a` | 高 | 看起来是错误路径, 应是 `/api/favorites/{id}` |
| `/api/kl/planning-actions/1/status` | 高 | 看起来是 hardcoded 测试路径, 应是参数化 |
| `/api/llm/digest` | 中 | LLM digest API 缺后端实现 (feature gate) |
| `/api/mcp/status` | 中 | MCP status endpoint 后端无 (feature gate 关闭) |
| `/api/mcp/tools` | 中 | 同上 |
| `/api/settings/mcp/enabled` | 中 | MCP enabled setting 后端无 |
| `/api/soul` | 中 | `soul_service.py` 有 `get_soul` 但路由未注册 |

**建议**: P1-1 优先核对 7 个 mismatch, 多半是 feature gate / 旧路径残留。

### 3.3 后端独有 94 个路由分类

| 类别 | 数量 | 路由示例 | 设计意图 |
|------|------|----------|----------|
| kl_pipeline 内部 | 18 | `/api/kl/*`, `/api/knowledge/*` | kl_pipeline API, 由 kl frontend 调用 |
| internal/admin | 11 | `/api/maintenance/*`, `/api/alerts/*`, `/api/cache/*` | cron/CLI 入口, 非前端 |
| scheduled jobs 触发 | 9 | `/api/quality/logs`, `/api/digests` | 调度器→API |
| codegarden (Phase 2b) | 12 | `/api/codegarden/*` | feature gate 关闭时的隐式路由, 前端按状态显示 |
| sync 协议 | 6 | `/api/sync/*` | 多端 sync, 客户端→服务端 |
| ai_hub / llm | 8 | `/api/llm/*`, `/api/recommend` | ai_hub 前端 (独立 SPA) |
| knowledge mgmt | 14 | `/api/knowledge/*` | knowledge-master skill 调用 |
| secnews dashboard | 6 | `/api/secnews/*`, `/api/wiki/*` | secnews-dashboard SPA (独立) |
| sources / health | 4 | `/api/sources/*` | 健康监控, 后台用 |
| security graph | 5 | `/api/security/*` | security_cockpit SPA (独立) |
| mode / settings | 4 | `/api/mode/*` | 配置前端 |

**结论**: 94 个路由并非"死路由", 而是分散到 7 个独立 frontend (kl / ai_hub / secnews / security_cockpit / knowledge-master / codegarden / main hotspot)。
**建议**: 不做删除, 改为建立 frontend→route 显式映射表 (P1-2 task)。

## 四、P0-3 Characterization Test 成果

新文件: `backend/tests/test_characterization_golden.py` (51 个测试, 全绿)

### 4.1 覆盖矩阵

| 模块 | 测试类 | 用例数 | 锁定的行为 |
|------|--------|--------|-----------|
| simhash | TestSimHashGolden | 8 | 8 段真实文本的 64-bit fingerprint (SHA-256 source) |
| simhash | TestSimHashDeterminism | 2 | 跨调用 / 跨进程稳定 |
| simhash | TestHammingDistance | 4 | 对称 / 自反 / 边界 (0/1/64) |
| simhash | TestIsDuplicateGolden | 5 | 5 对样本的 (hamming, is_dup) 锁定 |
| simhash | TestSimHashEdgeCases | 3 | 空 / 纯空白 / 纯标点不抛错 |
| retention | TestRetentionRunDecayFrozen | 5 | run_decay 增量更新 / 混合 initial / 错误 ISO / 空文件 / 缺 entries |
| retention | TestRetentionRecordAccessFrozen | 3 | reset existing / 新建 entry / events LIFO 50 |
| retention | TestRetentionHealthFrozen | 4 | 空库 ok / 全 healthy ok / below threshold / < 80% fail |
| concept_linker | TestLinkTagsToConceptsGolden | 6 | curated mapping / 去重 / 未知 tag / 10 tag 安全域样本 |
| concept_linker | TestValidateGraphSchemaGolden | 9 | 6 种 edge types / 非法 type / 缺 weight / dangling source / dup / top-level / nodes 必须是 list |

### 4.2 设计原则

- **不追求覆盖率**: 不重复 `test_wiki_archiver_retention.py` 的 27 个已有 retention 测试
- **golden 数值透明**: 每个 fingerprint 十六进制 + 十进制双标
- **frozen 时间**: retention 测试用 ISO 字符串 + `now=` 参数, 不依赖 freezegun
- **tmp_path 隔离**: 写 retention.json 的测试用 tmp_path, 不污染 llm-wiki-2.0/
- **不引入新依赖**: 仅用 pytest + 标准库

### 4.3 重构安全网

后续对这三个模块的修改, 若打破 assertion:
- SimHash: 多半是哈希源改了 → 必须 PR 评审 + 重建去重索引 (production 风险)
- Retention: 多半是公式/参数变了 → 确认 SPEC §18 仍适用
- Concept linker: 多半是 schema/curated mapping 变了 → 确认 llm-wiki-2.0 graph.json 一致性

## 五、执行命令复盘

```bash
# 1. 死代码扫描
.venv/bin/ruff check backend/ --select F401,F811,F841 --no-fix 2>&1 | grep "^F" | wc -l  # 81
.venv/bin/ruff check backend/ --select F401,F811 --fix --exclude tests  # All checks passed!

# 2. 路由提取
.venv/bin/python -c "from backend.main import app; schema=app.openapi(); print(len(schema['paths']))"  # 213 routes

# 3. Characterization test
.venv/bin/python -m pytest backend/tests/test_characterization_golden.py -v --tb=short  # 51 passed in 0.28s
```

## 六、P1+ 建议（按价值排序）

1. **P1-1**: 修复 7 个 frontend-only 路由 mismatch (前端→后端契约违反, 用户可见 bug)
2. **P1-2**: F841 批 1 (low risk, ~30 行直删, 1 个 commit)
3. **P1-3**: 跨 7 个 frontend (kl/ai_hub/secnews/security_cockpit/knowledge-master/codegarden/main hotspot) 建路由注册表 → 0 个未注册孤儿路由
4. **P1-4**: 后端模块入口加 `__all__`, 让 ruff / IDE 锁定对外 API
5. **P1-5**: 给 `compute_simhash` / `decay_score` / `link_tags_to_concepts` 加 mutation test, 验证 golden 真能 catch bug

## 七、未做事项

- ~~未跑全量 `pytest backend/tests/` 验证~~ (P1-5 验证: 230+ 相关测试全过, 2700+ 全量未跑因后台 pytest 仍未结束)
- ~~未对 frontend-only 7 个 mismatch 做实际修复~~ (P1-1 ✅ 6f235816: 2 个真 mismatch 已修, 5 个非真留档)
- ~~未实际删除 59 个 F841~~ (P1-2 ✅ 7ca15779: 批 1 删 11 个低风险, F841 55→44; 剩余 48 待 P2)
- 未改 `app.openapi()` 路由表 (P0 是 audit, 不改实现) — 仍 N/A, 后续若 CI 加路由 mismatch 审计再用
- ~~未对 5 个独立 frontend (kl/ai_hub/secnews/security_cockpit/knowledge-master) 做调用方深扫~~ (P1-3 ✅ a7965dc8: 跨 7 子模块路由注册表已建, hotspot 内未发现的 5 模块已分类)

## 八、P1 落地摘要 (2026-08-24)

- **P1-1** (commit 6f235816): 修 2/7 真 mismatch, 5/7 留档为 feature gate/test mock
- **P1-2** (commit 7ca15779): 删 11/55 低风险 F841, 剩 44 (含 33 tests + 11 production medium-risk)
- **P1-3** (commit a7965dc8): 建 ROUTE_REGISTRY.md (166 行) + routes/index.tsx 顶部注释
- **P1-4** (commit de4decf4): mutation test 10/11 = 90.9% catch rate (PASS ≥ 80%)
- **P1+ 剩余 (P2)**: 48 F841 + 1 真实盲点 (decay_score 精度) + 后端 __all__ 全量补齐

## 九、P2 落地摘要 (2026-08-25)

> **P2 7 子任务全部交付**, 6 commits (P2-1~P2-6) + P2-7 同步 commit。
> **完整 report**: `docs/P2_5_ALL_AUDIT.md` + `docs/P2_6_COCKPIT_EVAL.md`

- **P2-1** (commit 5fe965a7): F841 批 2 production rename, 中等风险 12 文件 17 个 dead vars (`_` 前缀 + `del` 占位 + `# noqa: F841` 留调用痕迹); 配 debug log 确认调用源; ruff F841: **44 → 27** (-17 production)
- **P2-2** (commit eae608e1): pk_map 1 个 high-risk dead variable 留档 `docs/P2_DEAD_VARS_PR_REVIEW.md`, 等 PR 评审决议 (删前需确认热路径调用方)
- **P2-3** (commit cf0a0a14): mutation 盲点补 test — `decay_score(days=1.5)` 精度断言 (M8 变异: 去掉 round → golden 失败); 新增 `TestDecayScorePrecisionFrozen` 6 tests + 修 mutation output regex; mutation score: 10/11 → **11/11 (100%)**
- **P2-4** (commit dbbb3d3c): F841 tests/ 30 个 cleanup, **区分 mock patch 设计意图**: 25 个真 dead 直接删, 2 个 mock patch context manager 改 `_mock_log` (ruff 视为 used), 1 个未消费 mock_exec drop `as` 子句; 237 tests passed
- **P2-5** (commit 4d76b2c2): 后端模块入口 `__all__` 全量 audit — 23 个 `__init__.py`, 10 个补齐 `__all__: list[str] = []` 零契约 (显式语义, 禁 `from pkg import *`); 顺手 ruff `--fix F401` 清理 19 个测试 unused imports
- **P2-6** (commit d2200a5c, doc `docs/P2_6_COCKPIT_EVAL.md`): security cockpit SPA 完整评估 (3 个静态 HTML + 1 CSS = 2363 行, CRM-like, 与 hotspot 业务正交); 三档方案 **A 冻结留档 (0h, 推荐) / B MVP 简版 (12h) / C 完整移植 (90h)**; 决策权归用户/产品方
- **P2-7** (本 commit): 三文档同步 — PROGRESS.md / CHANGELOG.md / P0_AUDIT.md §九

**P2 累计收益**:
- ruff F841: **44 → 0** (P2-1/-4), 剩 1 high-risk (pk_map, P2-2 留档)
- ruff F401: **20+ → 0** (P2-5 顺手)
- mutation coverage: 10/11 → **11/11** (100%)
- `__all__` 契约: 23 个 `__init__.py` 三档语义清晰

> **数据时间**: 2026-08-25 (系统时间)
> **状态**: P2 全项交付 (7/7 子任务), 待 P3 任务接续

## 十、P3 范围定义 (2026-08-25)

> §九尾注 "待 P3 任务接续" 此前仅为占位; 本节将其落为正式范围。
> **定位**: P3 = 治理线收尾 — 存量质量债清零 + 测试稳定性根治, **不含产品功能**。
> 数据基线: 2026-08-25 实测 (非引用历史数字)。

### P3-1 存量 lint 治理 (默认规则集, CI 必修)

- **现状**: `ruff check backend/` (CI 同款默认配置, `ci.yml:41`) = **41 errors**, 会挂 CI
  (计划门槛 `--select F401,F841` 已归零, 不受影响)
- **分布**: RUF100 ×16 + I001 ×15 + RUF022 ×4 (共 35 个 `[*] --fix` 可自动) /
  C401 ×2 / ASYNC230 ×2 / RUF006 ×1 / ASYNC221 ×1
- **做法**: 自动批一个 commit (`--fix` 仅限 RUF100/I001/RUF022 三类纯机械项);
  手工批逐个评审 — ASYNC230/221 与 RUF006 触及异步运行时语义
  (是否真阻塞事件循环需逐处确认), 禁止盲目 `--unsafe-fixes`
- **验收**: `ruff check backend/` 默认配置 → **0 errors**; 全量 pytest 零回归

### P3-2 前端存量测试失败清理

- **现状**: vitest 17 失败用例集中在 4 文件 — knowledge 模式组件
  (`Phase13ModeComponents` 5 / `OutboxMode` 7 / `ReviewMode` 3) + `CategoryNav` 2,
  另有文件级收集错误若干 (9 failed files 中其余为 import/collect 失败)
- **做法**: 先甄别 (真 bug / 过期断言 / 环境依赖) 再修; **根因消除优先于 skip**
  (用户既有偏好); 按 "一文件一 commit" 分批
- **验收**: vitest 全绿; 若确有必须保留的失败, 每个附根因文档

### P3-3 phase3 搜索性能断言根治

- **现状**: `test_phase3_acceptance.py::...::test_search_returns_cross_layer_results_under_500ms`
  固定 <500ms 阈值负载敏感 — 高负载全量跑 (448s) 超阈值, 单独复跑即过 (2026-08-25 实录)
- **做法**: 根因消除 — 预热后测量或按环境推导阈值, 或显式 `@pytest.mark.slow` 移出默认门;
  不接受"留档容忍"
- **验收**: 连续 3 次全量套件该测试稳定通过

### P3-4 (stretch) Playwright 浏览器 E2E 最小链路

- CRM US1-US3 一条 happy path; 沙箱受限则维持 backlog, 不阻塞 P3 收口

### 明确不进 P3

- CRM UI 增强 (批量导入/看板拖拽) / Auth 多租户 — 产品 backlog
- `app.openapi()` 路由 mismatch CI 化 — §七已留档为可选项, 无触发需求
- security-cockpit mockup 目录处置 — 方案 C 已交付, 目录维持原样

### 执行约定 (沿袭 P1/P2)

一任务一提交; staging 只限自身路径; 禁用 git stash; Mimosa scanner_no_output 照常提交、不宣称安全;
改动注册代码后同步 ARCHITECTURE.md (`generate_meta.py --check`)。

## 十一、计划外遗留清单 (2026-08-25 盘点)

| # | 事项 | 实测状态 | 归属 |
|---|------|----------|------|
| L1 | pk_map 高危 F841 | ✅ **已闭环** — `P2_DEAD_VARS_PR_REVIEW.md` §9: 方案 A 落地, 顺手修复两裁决端点 AttributeError→500 前置 bug, F401/F841=0 首次真正达成 | 无遗留 |
| L2 | 默认规则集 lint 41 errors (RUF100×16 等) | 会挂 CI (`ci.yml:41` 默认配置) | **P3-1** |
| L3 | 前端 vitest 17 failed (knowledge 组件为主) | HEAD 本底存量, worktree 基线核实 | **P3-2** |
| L4 | phase3 搜索 <500ms 断言 flaky | 负载敏感计时抖动 | **P3-3** |
| L5 | Playwright 浏览器 E2E 缺位 | 以全栈 E2E 替代中 | P3-4 stretch |
| L6 | codegarden 端口分配测试环境敏感 | ✅ 8765→8766 已改 (`3f5fe7d0`), lsof 依赖仍在但风险已降 | 无遗留 |
| L7 | CRM UI 增强 / Auth 多租户 | 产品 backlog | 不入治理线 |

> **状态**: P3 范围已定义 (P3-1 ~ P3-4), 待排期执行; L1/L6 已闭环仅存档。
