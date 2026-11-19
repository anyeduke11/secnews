# 前端重构 V1 · 分批验证报告（随批更新）

> 依据：[`FRONTEND_REWRITE_V1_PLAN.md`](../FRONTEND_REWRITE_V1_PLAN.md) §7 验收口径 / §7.4 交付物。
> 基线：[`FRONTEND_REWRITE_BASELINE_2026-11-17.md`](FRONTEND_REWRITE_BASELINE_2026-11-17.md)（唯一基线，只与它比较）。
> 纪律：实现侧不自评 PASS；本文件只登记**命令 + 原始输出数字**，结论由 owner 复核。

## 1. 批次进度总览

| 批 | 内容 | 退出条件 | 状态 |
|---|---|---|---|
| B0 | 覆盖率 / 首屏基线实测入档 | 数字入档 + `tsc` 绿 + 包体积不变 | ✅ 2026-11-17 |
| B1 | `tokens.css` 单一源 + L1 primitives 八件 + coverage.thresholds | 每原子 ≥1 测试 / 无业务依赖 / token 重复定义归零 | ✅ 2026-11-17 |
| B2 | 壳原地替换 + 全局 Toast 提到根 | `nav4_shell` 改造后绿 / 三态主题可切换 / 旧页 `--sn-*` 正常渲染 | ✅ 2026-11-17（见 §3） |
| B3 | `useQuery` + 域 API 模块 | 54 处直调降为 0 | ✅ 2026-11-17（见 §5） |
| B4 | 资讯域 `/` 重写 | 首屏区块全保留 / 单文件 ≤300 行 / 包体积不增 | ✅ 2026-11-18（见 §8；包体积于 §8.5 复测达标，D7 已关闭） |
| B5 | 知识域 + 行动域重写（owner 裁决范围 = 12 个超限文件） | 同上 | ✅ 2026-11-18（见 §9 + §10 + **§11 B5.6**；12 + 7 = 19 个超限容器全部达标） |
| B5.6 | 剩余 7 个超限文件拆分 + R3 契约冲突裁决 | 同上 + 豁免口径落地 | ✅ 2026-11-18（见 §11） |
| B6 | 设置域 + 工具页 + 旧 CSS 删除 + **组件层剩余 17 件超限拆分** + 性能对比 | §7 全部指标达标 / 旧代码零残留 | ✅ 2026-11-19（四子批 a/b/c/d，见 §13–§16；R4 LCP 单指标达标） |
| B8 | 缺口收口批（G3 / G4 / G5 补做） | 三项缺口关闭 / 门禁全绿 / R4 LCP 达标 | ✅ 2026-11-19（三子批 a/b/c，见 §19；LCP 中位 124–160 ms） |
| B9 | 遗留项收口批（设置域合并 + 页头原子 + 视觉机检） | chunk 回落 / DOM 逐字节不变 / 像素级零差异 / 门禁全绿 / R4 LCP 达标 | ✅ 2026-11-19（三子批 a/b/c，见 §20；LCP 中位 120–132 ms；新增缺口 G7 / G8 登记） |

## 2. B1 验证证据

```bash
cd frontend && npx tsc --noEmit                    # exit 0
cd frontend && npx vitest run --coverage           # 全量通过
cd frontend && npx vite build --logLevel error      # exit 0
python scripts/generate_meta.py --check             # OK
```

| 指标 | 基线（B0） | B1 实测 |
|---|---|---|
| Lines | 57.05% | 57.52% |
| Statements | 57.05% | 57.52% |
| Functions | 57.42% | 57.70% |
| Branches | 76.39% | 76.62% |
| 首屏 JS gzip | 92,998 B | 93,010 B |
| 首屏 CSS gzip | 15,146 B | 15,323 B |
| 全量 JS gzip | 549,589 B | 549,592 B |

primitives 八件 colocated test 合计 32 tests；`^:root` 定义全仓仅剩 `tokens/tokens.css` + `styles/breakpoints.css`。

## 3. B2 验证证据（壳原地替换）

### 3.1 改动面

| 文件 | 变更 |
|---|---|
| `src/shell/types.ts` | `SentinelLayer` / `PipeSnapshot` / `SourceHealthRow` / `BandItem` 契约类型 |
| `src/shell/menuOf.ts` | `LAYER_DEFS` + `menuOf()` + `BANDNAV_DEFS` + bandnav 收起持久化读写 |
| `src/shell/pipe.tsx` | `fetchPipe` / `usePipe` / `usePipeReloadOnSse` / `PipeProvider` / `fetchIngested24h` |
| `src/shell/PipeBar.tsx` | 印务条（心跳条） |
| `src/shell/MenuNav.tsx` | 报头 masthead + 版面条 bandnav + 主题三态按钮 |
| `src/shell/AppShell.tsx` | 壳组装层（`PipeProvider` → `.sentinel` → `MenuNav` → `PipeBar` → children） |
| `src/components/sentinel/SentinelShell.tsx` | 降为 **9 行兼容桥**，对外 4 类导出符号契约不变（B6 全量改指后删除） |
| `src/App.tsx` | 根层组合 `ToastProvider`（Toast 提到根） |
| `src/components/PageLayout.tsx` | `PageLayout` / `SentinelLayout` 不再自包 `ToastProvider` |
| `src/routes/index.tsx` | 删除 `/` 路由级 `ToastProvider`（DEV-0314 的临时补丁随根化撤销） |

零行为变更依据：DOM 结构与类名（`.sentinel` / `masthead` / `bandnav` / `pressbar`）、`menuOf` 全部 27 条归属分支、`BANDNAV_DEFS` 四菜单 chip 与 gate 过滤、bandnav 收起持久化键 `bandnav-collapsed` 全部原样保留。

### 3.2 退出条件逐条

| 退出条件 | 证据 | 结果 |
|---|---|---|
| `nav4_shell` 守卫改造后绿 | 守卫改为对 `src/shell/*` 六文件**聚合**断言（断言条目与强度不变），并新增「Toast 提到根」守卫；`npx vitest run src/routes/__tests__/nav4_shell.test.tsx` → **61 passed** | ✅ |
| 三态主题可切换 | 新增 `SentinelShell.test.tsx` 运行时用例：light → dark → paper → light，逐态断言 `<html data-theme>` 与 `localStorage['hotspot-theme']` | ✅ |
| 旧页在 `--sn-*` 别名下正常渲染 | `--sn-*` 别名 191 处仍在 `components/sentinel/sentinel.css`（→ 全局 token），`tokens/tokens.css` 中 0 处；`AppShell` 引入该 CSS，全部旧页渲染用例通过 | ✅ |

### 3.3 四道门禁（全量）

```bash
cd frontend && npx tsc --noEmit                          # exit 0
cd frontend && npx vitest run --coverage                 # exit 0
cd frontend && npx vite build --logLevel error           # exit 0
python scripts/generate_meta.py --check                  # OK
```

- 测试：**107 文件 / 751 tests 全部通过**（B1 后 99 文件 → 新增 shell 拆分与主题/Toast 用例）
- 覆盖率：Lines **57.54%** / Statements **57.54%** / Functions **57.85%** / Branches **76.62%**（基线 57.05 / 57.05 / 57.42 / 76.39，thresholds 未降）
- `src/shell` 覆盖率：AppShell 100% / MenuNav 100% lines / PipeBar 100% lines / menuOf 86.48% lines / pipe 100% lines
- `generate_meta --check`：`{"jobs": 56, "collectors": 19, "routers": 99, "services": 155, "core_routers": 67}` + AGENTS 7/7 文档数字与版本一致

### 3.4 体积复测（口径同基线 §2）

| 指标 | 基线（B0） | B2 实测 | 差 |
|---|---|---|---|
| 首屏 JS gzip | 92,998 B | **92,835 B**（index 27,060 + vendor-react 53,738 + SentinelHomePage 12,037） | −163 B |
| 首屏 CSS gzip | 16,507 B（15,146 + 1,361） | **16,567 B**（15,211 + 1,356） | +60 B |
| 全量 JS gzip | 549,589 B / 69 chunk | **548,357 B / 69 chunk** | −1,232 B |

B2 不做视觉与页面重写，体积基本持平属预期；20% 目标由 B4/B5/B6 承担。

## 4. 显式缺口（不隐藏）

| # | 缺口 | 影响 | 关闭时点 |
|---|---|---|---|
| G1 | ✅ **已关闭 2026-11-18** — LCP 基线实测中位数 **252 ms**（3 次：276 / 252 / 236），元素 `h1.headline`；证据见 §6 | §7.1 的 LCP 80% 目标（≤ ~201.6 ms）判为**高风险项**，理由见 §6.3 | 已关闭 |
| G2 | ✅ **已关闭 2026-11-18** — 四向映射产出于 `docs/audit/PRD_CAPABILITY_MAP_2026-11-18.md`（92 条逐条：已定位 68 / 未定位 24 / 有测试 47）；风险摘要见 §7 | 遗留 3 项须 owner 裁决（D3 CaseQueuePanel 未挂载 / 24 条未定位中 17 条后端能力 / 3 处零测试），见 §7 | 已关闭 |
| G3 | `EmptyState` / `Toast` / `ErrorBoundary` / `Icon` 未迁入 `primitives/`（77 处 import） | L1 原子目录不完整（功能无影响） | ✅ **已关闭 2026-11-19（B8-b）** — 4 件 + 4 个 colocated test 迁入 `primitives/`，86 处 import 在 81 个文件改指；证据见 §19.2 |
| G4 | `SentinelShell.tsx` 兼容桥（9 行）与 6 处旧路径 import 并存 | 双路径过渡态 | ✅ **已关闭 2026-11-19（B8-a）** — 6 处生产 import 全量改指 `src/shell/*`，桥物理删除，测试迁至 `shell/AppShell.test.tsx`；证据见 §19.1 |
| G5 | `src/api/settings.ts` **847 行**（B3 新建），超 §2.2「单文件 ≤300 行」 | 数据层文件超长（行为无影响；与 `api/v1.ts` 762 / `api/knowledge.ts` 572 同属历史级超长） | ✅ **已关闭 2026-11-19（B8-c）** — 847 行 → 22 行薄 barrel + 11 个子模块（最大 134 行），82 函数 + 导出类型全集零丢失，126 处消费方 import 路径不变；证据见 §19.3 |
| G6 | `hooks/useQuery.ts` 无生产消费者（仅 `useQuery.test.tsx`） | 数据层接缝已交付但未接线，B3 不计入运行时收益 | B4 首个重写区块接入 + 绑 SSE 失效 |
| G7 | **R-2 词汇表替换未完成**（DESIGN.md §5 R-2 真实范围 = StatusBadge / DataTable / 空态四态 按 §3 统一替换各域实现）：18 个文件自写 `<table>`、108 个文件自写四态、7 处域内标签未入词汇 | 全站同一概念多套实现；`primitives/DataTable` / `AsyncState` 生产消费者 = 0 | ⏸ **新登记 2026-11-19（B9）** — 分域分批推进，禁止全量机械替换（DOM 差异大）；处置建议见 §20.6，待 owner 裁决 |
| G8 | **6 件孤儿原语**：`AsyncState` / `DataTable` / `Inspector` / `Panel` / `SplitPane` / `Toolbar` 生产消费者 = 0（自 B1 建成起从未被页面消费） | 死代码 + 未落地的设计承诺；`Inspector` 与域内中心模态交互形态冲突 | ⏸ **新登记 2026-11-19（B9）** — 逐件定「落地到真实页」或「退役删除」；盘点与建议见 §20.6，待 owner 裁决 |

## 5. B3 验证证据（数据层收敛）

### 5.1 改动面

| 文件 | 变更 |
|---|---|
| `src/hooks/useQuery.ts` + `useQuery.test.tsx` | 查询工厂（`useSyncExternalStore` + 模块级 Map）：同 key 去重 / 前缀 `invalidate` / `{data,state,error,refetch}` 四态；10 tests |
| `src/api/pipeline.ts`（新建） | `getKlPipelineStats` — 仅 1 函数单列，避免壳入口为取一个端点把 `api/secnews.ts` 整包拉进首屏 chunk（实测 +732 B → 拆分后回落） |
| `src/api/settings.ts`（58 函数）/ `settingsQuality.ts`（10）/ `skills.ts`（10）/ `action.ts`（19）/ `security.ts`（7）/ `report.ts`（5） | B3 新建域模块，薄封装 `getJSON/postJSON/apiFetch`（非 2xx 仍抛 `ApiError`） |
| `src/api/knowledge.ts` / `secnews.ts` / `codegarden.ts` / `shared.ts` | 扩充端点，`listInfoFilterRules` 加泛型（修 `QualityDashboardPage` TS2345） |
| 约 56 个组件 / 16 个 hook | 改为经域模块取数；`unlockSecrets` 仍传 `role: 'admin'`（无行为变更） |
| `src/api/__tests__/domain_endpoints.test.ts`（新建） | 9 tests：锁 `report` / `security` / `skills` 的 URL + query 拼接 + method/body，任一侧改错即红 |

### 5.2 退出条件

```bash
cd frontend && grep -rn "getJSON\|postJSON\|apiFetch" \
  src/components src/routes src/hooks src/pages src/shell \
  --include='*.ts' --include='*.tsx' \
  | grep "lib/api" | grep -v "\.test\." | grep -v "ApiError\|getApiErrorMessage" | wc -l
# → 0
```

| 退出条件 | 证据 | 结果 |
|---|---|---|
| 54 处直调降为 0 | 上述命令 **0 行**（含 B2 遗留的 `src/shell/pipe.tsx`，本轮改指 `api/pipeline`） | ✅ |
| 无回归 | 四道门禁全绿 + 覆盖率高于 B2 + `nav4_shell` 守卫绿（见 §5.3 / §5.4） | ✅ |

### 5.3 四道门禁（全量）

```bash
cd frontend && npx tsc --noEmit                          # exit 0
cd frontend && npx vitest run --coverage                 # exit 0
cd frontend && npx vite build --logLevel error           # exit 0
python scripts/generate_meta.py --check                  # OK
```

- 测试：**109 文件 / 770 tests 全部通过**（B2 后 107/751 → 新增 useQuery 10 + 域端点契约 9）
- 覆盖率：Statements **58.03%** / Branches **77.13%** / Functions **58.16%** / Lines **58.03%**（基线 57.05 / 76.39 / 57.42 / 57.05；thresholds 未降）
- 首跑函数覆盖 **56.91%** 低于 57.42 门槛（域函数抽走后原组件内的覆盖随迁），已用 `domain_endpoints.test.ts` 补齐端点契约而非下调阈值
- `generate_meta --check` OK（56/19/99/155 · core_routers 67）

### 5.4 体积复测（口径同基线 §2）

| 指标 | 基线（B0） | B2 实测 | B3 实测 | 差（vs B0） |
|---|---|---|---|---|
| 首屏 JS gzip | 92,998 B | 92,835 B | **93,517 B**（index 27,691 + vendor-react 53,816 + SentinelHomePage 12,010） | **+519 B（+0.56%）** |
| 首屏 CSS gzip | 16,507 B | 16,567 B | **16,684 B**（15,323 + 1,361） | +177 B（+1.07%） |
| 全量 JS gzip | 549,589 B / 69 chunk | 548,357 B / 69 chunk | **552,383 B / 73 chunk** | +2,794 B（+0.51%） |

体积差来源：数据层模块被壳常驻 hook（`useFeatureFlags` / `useRefreshInterval` / `useFavorites` / `pipe`）静态引用，随入口 chunk 落地；`max-entries` 级联去重与 tree-shake 未覆盖该部分。**首屏 JS 相对基线略增 0.56%，属 B3 唯一负向指标**，如实登记；20% 目标仍由 B4–B6 承担（B4 起删除旧页冗余 + 懒加载分层）。

### 5.5 与契约的偏差（需 owner 知情）

| # | 契约写法 | 实际实现 | 理由 |
|---|---|---|---|
| D1 | `state ∈ loading\|success\|empty\|error` | `state ∈ loading\|ready\|empty\|error` | 与 B1 `primitives/AsyncState` 的 `AsyncStatus` 枚举对齐，避免同仓两套同义词；语义等价（`ready` ≡ `success`） |
| D2 | 域 API 落 `domains/{feed,knowledge,...}` | 落 `src/api/<domain>.ts` | 仓库已有 8 个 `api/*` 域模块（v1 / hotspots / sources / knowledge / secnews / codegarden / shared / settings），新建平行 `domains/` 会造成两套域目录 |
| D3 | 全站单一 `searchGlobal` | `searchGlobal`（全局搜索）与 `searchAll`（知识域多类型）并存 | 两者返回形状与后端端点不同，合并会改调用方行为 |
| D4 | 每端点一个函数 | `/api/skill-registry` 保留「运行/反馈」与「列表」两形状函数 | 历史双形状（`{items}` vs 数组），合并需后端统一，超出 B3 范围 |
| D5 | 域按业务域归属 | `getFederationStatus` 暂挂 `api/settings.ts` | 仅 1 处消费（设置页联邦状态卡），未单独建 `federation.ts` |

## 6. G1 关闭证据（LCP 基线实测，2026-11-18）

> 口径同契约 §7.1：生产构建 + `vite preview` + 桌面 1440×900 + Chromium 冷缓存 + 固定 API 夹具。**B6 复测必须复用同一脚本与同一夹具文件**，否则数字不可比。

### 6.1 采集脚本（新建，入仓）

| 文件 | 说明 |
|---|---|
| `frontend/perf/lcp_probe.mjs` | `capture` / `measure` 双模式；measure 每轮新建 `BrowserContext`（= 冷缓存），经 `page.route` 回放夹具；夹具未命中返回 404 `{"detail":"probe-fixture-miss"}`（缺失必须暴露，不静默走真实后端） |
| `frontend/perf/lcp-api-fixture.json` | **12 个端点（11 JSON + 1 SSE）**，157,555 B，captured_at `2026-11-17T23:17:21.158Z`；SSE 端点只记 `{sse:true}` 不读响应体，回放为 `retry: 60000` 空流 |

### 6.2 实测（B3 完成态）

```bash
cd frontend && npx vite preview --host 127.0.0.1 --port 4173 --strictPort   # 后台常驻
cd frontend && node perf/lcp_probe.mjs capture                              # 抓夹具（一次性）
cd frontend && node perf/lcp_probe.mjs measure --runs=3                     # 三轮冷缓存
```

| 轮次 | LCP | LCP 元素 |
|---|---|---|
| run1 | 276 ms | `h1.headline` |
| run2 | 252 ms | `h1.headline` |
| run3 | 236 ms | `h1.headline` |
| **中位数** | **252 ms** | — |

LCP 元素来源：[`SentinelHomePage.tsx#L648`](../../frontend/src/components/sentinel/SentinelHomePage.tsx#L648) 的 `<h1 className="headline">`。

### 6.3 口径偏差与环境事实（owner 需知情）

1. **采集时点偏差**：基线在 **B3 完成态**采集（B0 当时未采集）。B3 未改渲染路径（仅改取数入口），故可作为 B4 前基准；但严格意义上不是 B0 原始基线。
2. **LCP 由壳报头决定，不由内容区决定**：`h1.headline` 是首个大元素，252 ms 即定稿；后续内容区加载不再改变 LCP。故 §7.1 的「LCP ≤ 基线 80%」= **≤ ~201.6 ms**，仅靠删减内容区 JS 无法达成。
3. **判定为高风险项**：B6 只能在三处争取 —— 首屏关键路径 JS（`SentinelHomePage` chunk 12 KB + 壳常驻模块）、字体阻塞、报头 DOM 层级简化。若 B6 末 LCP 未达 80% 而 JS gzip 达标，按 §7.1「取 min」规则须如实判定未达标并呈报 owner，**不得改用单指标蒙混**。
4. **夹具时点**：夹具是 2026-11-17T23:17Z 的一次真实响应快照；若 B6 前夕端数据形状变化，须重新 `capture` 并**同时**用旧夹具跑一次对照，否则数字不可比。

## 7. G2 关闭证据（PRD 能力四向映射，2026-11-18）

产出文档：`docs/audit/PRD_CAPABILITY_MAP_2026-11-18.md`（未改动任何代码或其他文档）。

### 7.1 核实结论（收口时抽检）

| 项 | 结论 |
|---|---|
| 条数 | **92 条**（DATA 19 / KNOW 14 / ACT 19 / SET 15 / XF 25），与契约 §7.3 一致，无缺号；文档内映射表 92 行 + 未定位清单 24 行 = 116 行，与统计自洽 |
| 定位率 | 已定位 **68**（含 6 条「部分覆盖」：DATA-6 / DATA-10 / ACT-7 / ACT-17 / SET-5 / XF-25）；未定位 **24**；有前端测试覆盖 **47** |
| 路由对照 | 对照 `frontend/src/routes/ROUTE_REGISTRY.md` 与 `routes/index.tsx`：路由条目全部保留、无增删；2 类命名漂移（`DeepReadPage` vs `DeepReadView`、`/secnews/*` 组件名）+ 1 处状态声明冲突（D3）+ 1 处文档滞后（D4） |
| 抽检（本次独立验证） | ① `SentinelActionPage.tsx` 仅挂 `ExecOverviewPanel`（L563），确未挂 `CaseQueuePanel` ② `components/sync/` 无任何测试文件 ③ `DshControlCard.tsx` 存在但无测试 ④ `lib/interest.ts`、`lib/rejectionReasons.ts` 存在 ⑤ 文档表格行数 116 自洽 —— 均与文档一致 |

### 7.2 留给 owner 裁决的 3 项（不阻塞 B4，阻塞 B5 内容）

1. **D3 / ACT-17（高）**：`components/v1/panels/CaseQueuePanel.tsx` 有组件、有测试，但 `/action` 只挂 `ExecOverviewPanel`，完整队列实际不可达；而 `ROUTE_REGISTRY.md` 声称「P1 CaseQueue 迁入 `/action` ✅ 完成」。B5 前须裁决：**漏挂（需补挂）** 还是 **有意收敛（需更正 registry）**。
   → **✅ 已裁决并关闭（2026-11-18，契约 §0 R1）：判定漏挂，B5 已补挂 `/action` 并更正 registry**，证据见 §9.3。
2. **24 条未定位中 17 条属后端/工程纪律能力**：前端重写不承载；若重写期临时想补可见性，只能作为四菜单内区块，禁止新增一级入口。
3. **3 处零测试：SET-5（sync）/ SET-14（dsh）/ XF-15**：按「有测试=安全」推进会静默丢功能，B6 须补测试或写入显式豁免清单。
## 8. B4 验证证据（资讯域 `/`，2026-11-18）

### 8.1 改动面（9 文件，均为 `frontend/src/components/sentinel/`）

| 文件 | 行数 | 职责 |
|------|------|------|
| `SentinelHomePage.tsx` | 299 | **容器**：状态 / 取数 / 区块组合（原 808 行） |
| `feed/feedModel.ts` | 102 | 纯常量 + 纯函数（频道 / 时间窗 / `safeHref` / `relTime` / `heatOf`） |
| `feed/FeedAtoms.tsx` | 102 | 行级原子：`FeedRowBinding` / `StarButton` / `DeepReadChip` / `FlashRow` |
| `feed/UrlImport.tsx` | 66 | `POST /api/kl/import/url`（自挡非 http(s)） |
| `feed/FeedControls.tsx` | 118 | 模式条 + 检索条 |
| `feed/FeedStates.tsx` | 46 | 骨架 / 错误 / 空态 |
| `feed/FeedMustRead.tsx` | 96 | 今日必读（头条 + 次级重点） |
| `feed/FeedStream.tsx` | 192 | 精选 / 深度 / 待读（含告警） / 已读 |
| `feed/feedModel.test.ts` | 90 | 12 tests（新增） |

### 8.2 退出条件逐条

1. **首屏区块全保留** ✅ — `SentinelHomePage.test.tsx`（31 tests）原样通过，零断言改动；仅 `beforeEach` 追加 `__resetQueryCache()`（模块级缓存隔离）。覆盖：头条 `h1.headline`、今日一句话、今日必读、待读→已读递进、collect_done 三分支节流、精选/深度/告警视图、粘性 controlbar。
2. **单文件 ≤300 行** ✅ — 修复后容器 **296 行**（懒加载辅助片段抽到 `SentinelHomeAux.tsx`，26 行），其余 62–243 行；无超限文件。
3. **包体积不增** ✅（**修复后**，详见 §8.5）— 首屏 JS gzip **92,758 B**（index 27,686 + vendor-react 53,816 + SentinelHomePage 11,256），相对 B3 **93,517 B 降 −759 B / −0.81%**。修复前为 **94,857 B**（同口径复测；台账原记 94,710 B，差异来自 gzip 工具口径，见 §8.5.1），相对 B3 +1,340 B → 登记偏差 **D7**，已于 §8.5 关闭。首屏 CSS 16,831 B（+147 B，行内 style 下沉 CSS 的代价，已声明）；全量 JS 555,341 B / 75 chunk（残留项，见 §8.5.4）。
4. **G6 接线** ✅ — `useQuery('feed:quality')` + `useQuery('feed:picked', enabled: mode==='scan')` 替换手写 `loadSide` / picked effect；`useEffect(() => bindInvalidateOn(SSE_EVENTS.COLLECT_DONE, 'feed:', { throttleMs: SIDE_RELOAD_GATE_MS }), [])` 整域失效，10s 节流与 collect_done 测试期望一致；主列仍由 `useHotspotData` 3s 防抖合并。

### 8.3 门禁实测

- `npx tsc --noEmit` exit 0
- `npx vitest run --coverage` **110 文件 / 782 tests 全通过**（exit 0）；末次复跑 statements **58.16** / branches **77.36** / functions **58.39** / lines **58.16**（另一轮复跑 58.22 / 77.46 / 58.35 / 58.22；两轮均高于基线 57.05 / 76.39 / 57.42 / 57.05 与 thresholds 57.05 / 57.05 / 57.42 / 76.39）
- ⚠️ **flaky 披露（Rule 12，不隐藏）**：其中一轮全量并发跑出现 1 例超时失败 —— `SentinelHomePage.test.tsx > 赞/踩链路 (DEV-0311)`（`Test timed out in 5000ms`），同文件单跑 31/31 通过、随后全量复跑整轮通过。判据：该用例断言的是赞踩 POST/DELETE 链路，与本次改动（体积/懒加载）无因果关系；失败发生在全量并发高负载下且未复现。**结论为负载敏感型既有抖动，非本批引入**，但按「失败必须显式声明」记录于此；若 B6 复现频率升高，应单独治理（提高该用例 timeout 或减少并发）。
- `npx vite build --logLevel error` exit 0（体积见 8.2-3 与 8.5.4）
- `python scripts/generate_meta.py --check` exit 0（架构数字未变，本批为纯前端改动）

> 本节为 **2026-11-18 包体积修复批** 的复测结果；修复前的同名数字见 git history 与 §8.5.4 对照列。

### 8.4 偏差登记

- **D7（新增，负向）→ 已关闭（§8.5）**：B4「包体积不增」未达成（+1,193 B / +1.28%，台账口径），代价为 G6 `useQuery` 首次进入产物；2026-11-18 包体积修复批后首屏 JS gzip 降至 **92,758 B**（较 B3 93,517 −759 B / −0.81%）。20% 目标仍由 B6 承担（旧页删除 + 懒加载回收）。
- **D6（新增，沿用缺口）**：`PriorityDigestCard` 保留手写 fetch 未接 `useQuery` —— 其「刷新按钮发 `force=true` 请求」语义无法用现有 `useQuery` 表达（`refetch` 不携带参数），强行接入会改变行为；等 `useQuery` 支持参数化 key 时再收。

### 8.5 D7 关闭记录（2026-11-18，包体积修复批）

#### 8.5.1 口径修正（先于结论）

台账 B4 原记「首屏 JS gzip 94,710 B」用 `gzip -c` CLI 采集（含文件名头）；本批统一改用 Node `zlib.gzipSync`（level 6，与 B0 基线采集脚本同口径）：B3 复测 **93,517 B**（与台账逐字一致，口径校验通过），B4 复测 **94,857 B**（较原记 +147 B，即 CLI 头差）。**结论不变：D7 是真实回归。**

本次固化两个首屏口径（采样对象均为 `frontend/dist`）：

| 口径 | 定义 | 用途 |
|---|---|---|
| 首屏 JS（3 chunk） | `index-*.js` + `vendor-react-*.js` + `SentinelHomePage-*.js` 的 gzip 之和 | 与 B0/B3 台账可比；**D7 判定口径** |
| 首屏 eager 闭包 | 以 `dist/index.html` 的 `<script>` / `<link modulepreload>` 为种子，递归**静态** `from"..."` import 闭包（含路由 chunk） | 浏览器首屏真实下载量；含共享 chunk，排除仅被 `import()` 引用的懒加载 chunk |

两口径差异：3 chunk 口径不含路由 chunk 之外的共享 chunk（`realtime` / `ReactionButtons` / `secnews` / `v1` / `action` / `panelShell` / `useAbortGuard`），eager 闭包口径含。两者在 B4 修复前分别为 94,857 / 100,795 B。

#### 8.5.2 归因（sourcemap VLQ 逐字节归因到源文件）

| 项 | B3 | B4 修复前 | 差 |
|---|---|---|---|
| 路由 chunk 归因总量（raw） | 36,979 | 40,443 | **+3,464** |
| 其中 `hooks/useQuery`（G6 强制，首个生产消费者，此前被 tree-shake 掉） | 0 | 2,109 | +2,109（**唯一内容**） |
| 其中 feed/ 拆分胶水（8 文件 vs 1 文件） | — | +1,353 | +1,353（**重复内容**） |

**关键结论（决定修复策略）**：gzip 对**重复文本几乎免费** —— 去掉 3,637 raw 的重复内容只换来 −596 B gzip；唯一内容才按 ~0.35 的比例折算。因此本批不靠「继续去重」，而是**把唯一内容移出首屏包**。

#### 8.5.3 改动面（7 项，1 项为 `useQuery` 内部重构）

| # | 手段 | 文件 | 性质 | raw 影响 |
|---|---|---|---|---|
| 1 | `useQuery` 精简：entry 自带 `fetcher`/`isEmpty`，删旁路注册表（`fetchers`/`emptiness` 两个 Map + 3 个函数） | `hooks/useQuery.ts` | 内部重构，公共 API 与 10 tests 不变 | −260 |
| 2 | 四态面板收敛为单一 `FeedPanel`（星形 / 时钟圆环 SVG 各留一份，四处空态/错误态复用） | `feed/FeedStates.tsx` + `feed/FeedStream.tsx` | 结构去重，DOM 不变 | −745 |
| 3 | `HeatCells` / `PracticeTag` 行级原子（热度格与实践域标签原各三处重复） | `feed/FeedAtoms.tsx` | 结构去重 | −320 |
| 4 | `tagColorOf` 改复用 `CHANNEL_DEFS` 色板；箭头 path 字面量三处共用一份 `ICON_ARROW_D` | `feed/feedModel.ts` | 常量归并 | −390 |
| 5 | 静态行内 style 下沉 CSS 类（动态色值仍留行内） | `feed/FeedControls.tsx` / `FeedStream.tsx` / `FeedMustRead.tsx` / `UrlImport.tsx` + `sentinel.css` | 合规（AGENTS：行内 style 仅允许 dynamic 计算值） | JS −845 / CSS +700 |
| 6 | `NewsAlertList` 改按需加载（仅 alert 模式渲染） | `feed/FeedStream.tsx` | **行为变更**，见下 | −2,352 |
| 7 | 完整「受管信号」面板改按需加载（位于主列之后 = 首屏之下）；右栏只读摘要拆为独立模块保持**同步**加载 | `v1/panels/SignalPanel.tsx` + 新增 `v1/panels/SignalPanelCompact.tsx` + `sentinel/SentinelHomePage.tsx` | **行为变更 + API 变更**，见下 | −5,700 |
| 8 | 容器内的两处辅助片段（`RailWithPipe` / `SignalPanelLazy`）抽为独立文件 —— 否则第 7 项会把容器推过 ≤300 行硬约束 | 新增 `sentinel/SentinelHomeAux.tsx` | 结构搬家，零行为变化 | −55（仅体积口径里的归属位移） |

**行为变更声明（owner 需知情）**

1. `NewsAlertList` 与完整 `SignalPanel` 改为 `React.lazy` + `Suspense`：两者首帧渲染回退占位（`NewsAlertList` 回退与组件自身载入态 DOM 一致：`news-alert-list > na-empty`；`SignalPanel` 回退为「载入中…」）。页面级测试**零断言改动**通过（alert 用例原本就是 `waitFor` 异步断言；页面上无任何测试断言完整 `SignalPanel`）。
2. `SignalPanel` 的 `compact` prop 已移除 —— 右栏摘要迁至新模块 `SignalPanelCompact`（同一数据源 `listSignals`，DOM 与行为逐字保留）；`SignalPanel.test.tsx` 中 2 条 compact 用例改为渲染 `SignalPanelCompact`，其余断言不动。
3. 检索条的 sticky `top` 仍留行内 style（DEV-0188 契约测试断言的就是 `bars[1].style.top`，不能下沉 CSS）；其余静态布局值下沉。

#### 8.5.4 实测（`node zlib.gzipSync`，同机同命令）

| 口径 | B0 基线 | B3 | B4 修复前 | B4 修复后 | vs B3 |
|---|---|---|---|---|---|
| 首屏 JS（3 chunk，D7 判定口径） | 92,998 | 93,517 | 94,857 | **92,758** | **−759 / −0.81%** |
| 首屏 eager 闭包 | — | 99,379 | 100,795 | **98,532** | **−847 / −0.85%** |
| 首屏 CSS | 16,507 | 16,684 | 16,605 | 16,831 | +147 |
| 全量 JS / chunk 数 | 549,589 / 69 | 552,383 / 73 | 554,417 / 73 | 555,341 / 75 | +2,958 / +2 chunk |

**残留（不隐藏）**

- **全量 JS 555,341 B / 75 chunk**（较 B3 +2,958 B）：其中 **+924 B 是 2 个懒加载 chunk 的边界开销**（同一份代码拆成独立 chunk 后各自带一份压缩字典与 import 样板，代码体积本身未增），另 +2,109 raw 是 G6 强制的 `useQuery` 实体化。**留给 B6（旧页删除 + 懒加载回收）**。
- **首屏 CSS +147 B**（较 B3）：行内 style 下沉 CSS 的代价；JS 侧省下的更多，首屏 JS+CSS 合计较 B3 净 −594 B。
- **LCP 未复测**：基线本身仍未采集（§2.4 缺口），本次新增 2 处 Suspense，**不得声称 LCP 未受影响**。

## 9. B5 验证证据（知识域图谱 + 行动域，2026-11-18）

> 本批性质 = **结构性拆分 + R1 补挂**，非视觉重做、非数据层重写。DOM / class / `data-testid` / aria 文案逐字保留，因此页面级测试可零断言通过。取数逻辑原样搬运，**本批未接入 `hooks/useQuery`**（接线风险由 owner 另批裁决）。

### 9.1 改动面（12 个新建 + 3 个容器改写，均在 `frontend/src/components/sentinel/`）

| 原文件 | 原行数 | 现行数 | 拆出 |
|---|---|---|---|
| `SentinelGraphPage.tsx` | 766 | **288** | `graph/graphModel.ts` 250 · `graph/GraphSide.tsx` 157 · `graph/GraphCanvas.tsx` 108 · `graph/GraphSvg.tsx` 107 · `graph/GraphFilters.tsx` 59 |
| `SentinelActionPage.tsx` | 576 | **284** | `action/ReviewStackPanel.tsx` 160 · `action/JudgingQueuePanel.tsx` 123 · `action/actionModel.ts` 119 · `action/ActionFloorHeader.tsx` 32 |
| `action/RunStage.tsx` | 333 | **109** | `action/RunActionRow.tsx` 191 · `action/RunFinishForm.tsx` 78 · `action/runStageModel.ts` 70 |

15 个非测试文件（12 新建 + 3 改写）全部 ≤300 行；最大 288。`RunStage` 导出名与 props 签名逐字未变，消费方 `ActionCommandConsole.tsx`（L27 import / L208 使用）与 `stages.test.tsx` 零改动。

### 9.2 守卫处理（走了「优先方案」，未放宽任何断言）

`nav4_shell.test.tsx` 有两条**源码文本守卫**直读 `SentinelGraphPage.tsx`（画布模式开关 + `InfiniteCanvas` import）。实测三要素全部仍在容器内，**守卫文件一字未改**：

| 守卫断言 | 现位置 | 状态 |
|---|---|---|
| `const [canvasMode, setCanvasMode] = useState(false)` | `SentinelGraphPage.tsx` L59 | 字面写法未变（未加泛型、未改名） |
| `from '../shared/editorial/InfiniteCanvas'` | `SentinelGraphPage.tsx` L36 | import 留容器 |
| `画布模式`（中文文案） | L58 / L60 / L191 | 在 |
| `SentinelActionPage.tsx` 含 `layer="action"`（守卫 L116） | `SentinelActionPage.tsx` L223 | 在 |

`SentinelGraphPage.test.tsx`（389 行 / 13 处渲染断言 + 画布模式 describe）**零改动**；`stages.test.tsx`、`ActionCommandConsole.test.tsx`、`PlanPanel.test.tsx`、`ApprovalInbox.test.tsx`、`CopilotCards.test.tsx` 均零改动。

### 9.3 R1（CaseQueuePanel 补挂）关闭证据

- 挂载点：`SentinelActionPage.tsx` L268 `<CaseQueuePanel />`，位于 `<ApprovalInbox />` 之后、`<ExecOverviewPanel />` 之前（队列含 `blocked`，总览不含，二者互补）；L27/L43 为裁决注释与 import。
- `CaseQueuePanel.tsx`（103 行）本体与其测试**未改动**。
- 新增守卫：`SentinelActionPage.test.tsx` **追加** 1 条用例（断言 `/action` 渲染出队列 DOM）。已做负向验证 —— 临时删除该行时该用例失败（`expected null not to be null`），恢复后通过；用例数 782 → **783**。
- `ROUTE_REGISTRY.md` 的「P1 CaseQueue 迁入 /action ✅ 完成 (2026-09-13)」不实表述已更正。

### 9.4 门禁实测（原始数字）

```bash
cd frontend && npx tsc --noEmit                     # exit 0
cd frontend && npx vitest run --coverage            # 见下（含 1 例 flaky，复跑全绿）
cd frontend && npx vite build --logLevel error      # exit 0
python scripts/generate_meta.py --check             # OK (56/19/99/155 · core_routers 67) · AGENTS 7/7
```

- 覆盖率 **58.38 / 77.48 / 58.82 / 58.38**（Stmts/Branch/Funcs/Lines），高于 B4 态 58.16 / 77.36 / 58.39 / 58.16 与 B0 基线 57.05 / 76.39 / 57.42 / 57.05，thresholds 未下调。
- 组件层直调 grep（`getJSON|postJSON|apiFetch` → `lib/api`）**0 行**，B3 成果保持。
- ⚠️ **flaky 披露（同 DEV-0396 型）**：全量并发首跑出现 **1 例失败** `components/settings/OpsRunsPanel.test.tsx` L42（断言 `失败 1` 时页面仍停在「载入中…」）。判定依据：① 单跑该文件 **5/5 通过** ② 该文件自 `7f65f1a`（B0–B3）后**零改动**，B5 未触碰设置域 ③ 全量复跑 **110 文件 / 783 tests 全通过**。结论 = 负载敏感型既有抖动，非本批引入；设置域抖动治理并入 B6。

### 9.5 体积与偏差（负向项，如实登记）

| 口径 | B4 收口（D7 后） | B5 实测 | 差 |
|---|---|---|---|
| 首屏 JS（3 chunk 判定口径） | 92,758 B | **92,772 B**（index 27,697 + vendor-react 53,816 + SentinelHomePage 11,259） | **+14 B** |
| 全量 JS / chunk 数 | 555,341 B / 75 | **556,845 B / 75** | +1,504 B / chunk 持平 |

- **偏差 D8（新增，负向）**：B5 退出条件 3「包体积不增」严格未达成 —— 首屏 JS **+14 B（+0.015%）**。归因：新增 12 个模块使入口 chunk 的模块 id 与图序位移，entry +11 B、页 chunk +3 B；无新依赖、无新增首屏代码路径（`/action` 与 `/knowledge/graph` 均为 lazy 路由，CaseQueuePanel 落进行动域 chunk）。量级在 gzip 噪声内，但按纪律登记为偏差，**不声称达标**。

- **B5 范围（已由 owner 裁决为 12 文件）**：契约 §6 的 B5 原文是「知识域 + 行动域重写」，本轮按 owner 两次裁决执行「点名三超限 + 续拆剩余 9 个」共 12 个文件；域内其余超限项见 §10.4 残留清单。

## 10. B5 续拆验证证据（owner 裁决「续拆剩余 9 个」，2026-11-18）

> 同 §9 性质：结构性拆分，DOM/class/`data-testid`/aria 逐字保留，取数原样搬运，未接 `useQuery`。5 路子任务并行执行，**所有数字由主会话在合并态统一复测**（子任务自验仅为局部快照）。

### 10.1 改动面（38 新建 + 9 容器改写）

| 原文件 | 原行数 | 现行数 | 拆出 |
|---|---|---|---|
| `v1/CaseDetail.tsx` | 784 | **226** | `caseDetail/` 10 件：ActionsSection 206 / `useCaseDetailMutations.ts` 205 / KnowledgeSection 94 / JudgmentsSection 92 / CaseDetailHeader 69 / RecallKnowledgeSection 56 / EvidenceSection 42 / caseDetailModel 35 / WalkthroughPathsCard 29 / CaseBadge 22 |
| `knowledge/ReviewMode.tsx` | 658 | **190** | `knowledge/review/` 5 件：ReviewFlipCard 234 / ReviewStates 100 / ReviewComplete 85 / reviewModel 58 / ReviewHeader 29 |
| `knowledge/KnowledgeImport.tsx` | 538 | **234** | `knowledge/import/` 5 件：SourceCards 156 / CuboxImportCard 111 / ImportStatusBar 77 / ImportHero 45 / importModel 40 |
| `knowledge/KnowledgeCompoundingDashboard.tsx` | 534 | **110** | CompoundingCards 246 / compoundingDashboardModel 234 / CompoundingStates 80 |
| `knowledge/DeepReadMode.tsx` | 503 | **196** | DeepReadArticle 178 / DeepReadSidebar 126 / DeepReadHeader 52 / deepReadModeModel 33 |
| `sentinel/review/ReviewOverlay.tsx` | 584 | **91** | ReviewSessionView 175 / ReviewManageView 165 / reviewModel 102 / ReviewDataView 90 |
| `action/ApprovalInbox.tsx` | 449 | **149** | ApprovalDraftCard 231 / ApprovalFailedList 57 / approvalModel 46 / ApprovalBadge 18 |
| `knowledge/KnowledgePlanningPanel.tsx` | 388 | **173** | PlanningActionCard 183 / planningModel 69 |
| `knowledge/AttentionHeatmap.tsx` | 358 | **153** | AttentionHeatmapGrid 178 / attentionModel 91 |

38 个新建非测试文件最大 246 行，**全部 ≤300**；9 个容器最大 234 行。

### 10.2 契约保持点（子任务声明 + 主会话复核）

- **导出名与文件路径全部不变**；`ReviewOverlay` 以 `export type { RvView }` 再导出、`CaseDetail` 以 `export { Badge }` 再导出，消费方（`SentinelActionPage` / `ReviewStackPanel` / `V1Prototype`）import 路径未改。
- **R19.1 N+1 契约**：`CaseDetail` 拆分后 `getCaseAggregate` 仍只在容器调用一处，`getCase/listJudgments/listActions/listRuns/listArtifacts` 零调用；`c11_aggregate_and_sse.test.tsx` **未改一行**并通过（主会话全量复测含该文件）。
- **echarts 单一入口**：新增区块文件**零新增 echarts import**，图表仍经 `shared/EChart` 统一入口（契约 §2.1 硬规则 4）。
- **测试文件零改动**：`git status` 复核 —— 本组 9 个改动文件全为 `M` 源码，**无任何测试文件出现在改动集中**（不同于 §9.3 的追加用例，本组连追加都没有）。

### 10.3 门禁实测（合并态统一复测）

```bash
cd frontend && npx tsc --noEmit                  # exit 0（全仓，非局部快照）
cd frontend && npx vitest run --coverage         # 110 文件 / 783 tests 全通过
cd frontend && npx vite build --logLevel error   # exit 0
python scripts/generate_meta.py --check          # OK · AGENTS 7/7
```

- 覆盖率 **58.61 / 77.58 / 59.59 / 58.61**（Stmts/Branch/Funcs/Lines）—— 高于 B5 首批 58.38/77.48/58.82/58.38、B4 态 58.16/77.36/58.39/58.16 与 B0 基线 57.05/76.39/57.42/57.05；阈值未下调。
- 本轮全量并发跑 **0 失败**（§9.4 的 `OpsRunsPanel` flaky 未复现，仍按既有抖动登记）。
- 体积：首屏 JS 口径 A **92,776 B**（index 27,702 + vendor-react 53,816 + SentinelHomePage 11,258）；入口 CSS 15,470 B；全量 JS **558,524 B / 75 chunk**。
  - 较 B5 首批 92,772 **+4 B**；较 D7 收口 92,758 累计 **+18 B / +0.019%**（D8 仍在，未扩大）。
  - 全量较首批 +1,679 B、较 D7 累计 +3,183 B，chunk 数保持 75（拆分只改源码结构，未新增路由 chunk）。
  - 归因：38 个新模块进入各自路由 chunk 的图序与 import 样板；首屏两域均为 lazy 路由，**不影响首屏关键路径**。

### 10.4 B5 残留（不隐藏；建议并入 B6 或另开 B5.6）

owner 裁决范围为「9 个续拆项」，已全部完成。但按契约 §6「知识域 + 行动域重写」与 §2.1 全站硬规则，两域内**仍有超限文件未拆**：

| 域 | 文件 | 行数 |
|---|---|---|
| 行动 | `components/events/EventsReviewPage.tsx`（`/action/events`） | 341 |
| 行动 | `components/report/WeeklyReport.tsx` / `MonthlyReport.tsx`（`/report`） | 369 / 368 |
| 知识 | `components/skills/SkillBuilder.tsx`（`/skill-store/new`） | 552 |
| 知识 | `components/reader/DeepReaderPage.tsx`（`/reader/:id`，**被源码守卫直读**） | 495 |
| 知识 | `components/dashboard/Dashboard.tsx`（`/dashboard`） | 341 |
| 归属待确认 | `components/shared/NoteEditor.tsx` | 334 |

> **本表 7 项已于 2026-11-18 由 B5.6 全部拆分达标**（`NoteEditor` 归属确认为知识域 = 消费方 `ReviewPage` `/reviews`），证据见 §11.1；R3 契约冲突已裁决关闭，见 §11.3。

另：契约 §2.3「保留物」里的契约层文件仍超长（`contexts/I18nContext.tsx` 957 / `types/index.ts` 907 / `api/settings.ts` 847（= G5）/ `api/v1.ts` 762 / `api/knowledge.ts` 572 / `types/codegarden.ts` 453 / `api/secnews.ts` 420 / `api/codegarden.ts` 375 / `hooks/realtime.ts` 315），这些属**类型与 API 契约层**，§2.1 的 ≤300 行规则与 §2.3 保留条款本身相冲突，需要 owner 明确豁免口径，不由实现侧自行决定。

> **该冲突已于 2026-11-18 由 R3 裁决关闭**（见 §11.3），口径 = **按文件类别分层豁免，非全站豁免**。

## 11. B5.6 验证证据（7 个剩余超限文件 + R3 契约冲突裁决，2026-11-18）

> owner 裁决「先处理那 7 个超限文件和契约冲突的裁决」。同 §9/§10 性质：结构性拆分，DOM/class/`data-testid`/aria 逐字保留，取数原样搬运，未接 `useQuery`。3 路并行子任务，**所有数字由主会话在合并态统一复测**。

### 11.1 改动面（28 新建 + 7 容器改写）

| 原文件 | 原行数 | 现行数 | 拆出 |
|---|---|---|---|
| `skills/SkillBuilder.tsx` | 552 | **176** | `skills/` 8 件：SkillBuilderStep1Form 124 / SkillBuilderSchemaEditor 90 / skillBuilderModel 69 / SkillBuilderNavBar 61 / Step3Form 76 / Step2Form 58 / SkillBuilderStepper 42 / Step4Form 24 |
| `reader/DeepReaderPage.tsx` | 495 | **202** | `reader/` 5 件：deepReaderModel 161 / DeepReaderMarkdown 113 / DeepReaderComposer 58 / DeepReaderRail 58 / DeepReaderArticle 41 |
| `events/EventsReviewPage.tsx` | 341 | **216** | EventsReviewBlocks 223 / eventsReviewModel 37 |
| `dashboard/Dashboard.tsx` | 341 | **110** | dashboardModel 83 / SkillMatrix 76 / HealthCard 59 / TriggerTimeline 55 |
| `report/WeeklyReport.tsx` | 369 | **146** | WeeklyReportBlocks 212 / WeeklyReportHighlights 91 / sharedBlocks 90（周/月共用） |
| `report/MonthlyReport.tsx` | 368 | **138** | MonthlyReportBlocks 222 / MonthlyReportHighlights 93 |
| `shared/NoteEditor.tsx` | 334 | **155** | noteEditorModel 148（内联 style 常量）/ NoteEditorList 101 / NoteEditorComposer 44 |

28 个新建非测试文件最大 **223** 行、7 个容器最大 **216** 行，全部 ≤300。导出名与文件路径全部不变（`WeeklyReportContent` / `MonthlyReport` / `DeepReaderPage` / `NoteEditor` / `SkillBuilder` / `Dashboard` / `EventsReviewPage`）。

### 11.2 守卫保持（本批最高风险项）

`nav4_shell.test.tsx` 有三条断言涉及本批文件，**守卫文件未改**，实测：

| 守卫断言 | 实测 |
|---|---|
| 「5 个视图组件文件存在且带 colocated test」：`src/components/events/EventsReviewPage.tsx` + 同名 `.test.tsx`、`src/components/reader/DeepReaderPage.tsx` + 同名 `.test.tsx` 均可读 | ✅ 两个容器**原地保留为同名文件**，test 文件原位原名未动 |
| 「5 视图不得自嵌 SentinelShell」：5 文件源码 `not.toContain("SentinelShell")` | ✅ `EventsReviewPage.tsx` / `DeepReaderPage.tsx` grep 计数 = **0** |
| 「未实现端点 TODO 全部闭环」：`DeepReaderPage.tsx` `not.toContain("backend not implemented")` | ✅ grep 计数 = **0** |

另：`EventsReviewPage` / `DeepReaderPage` / `NoteEditor` 的既有测试（`EventsReviewPage.test.tsx` / `DeepReaderPage.test.tsx` / `ReviewPage.test.tsx`）**一行未改**并通过；`SkillBuilder.test.tsx` / `Dashboard.test.tsx` 一行未改并通过。

### 11.3 R3 裁决（§2.1 硬规则 3 与 §2.3 保留物冲突）—— 关闭

**冲突事实**（实测，非印象）：

| 文件 | 行数 | 内部结构（实测计数） |
|---|---|---|
| `contexts/I18nContext.tsx` | 957 | 词条表 + 3 个 interface；**长度来自声明式内容** |
| `types/index.ts` | 907 | 81 个 interface/type，**569 行纯类型声明**，仅 7 个导出函数 |
| `api/settings.ts` | 847 | 82 个端点函数（每函数 1 端点） |
| `api/v1.ts` | 762 | 35 端点 + 56 interface |
| `api/knowledge.ts` | 572 | 47 端点 + 17 interface |
| `types/codegarden.ts` | 453 | 45 interface，**338 行纯类型** |
| `api/secnews.ts` | 420 | 36 端点 + 22 interface |
| `api/codegarden.ts` | 375 | 35 端点 + 14 interface |
| `hooks/realtime.ts` | 315 | SSE 事件契约（§2.3 明列保留） |

**裁决口径（§0 R3）**：**按文件类别分层豁免，非全站豁免**

1. **契约层豁免**（`types/`、`api/`、`contexts/`、`lib/`、`hooks/realtime.ts`）：不适用 ≤300 行，改为**按文件职责拆分**。理由：这些文件的长度来自**声明式契约**（端点函数 1:1、类型声明），硬拆会把类型定义切碎、破坏 §2.3「契约层不重写」与 §2.1 硬规则 2（跨域 import 出口）。
2. **组件层零豁免**：`components/` / `pages/` / `primitives/` / `shell/` 下的任何文件一律 ≤300 行。当前**组件层剩余 17 件全部归 B6 拆**，不得以「历史遗留」留存：
   `MaintPage` 522 · `settings/DatabaseMaintenance` 470 · `ItemDetailDialog` 453 · `DeepReadPage` 428 · `settings/quality/SecretsPanel` 427 · `v1/V1Prototype` 411 · `HistoryPage` 407 · `layout/LayerCard` 385 · `TodoItem` 376 · `secnews/settings/InfoFilterCard` 375 · `settings/quality/CustomRulesPanel` 348 · `settings/ModelPoolPanel` 341 · `settings/ContentPreferencesCard` 335 · `settings/ProxySettings` 328 · `secrets/SecretsPage` 320 · `settings/SettingsDashboard` 311 · `secnews/settings/DshControlCard` 303。
3. **豁免清单逐条可查**，已写入契约 §2.1 硬规则 3 脚注 + §0 R3 行，不静默绕过。

**豁免的例外**：`api/settings.ts` 847 行虽在豁免目录，但它是 B3 新建而非历史契约，且已登记缺口 **G5**（§4）—— G5 仍有效，B6 设置域重写时按子域拆分，**不因 R3 豁免而关闭 G5**。

### 11.4 门禁实测（合并态统一复测）

```bash
cd frontend && npx tsc --noEmit                  # exit 0（全仓）
cd frontend && npx vitest run --coverage         # 110 文件 / 783 tests 全通过
cd frontend && npx vite build --logLevel error   # exit 0
python scripts/generate_meta.py --check          # OK · AGENTS 7/7
```

- 覆盖率 **58.64 / 77.50 / 59.97 / 58.64**（Stmts/Branch/Funcs/Lines）—— 高于 B5 续拆批 58.61/77.58/59.59/58.61 与 B0 基线；阈值未下调。
- 体积：首屏 JS 口径 A **92,770 B**（index 27,697 + vendor-react 53,816 + SentinelHomePage 11,257）—— 较 B5 续拆批 92,776 **−6 B**，较 D7 收口 92,758 累计 **+12 B / +0.013%**（D8 未扩大，且本批已回落 6 B）。入口 CSS 未变；全量 JS **559,813 B / 75 chunk**（+1,289 B，chunk 数持平）。

### 11.5 残留

① 组件层 17 件超限归 B6（R3 组件层零豁免，已登记契约 §6）；② `api/settings.ts` G5 仍有效；③ LCP 仍未复测（**已由 B5.5 关闭，见 §12**）；④ `NoteEditor` 仍物理位于 `components/shared/`（消费方 `ReviewPage` 在知识域），迁移需改 import，本批未做。

## 12. B5.5 首屏瘦身专项验证证据（2026-11-18）

> owner 裁决「开始 B5.5 首屏瘦身专项」，并在过程中两项裁决：**i18n 按 locale 动态加载**、**口径降级为 LCP 单指标（R4）**。方法论：**归因先行**（R2 遗留的 JS 口径问题必须先量化到源文件，再决定动哪里）。

### 12.1 归因工具入仓（先量化，后动手）

| 工具 | 作用 | 关键实现 |
|---|---|---|
| `frontend/perf/chunk_attrib.mjs` | 把产物 chunk 字节归因到源文件 | 解析 sourcemap + VLQ 解码；**必须按 `genCol` 区间切分**——产物 minify 后整块只有 1–3 行，行级归因会把整个 chunk 记给第一个 source（首跑即复现该错误：入口 chunk 82,963 B 全记给 `react-jsx-runtime`） |
| `frontend/perf/lcp_ab.mjs` | LCP A/B 对照（留字体 / 拦字体） | `PerformanceObserver` + `getEntries()`；`waitUntil: 'load'` + try/catch 容错（load 超时后仍读已发生的 LCP） |
| `frontend/perf/lcp_diag.mjs` | 诊断 `load` 事件超时是否由外部字体 stylesheet 阻塞 | 路由拦截 `fonts.googleapis.com` 后对比 load 耗时 |

三个脚本均入仓（可复用；B6 复测必须同脚本同夹具）。

**归因结论（实测 raw 字节）**：

| 项 | 字节 | 占比 |
|---|---|---|
| 入口 chunk `index-*.js` | 77,505 raw / 27,697 gzip | — |
| └ `contexts/I18nContext.tsx` | **33,937 raw** | **入口 chunk 43.8%** |
| └ 两份词条表 gzip 合计 | **13,770 B**（zh 7,329 + en 6,441） | 入口 chunk 的一半 |
| `vendor-react-*.js` | 53,816 gzip | 其中 `react-dom` 占 **79.1%**（不可压缩运行时） |

→ 首屏 JS 侧唯一可动的大项是 **en-US 词条表**（默认语种 zh-CN 必须常驻：既是默认语种又是跨语种 fallback 源）。

### 12.2 改动一：Google Fonts 改非阻塞（LCP 主抓手）

`frontend/index.html` 的字体 `<link rel="stylesheet">` 是**渲染阻塞资源**，且指向外部 CDN。A/B 实测（5 轮，同夹具同视口）：

| 组 | LCP 样本（ms） | 中位 | 区间 |
|---|---|---|---|
| 留字体（原状） | 0 / 7,556 / 492 / 224 / 448 | **448** | [0, 7,556] —— **方差 7.5 s** |
| 拦字体 | 120 / 120 / 124 / 116 / 100 | **120** | [100, 124] —— 方差 ±24 ms |

`lcp_diag.mjs` 佐证：拦字体后 `load` 仅 16 ms，不拦 206 ms（另两次直接 30 s 超时）。

**修复**：`media="print"` + `onload="this.media='all'"` + `<noscript>` 回退同步 `<link>`。字体不再阻塞首屏渲染，慢/不可达时退化为系统字体（同时修掉一个**生产级单点故障**：字体 CDN 慢时首屏会挂起数秒）。

**修复后 5 轮实测**：`[124, 136, 148, 128, 108]` → **中位 128 ms**，区间 [108, 148]（方差 40 ms）。

| 判定项（R4 后唯一指标） | 基线 | 目标 | 实测 | 结论 |
|---|---|---|---|---|
| LCP 中位数 | 252 ms | ≤ 201.6 ms（80%） | **128 ms** | **达标** |

> 基线口径修订：原 252 ms 采于字体 CDN 恰好快响应的偶然条件，**不代表常态**（常态是 448 ms 中位、7.5 s 尾部）。已写入契约 §7.1，B6 复测须记录「带字体 / 不带字体」两组以区分代码回归与网络抖动。

### 12.3 改动二：i18n 词条按 locale 动态加载

`contexts/I18nContext.tsx` **957 → 131 行**，两份词条表外移：

| 文件 | 行数 | keys |
|---|---|---|
| `lib/i18n/messages.zh-CN.ts` | 426 | 390 |
| `lib/i18n/messages.en-US.ts` | 426 | 389（原文件本就少 1 条，**未"修正"**） |
| `lib/i18n/index.ts` | 18 | 导出 zh 静态表 + `loadEnUSMessages()` 动态 `import()` |

**等价性校验**：区间切分脚本逐条比对 **779 个 key 的 key + value，全等 PASS**（zh 390 + en 389）。zh-CN 静态常驻（默认语种 + 跨语种 fallback 源），en-US 拆成独立 chunk `messages.en-US-*.js` = **5,926 B gzip**，仅 locale=en-US 时发起请求。

**行为变更登记（不隐藏）**：
1. 英文用户**首帧**会短暂显示 zh-CN 词条（约 1 帧），en-US chunk 到达后切回 —— 已由 owner 裁决接受，测试改 `waitFor` 而非改语义。
2. 测试改动共 **9 例**（`I18nContext.test.tsx` 5 + `Dashboard.test.tsx` 4），全部为「加 `async` + `waitFor`」，**断言目标文案逐字不变**（`'Skill Dashboard'` / `'14/14','12/20','0','OK'` / `'Enabled'` / `'Disabled'` / 切换后文案必须不同）。

### 12.4 门禁实测

```bash
cd frontend && npx tsc --noEmit                  # exit 0
cd frontend && npx vitest run --coverage         # 110 文件 / 783 tests 全通过
cd frontend && npx vite build --logLevel error   # exit 0
python scripts/generate_meta.py --check          # OK · AGENTS 7/7
```

- 覆盖率（两次实测）**58.75 / 77.67 / 59.95 / 58.75** 与 **58.73 / 77.64 / 60.00 / 58.73**（Stmts/Branch/Funcs/Lines）—— 均高于 B5.6 的 58.64/77.50/59.97/58.64 与 B0 基线，阈值未下调；两次差异 ≤0.05 来自异步用例（`waitFor`）的时序抖动，非覆盖率回退。

### 12.5 体积（观测项，R4 后不阻断但不得高于基线）

| 指标 | B5.6 | **B5.5** | 变化 |
|---|---|---|---|
| 首屏 JS 口径 A | 92,770 B | **88,279 B** | **−4,491 B / −4.8%** |
| 入口 chunk | 27,697 | 23,208 | −4,489 |
| vendor-react | 53,816 | 53,816 | 0（不可压缩） |
| SentinelHomePage | 11,257 | 11,255 | −2 |
| 入口 CSS | 15,470 | 15,470 | 0 |
| 全量 JS / chunk 数 | 559,813 / 75 | 561,200 / **76** | +1,387（= en-US 独立 chunk 5,926 − 入口内词条 4,489） |

较 B0 基线 92,998 **累计 −4,719 B** —— **首次低于基线**（此前各批均在基线之上）。

### 12.6 残留与后续

① LCP 已达标但**基线口径本身不可信**（见 §12.2 注），B6 最终判定须带/不带字体各测一组；
② `perf/lcp_*.mjs` 依赖 Playwright 与本地 `vite preview`，**未纳入 CI**（CI 无浏览器），为人工复测工具；
③ en-US 首帧中文为中英双语用户的已知行为变更，若需消除可改为「首帧按 `navigator.language` 预判 + 阻塞首帧」，但会回退 LCP 收益，当前不做。

## 13. B6-b 设置域 /settings 验证证据（2026-11-18）

> B6 拆四子批（a 组件层超限 / b 设置域 / c 工具页容器 / d 旧 CSS 收尾），owner 裁决**从 b 起**。旧三份 CSS（`sentinel.css` / `sentinel-action.css` / `sentinel-graph.css`）处置口径由 owner 定为「按业务流和逻辑重构，打破壳层硬性」，属 **B6-d** 范畴，本批不执行。

### 13.1 改动一：侧边栏 IA 按业务流重排（数据进来 → AI 加工 → 系统维护）

`settings/sections.tsx` **107 → 114 行**，5 组（含无名的 overview + c8 遗留两组）重划为 **3 个业务流组 + 无名总览**：

| 组键 | 标签 | 归属段 | 判定依据 |
|---|---|---|---|
| `overview` | （不设标题） | `overview` | 首屏体检入口，不需要分组标题 |
| `ingest` | 数据接入 | `collection` / `network` | 数据怎么进来（采集/质量/信源/代理） |
| `intelligence` | AI 与偏好 | `models` / `general` | 进来之后 AI 怎么加工、界面怎么呈现 |
| `system` | 系统与运维 | `connectivity` / `ops` | 系统自身状态（同步/MCP/凭据/维护/导出/进程启停） |

- `SECTIONS` 声明顺序同步改为 `overview → collection → network → models → general → connectivity → ops`（与业务流顺序一致）。
- **深链零破坏**：`cat` 键不变，`SettingsPage` 的 `?cat=` 校验逻辑（`SECTIONS.some(s => s.key === catParam)`）无需任何映射。
- **两处语义纠错**（原归属与内容不符）：`general`（主题/模式/兴趣/能力开关）原挂「管道与门控」→ 现 `intelligence`；`connectivity`（同步/MCP/主密钥）原挂「数据源」→ 现 `system`。

### 13.2 改动二：9 件超限文件拆分（settings 域超限清零）

| 原文件 | 原行数 | 现行数 | 新增文件（行数） |
|---|---|---|---|
| `settings/DatabaseMaintenance.tsx` | 470 | **216** | `.types.ts` 15 / `Status.tsx` 98 / `Actions.tsx` 95 / `DangerZone.tsx` 138 / `Duplicates.tsx` 85 |
| `settings/quality/SecretsPanel.tsx` | 427 | **282** | `Table.tsx` 46 / `KeyModals.tsx` 97 / `Form.tsx` 101 / `.types.ts` 15 |
| `secnews/settings/InfoFilterCard.tsx` | 375 | **217** | `infoFilter.types.ts` 15 / `InfoFilterAddForm.tsx` 124 / `InfoFilterRuleList.tsx` 70 / `InfoFilterPreview.tsx` 87 |
| `settings/quality/CustomRulesPanel.tsx` | 348 | **233** | `.types.ts` 58 / `Form.tsx` 77 / `DryRun.tsx` 27 |
| `settings/ModelPoolPanel.tsx` | 341 | **239** | `ModelPoolPanelParts.tsx` 150 |
| `settings/ContentPreferencesCard.tsx` | 335 | **274** | `ContentPreferencesCardParts.tsx` 75 |
| `settings/ProxySettings.tsx` | 328 | **181** | `ProxySettingsParts.tsx` 222 |
| `settings/SettingsDashboard.tsx` | 311 | **231** | `.types.ts` 63 / `.format.ts` 28 |
| `secnews/settings/DshControlCard.tsx` | 303 | **223** | `DshControlCardHeader.tsx` 92 / `DshControlCardGateOff.tsx` 40 / `dshControlCard.types.ts` 5 |

- 全部导出签名（named + default）保持不变，`SettingsPage.tsx` **零改动**；20 个新文件全部 ≤300 行，最大 282 行。
- **settings 域超限文件数：17 → 0**（B4/B5 遗留的 8 件属 `settings/*` 之外的组件层，仍归 B6-a）。

### 13.3 测试口径变更（显式登记，不隐藏）

`settings/sections.test.ts` 原断言「5 组标签 + 旧组键归属」，随 IA 重排必然失败（实测 2 例红）。处理原则（Rule 9）：该测试编码的是**导航分组这一产品契约**，owner 已裁决新契约，故**更新测试到新契约**而不是回滚 IA。改写后 3 例：

1. 分组标题固定为三组（`数据接入` / `AI 与偏好` / `系统与运维`）；
2. 每段必须归属三组之一，除 `overview` 外不得挂到无标题组（否则导航里看不到入口）；
3. 关键能力归属：`collection`/`network` → `ingest`，`models`/`general` → `intelligence`，`connectivity`/`ops` → `system`。

### 13.4 门禁实测

```bash
cd frontend && npx tsc --noEmit                  # exit 0
cd frontend && npx vitest run                    # 110 文件 / 783 tests 全通过
cd frontend && npx vitest run --coverage         # 58.92 / 77.61 / 60.61 / 58.92 (Stmts/Branch/Funcs/Lines)
cd frontend && npx vite build --logLevel error   # exit 0
python scripts/generate_meta.py --check          # OK
```

- 覆盖率 vs `vite.config.ts` 阈值（B0 基线 lines/statements 57.05 · functions 57.42 · branches 76.39）：**四项全部高于阈值**（+1.87 / +1.22 / +3.19 / +1.87 pp）。
- 登记一处**轻微回落**：Branch 77.61 比 B5.5 的 77.67 **−0.06pp**。归因为拆分后在子组件内新增了提前返回 / 空态分支（分母增大而实测分支未同步覆盖），非覆盖率门槛回退；仍高于阈值 1.22pp。

### 13.5 体积（观测项）

| 指标 | B5.5 | **B6-b** | 变化 |
|---|---|---|---|
| 首屏 JS 口径 A | 88,279 B | **88,292 B** | **+13 B / +0.015%** |
| 入口 chunk | 23,208 | 23,219 | +11 |
| vendor-react | 53,816 | 53,816 | 0 |
| SentinelHomePage | 11,255 | 11,257 | +2 |
| 全量 JS / chunk 数 | 561,200 / 76 | 562,455 / 76 | +1,255（settings 域拆分产物，懒加载 chunk 数不变） |

较 B0 基线 92,998 仍**累计 −4,706 B**。`SettingsPage` 为路由级懒加载 chunk，本批拆分只影响该 chunk 内部构成，不进入首屏。

### 13.6 未做与残留（显式声明）

① **`settings-shell.css` 未去 `.settings-shell` 前缀、未删 `--sn-*` 别名层**。理由三条：它是设置域自身样式（由 `SettingsPage.tsx` import），不是壳层样式；`st-*` 原子实测**无跨域碰撞**（全仓 settings 域外唯一使用者是 `components/shared/editorial/Stamp.tsx`，其类是 `st` / `st-mint` / `st-amber` / `st-red` / `st-ink` / `st-solid` / `st-outline` / `st-lg`，与 `st-btn`/`st-card`/`st-chip`/`st-rule`/`st-cell`/`st-sidenav`/`st-head` **零重叠**）；去前缀属全站原子统一动作，与本批「零视觉变更」目标冲突，留给 **B6-d** 一次做完。
② `SettingsDashboard` 的 `QUICK_JUMPS` 是硬编码字面量，其顺序与新侧边栏顺序（collection 在 network 之前）不完全一致。本批要求零 DOM 变更，未动；登记为轻微 UX 不一致，随 B6-d 或 B6-c 处理。
③ 全站组件层超限仍余 **8 件**：`MaintPage` 522 / `ItemDetailDialog` 453 / `DeepReadPage` 428 / `V1Prototype` 411 / `HistoryPage` 407 / `layout/LayerCard` 385 / `TodoItem` 376 / `secrets/SecretsPage` 320 → **B6-a**。

## 14. B6-a 组件层剩余超限拆分验证证据（2026-11-18）

> 承接 §13.6 ③ 的 8 件清单，一次拆完。**目标达成：全站组件层（非测试）超限文件 8 → 0**，剩余 10 件全部落在 R3 分层豁免的契约层。

### 14.1 拆分结果（8 件 → 0 件，新增 23 文件）

| 原文件 | 原行数 | 现行数 | 新增文件（行数） |
|---|---|---|---|
| `MaintPage.tsx` | 522 | **189** | `MaintPage.types.ts` 92 / `MaintPageParts.tsx` 22 / `MaintPageHealthCard.tsx` 80 / `MaintPageVacuumCard.tsx` 116 / `MaintPageCleanupCard.tsx` 163 |
| `ItemDetailDialog.tsx` | 453 | **249** | `ItemDetailDialog.types.ts` 6 / `ItemDetailDialogHeader.tsx` 32 / `ItemDetailDialogParts.tsx` 223 / `ItemDetailDialogFooter.tsx` 98 |
| `DeepReadPage.tsx` | 428 | **138** | `DeepReadPageSectionCard.tsx` 153 / `DeepReadPageHeader.tsx` 92 / `DeepReadPageMetaBar.tsx` 113 |
| `v1/V1Prototype.tsx` | 411 | **47** | `V1PrototypeKnowledgeView.tsx` 198 / `V1PrototypeKnowledgeCard.tsx` 205 / `V1PrototypeParts.tsx` 14 |
| `HistoryPage.tsx` | 407 | **261** | `HistoryPageBatchList.tsx` 95 / `HistoryPageFilters.tsx` 55 / `HistoryPageItem.tsx` 56 / `HistoryPageParts.tsx` 41 |
| `layout/LayerCard.tsx` | 385 | **139** | `LayerCardParts.tsx` 174 / `LayerCardStates.tsx` 88 |
| `TodoItem.tsx` | 376 | **253** | `TodoItemActions.tsx` 161 |
| `secrets/SecretsPage.tsx` | 320 | **246** | `SecretsToolbar.tsx` 128 |

- 主文件最大 261 行；新文件最大 223 行 —— **全部 ≤300**。
- 拆分口径：纯搬迁。DOM 结构 / className / data-testid / i18n key / hooks 调用顺序逐字保留，未做任何行为或视觉改动。
- **导出面零变更**：`MaintPage` / `ItemDetailDialog` / `DeepReadPage` / `KnowledgeV1Page` / `HistoryPage` / `TodoItem` / `SecretsPage` 全部从原路径同名导出；`layout/LayerCard` 的 **8 个导出**（`LayerCard` `LayerCardRow` `LayerCardGrid` `LayerCardAlert` `PipelineFlow` `ViewMoreLink` `LayerEmptyState` `LayerSkeleton`）经 `export { … } from './LayerCardParts'` 原样转发，调用方零改动。

### 14.2 拆后全站超限扫描（组件层清零）

```
907 types/index.ts          847 api/settings.ts      762 api/v1.ts
572 api/knowledge.ts        453 types/codegarden.ts  428 lib/i18n/messages.zh-CN.ts
428 lib/i18n/messages.en-US.ts  420 api/secnews.ts   375 api/codegarden.ts
315 hooks/realtime.ts
```

10 件**全部**属 §2.1 R3 分层豁免（契约层按职责拆分、不按行数）。组件层（`components/` `routes/` `shell/`）**零超限**。

### 14.3 门禁实测

```bash
cd frontend && npx tsc --noEmit                  # exit 0
cd frontend && npx vitest run                    # 110 文件 / 783 tests 全通过
cd frontend && npx vitest run --coverage         # 58.69 / 77.45 / 60.30 / 58.69 (Stmts/Branch/Funcs/Lines)
cd frontend && npx vite build --logLevel error   # exit 0
python scripts/generate_meta.py --check          # OK (56/19/99/155, core_routers 67)
```

- 覆盖率四项仍**全部高于** `vite.config.ts` 阈值（57.05 / 76.39 / 57.42）：+1.64 / +1.06 / +2.88 / +1.64 pp。
- **登记小幅回落**：较 B6-b（58.92 / 77.61 / 60.61 / 58.92）为 −0.23 / −0.16 / −0.31 / −0.23 pp。归因：拆分后文件粒度变细，V8 计数按文件重置，`LayerCard`/`TodoItem` 两族本无测试覆盖（见 §14.5 ①），其行数在更小的文件里被更完整地计入分母。**未触及阈值，不构成门槛回退**。
- 专项测试：`MaintPage.test.tsx` 11/11、`DeepReadPage.test.tsx` 10/10、`secrets` 域 11/11、`v1_url_builder.test.ts` 7/7（该测试静态读 `V1Prototype.tsx` 源码断言无 `MOCK_`，拆分后主文件 47 行仍满足）。**四个测试文件均未修改**。

### 14.4 体积（观测项）

| 指标 | B6-b | **B6-a** | 变化 |
|---|---|---|---|
| 首屏 JS 口径 A | 88,292 B | **88,272 B** | **−20 B** |
| 入口 chunk | 23,219 | 23,201 | −18 |
| vendor-react | 53,816 | 53,816 | 0 |
| SentinelHomePage | 11,257 | 11,255 | −2 |
| 全量 JS / chunk 数 | 562,455 / 76 | 563,571 / 76 | +1,116 |

纯搬迁不改代码总量，首屏 −20 B 属 gzip 分块边界抖动（非优化收益）。全量 +1,116 B 来自新增 `export`/`import` 语句与模块包装。较 B0 基线 92,998 累计 **−4,726 B**。

### 14.5 未做与残留（显式声明）

① **`LayerCard` 与 `TodoItem` 当前在 `src/` 内无任何实际 import**（并行拆分时实测 grep 无引用；仅 gitignored 的本地 hook 状态快照提及）。导出面按要求完整保留，**未做删除清理** —— 删除属"减少代码面"的独立决策，超出 B6-a「拆到 ≤300 行」范围，登记待 owner 定夺。

② `V1Prototype.tsx` 文件名与导出名 `KnowledgeV1Page` 不一致，属既有约定，本批**未改名**（改名会波及 `routes/lazy-imports.ts`，非拆分范畴）。

③ B6 剩余子批：**c** 工具页容器统一（**d 已由 §15 交付**）。

---

## 15. B6-d — 壳层 / 资讯域 CSS 拆分（DEV-0403 · 2026-11-19）

**口径来源**：owner 裁决「旧三份 CSS 按照业务流和逻辑进行重构，打破壳层硬性，一切以业务流和逻辑为主」。

**病灶（唯一物理依据）**：`components/sentinel/sentinel.css`（607 行）被 `shell/AppShell.tsx` 全局 import → 全站所有页面（含设置域、工具页）都加载资讯域样式。

### 15.1 拆分归属表

| 归属 | 文件 | 行数 | 内容 |
|---|---|---|---|
| L2 壳层（AppShell 全局 import） | `shell/shell.css`（新建） | 275 | `.sentinel{}` 容器块（`--sn-*` 别名转发 / `--sn-bandnav-h` / 字体背景行高）· `::selection` · `:where(.sentinel) a/button` 元素重置 · `.tool-main` · `:focus-visible` · `.mono`/`.num` · masthead（`.masthead` `.mh-*` `.nv*`）· cmdbar（`.cmdbar*` `.cmd-result` `.mh-meta` `.clock` `.iconbtn`）· bandnav（`.bandnav` `.bn-*` 收起态）· pressbar（`.pressbar` `.pipe-*` `.pulse` `@keyframes sn-pulse` `.beat-*`）· 空态/骨架原子（`.empty-panel` `.empty-ring` `.empty-cta` `.skel-line`）· 主题覆写壳层部分 · 心跳漏斗 `.pipe-funnel` 组 · 壳层响应式（1240/1080/820/640） |
| L4 资讯域（资讯域三页 import） | `components/sentinel/sentinel.css` | 358 | `.controlbar` `.modes` `.mode-btn` `.channels` `.chip` · `.layout` `.maincol` `.story-top` `.meta-row` `.tag` `.src` `.time` `.headline` `.standfirst` `.heatbox` `.heat-cells` `.readmore` `.secondary` `.sub-item` `.flash-*` `.pick-*` · `.news-alert-list` `.na-*` `.abtn` · `.rail` `.src-list` `.judge-stats` `.act-*` `.endnote` · `.sentinel[data-mode=…]` 四态 · `.sn-oneline*` · 主题覆写资讯域部分 · `.sn-import*` · `.jd-eval*` · Phase 3 编辑部排版 · D7 收口 · 资讯域响应式 |

行数对账：607 → 275 + 358 = 633（+26 = 文件头 16 + 两条 1080px 联合规则 `@media` 各留一份 7 + 分节注释 3）。**剥注释/空行后逐行多重集比对**，唯一差异是 `.pressbar,.bandnav` 与 `.controlbar` 的联合规则按归属拆成两条。

归属零交叉（grep 实测）：`shell.css` 含 `.masthead{` / `.bandnav{` / `.pressbar{` 共 7 处，**不含** `.controlbar` / `.headline` / `.rail{` / `.news-alert-list`；`sentinel.css` 反之。三个资讯域页面（`SentinelHomePage` L39 / `SentinelActionPage` L55 / `SentinelGraphPage` L46）继续 `import './sentinel.css'`，共享原子（`.heat-cells` 等）仍可达。

未搬动（显式）：`sentinel-action.css`（453 行）与 `sentinel-graph.css`（219 行）本就只被各自页面 import = 页级 scoped，不存在壳层硬性，按 Rule 2/3 不做零收益搬目录。

### 15.2 守卫改造（断言条目与强度不变）

`routes/__tests__/nav4_shell.test.tsx` 原以 `readFileSync` 直读单份 `sentinel.css` 做源码文本断言。改为两文件拼接后再断言（B2 先例同法）：

```tsx
const SHELL_CSS = readFileSync(join(ROOT, "src/shell/shell.css"), "utf-8");
const SENTINEL_CSS_FILE = readFileSync(join(ROOT, "src/components/sentinel/sentinel.css"), "utf-8");
const SENTINEL_CSS = `${SHELL_CSS}\n${SENTINEL_CSS_FILE}`;
```

断言条目、正则与强度一字未改；`nav4_shell.test.tsx` 61 tests 全通过。

### 15.3 门禁

| 项 | 结果 |
|---|---|
| `npx tsc --noEmit; echo $?` | exit 0（无管道，取真实退出码） |
| `npx vitest run`（全量） | **110 文件 / 783 tests 全通过，0 失败** |
| `npx vitest run src/routes/__tests__/nav4_shell.test.tsx` | 61 / 61 |
| `npx vite build` | exit 0 |
| `python scripts/generate_meta.py --check` | OK |

### 15.4 构建产物分流证据（决定性）

| CSS chunk | raw | gzip | 含 `masthead` | 含 `headline` |
|---|---|---|---|---|
| `index-*.css`（全局壳层） | 60,951 | 12,759 | ✅ | ❌ |
| `sentinel-*.css`（资讯域） | 16,306 | 3,306 | ❌ | ✅ |
| `SettingsPage-*.css` | 17,645 | 3,142 | ❌ | ❌ |
| `SentinelActionPage-*.css` | 20,683 | 3,456 | ❌ | ❌ |
| `SentinelGraphPage-*.css` | 11,404 | 2,470 | ❌ | ❌ |
| `pages-*.css` | 5,526 | 1,361 | ❌ | ❌ |

结论：壳层样式随入口 chunk 加载，资讯域样式只在进入资讯域时加载；**设置域与工具页不再加载资讯域样式**，「壳层硬性」已实测拆除。

### 15.5 体积（观测项，口径 A = index + vendor-react + SentinelHomePage）

| 项 | B6-a | B6-d | Δ |
|---|---|---|---|
| index（入口） | 23,201 | 23,225 | +24 |
| vendor-react | 53,816 | 53,816 | 0 |
| SentinelHomePage | 11,255 | 11,273 | +18 |
| **首屏 JS gzip** | 88,272 | **88,314** | **+42**（+0.05%） |
| 全量 JS gzip / chunk | 563,571 / 76 | 563,714 / 76 | +143 |

较 B0 基线 92,998 累计 **−4,684 B（−5.04%）**，仍低于基线，满足 R4「每批登记且不得高于基线」。本批为纯 CSS 归属搬移，JS 侧 +42 B 属 chunk 模块序位移，非新增代码。

### 15.6 LCP 复测（R4 唯一判定指标）

脚本 `perf/lcp_ab.mjs --runs=3`（生产 `dist` + `vite preview` 1440×900 冷缓存 + `perf/lcp-api-fixture.json` 固定回放）：

| 组 | 三次采样 (ms) | 中位 | LCP 元素 |
|---|---|---|---|
| with_fonts | 116 / 124 / 168 | **124** | `h1.headline` |
| no_fonts | 116 / 116 / 112 | **116** | `h1.headline` |

基线 252 ms，目标 ≤ 201.6 ms（80%）→ **达标（124 ms，较基线 −50.8%）**。B5.5 的字体非阻塞改造在真实网络抖动下的收益保持稳定（带/不带字体仅差 8 ms）。

### 15.7 未做与残留（显式声明）

① **`--sn-*` 别名层保留不删**。它定义在 `.sentinel{}` 内、全部转发 `index.css` 全局 token，属 `.sentinel` 作用域内的语义转发层，与「壳层硬性」无关（后者已由代码分割解决）。删除需机械改写 4 份 CSS 中 1000+ 处 `var(--sn-*)`，零功能收益、高回归风险，违反 Rule 2 / Rule 3。契约 §8 风险表「B6 才删除」条目已按 Rule 7 改判并登记理由。

② **全站 `st-*` 原子去前缀不做**。同属纯改名：`st-*` 实测无跨域碰撞（设置域 `settings-shell.css` 与 `shared/editorial/Stamp.tsx` 的 `st-*` 零重叠），去前缀不改变任何加载边界。

③ `sentinel-action.css` / `sentinel-graph.css` **不搬目录**（理由见 §15.1）。

④ B6 剩余子批 **c**（工具页容器统一）**已由 §16 交付**（2026-11-19，DEV-0404）。

⑤ LCP 采样为冷缓存 + 固定夹具口径，未覆盖弱网/低端机场景；本报告不据此声称移动端或弱网指标。

## 16. B6-c 验证（工具页容器统一，口径 A）

### 16.1 病灶与改动

`PageLayout`（唯一挂载点 `routes/index.tsx#L135`）提供 `tool-main max-w-[1580px] mx-auto px-4 sm:px-6 pt-4 pb-16`（本批未改动），3 个 skills 工具页又各自再套一层 `p-4 md:p-6` → 双重内边距。

| 文件 | 改动 |
|---|---|
| `skills/SkillStore.tsx#L115` | 删 `p-4 md:p-6`，保留 `max-w-[1400px] mx-auto w-full` |
| `skills/SkillDetail.tsx#L80` | 删 `p-4 md:p-6`，保留 `max-w-[900px] mx-auto w-full` |
| `skills/SkillBuilder.tsx#L89` | 删 `p-4 md:p-6`，保留 `max-w-[800px] mx-auto w-full` |

全仓 `grep 'p-4 md:p-6'` 实测仅这 3 处；三页均只经 `/skill-store*` 路由在 PageLayout 内挂载（grep 无其他消费者）；其余工具页无自有 `max-w` / padding 容器包裹，未改动。

### 16.2 口径

owner 2026-11-19 裁定 **口径 A（最小）**：内容列宽（1400 / 900 / 800 属阅读型业务语义）由各页保留；**页边距统一由 PageLayout 提供**。口径 B（抽 `primitives/ToolPage`）与口径 C（PageLayout 独占宽度）未采纳 —— C 会把 900/800 窄阅读列拉宽，破坏详情 / 向导阅读体验。

### 16.3 门禁

```bash
cd frontend && npx tsc --noEmit                      # exit 0
cd frontend && npx vitest run src/components/skills   # 40 tests passed
cd frontend && npx vitest run --reporter=dot          # 110 文件 / 783 tests 全通过
cd frontend && npx vite build --logLevel error        # exit 0
python scripts/generate_meta.py --check               # OK
```

`nav4_shell.test.tsx` 无 `p-4 md:p-6` / `max-w-[1400|900|800px]` 断言（grep 实测），容器守卫（`max-width 1580 + 底部 64px`）指向 PageLayout，本批未触及。

### 16.4 体积（观测项，口径 A = 入口 + vendor-react + SentinelHomePage）

| 项 | B6-d | B6-c | Δ |
|---|---|---|---|
| index（入口，取自 `dist/index.html`） | 23,225 | 23,205 | −20 |
| vendor-react | 53,816 | 53,816 | 0 |
| SentinelHomePage | 11,273 | 11,273 | 0 |
| **首屏 JS gzip** | 88,314 | **88,294** | **−20** |
| 全量 JS gzip / chunk | 563,714 / 76 | 563,689 / 76 | −25 |
| 首屏 CSS gzip（index-*.css） | 12,759 | 12,754 | −5 |

较 B0 基线 92,998 累计 **−4,704 B（−5.06%）**，满足 R4「每批登记且不得高于基线」。

### 16.5 LCP 复测（R4 唯一判定指标）

`node perf/lcp_ab.mjs --runs=3`（复用 §15.6 同脚本 / 同夹具 / 已常驻 4173 的 `vite preview` 冷缓存）：

| 组 | 三次采样 (ms) | 中位 | LCP 元素 |
|---|---|---|---|
| with_fonts | 300 / 136 / 156 | **156** | `h1.headline` |
| no_fonts | 124 / 112 / 128 | **124** | `h1.headline` |

同会话另一次测量（相隔数分钟）：with_fonts 中位 **136** / no_fonts 中位 **128**。两组四次测量中位区间 124–156 ms，均 ≤ 201.6 ms → **达标**（较基线 252 ms 降 38%–51%）。with_fonts 首轮 300 ms 为字体 CDN 单次抖动，后续采样回落 —— 与 R4 归因一致。

### 16.6 未做与残留（显式声明）

① 口径 B / C 未采纳（owner 裁定 A）：本批零新增抽象、零 CSS 变更。
② 其余工具页（`SkillsPage` / `/dashboard` / `/secrets` / `/report` / `/maint` / 知识域子页）实测无自有容器包裹，未改动 —— 统一动作只落在确有双重容器的 3 页。
③ 未做人工视觉截图回归（仓库无视觉基线）：本批为删除重复 padding 的确定性改动；如需可对 3 页补 `preview` 截图比对。

---

## 17. B7 验证证据（redesign-v1 落地 R-1~R-4，DEV-0405 · 2026-11-19）

蓝本: `design/redesign-v1/DESIGN.md` §5（R-1 token 对齐 / R-2 组件词汇表替换 / R-3 印章组件化 / R-4 壳层微调）+ `design/redesign-v1/index.html` 交互 demo。

### 17.1 先查后改（为 R-2 定标）

| 层 | 实测 | 结论 |
|---|---|---|
| L0 `tokens/tokens.css` | 与 demo 约 95% 同源；差异 = `--line-strong` 三态数值 + demo 独有别名 | 走别名补齐，不加新色值 |
| L1 `primitives/` | 8 件已建、全仓引用数 = 0（孤儿） | R-2 的落点 |
| L2 壳（`shell/shell.css` + `AppShell`） | masthead / bandnav / pressbar / cmdbar 与 demo 同构 | R-4 无改动价值 |
| L3 `domains/` | 不存在 | 本批不建（D4 绞杀者不加新层） |
| L4 页面 | 21 处手写 `<h1>`，其中 6 页已用 `.ed-*` | R-2 消费面 |

### 17.2 R-2 首版返工（平行词汇表双轨，已撤回）

首版按 demo 类名新建 `.pg-head` / `.sec-title` / `.card` / `.stamp` / `.empty4`（137 行）。grep 发现 `components/shared/editorial/pages.css` 的 `.ed-*` 已是成熟词汇（ed-head ≈ pg-head、ed-sechead ≈ sec-title、ed-card ≈ card），`.empty-panel` 在 `shell.css`、`Stamp.tsx` 已在 `shared/editorial` → 判为平行双轨，**137 行全部删除**，`primitives.css` 缩至 26 行只补 `.badge` 一族。依据 DESIGN.md §5「先 grep 复用、禁止平行新增」。

### 17.3 改动清单

| 文件 | 改动 |
|---|---|
| `tokens/tokens.css` | R-1：补 `--shell-w` / `--dur-fast\|normal\|slow` / `--info` / `--accent-weak\|mint-weak\|amber-weak\|red-weak\|info-weak`（全部指向既有 token，零新色值）；`--line-strong` 三态对齐 demo（light 0.28 / dark 0.30 / paper `#cfc6b4`）。`--cat-*` 不引入（避免与生产 `--color-*` 分类色板双轨） |
| `primitives/primitives.css`（新，26 行） | `.sentinel .badge` + `b-ok / b-part / b-none / b-disc / b-red` 五档语义徽章（`.ed-*` 家族唯一缺口）；由 `StatusBadge.tsx` 自带 import |
| `primitives/PageHeader.tsx` | 改为复用 `.ed-head / .ed-h1 / .ed-sub`，自带 import pages.css；补 `kicker`（`.ed-kicker`）与 `footer`（描述下尾注）两个可选 prop |
| `primitives/StatusBadge.tsx` | 改吃 `.badge + .b-*`；tone 映射 ok→b-ok / info→b-part / warn→b-none / risk→b-red / neutral→b-disc；`data-tone` 与文字标签纪律保留 |
| `primitives/PageHeader.test.tsx` | 4 → 5 tests（新增 kicker 渲染 / footer 渲染 / kicker→h1 顺序） |
| `components/dashboard/Dashboard.tsx` | 实页接入 1：去自有 `p-6` 双重边距，保留 `dashboard-title` / `dashboard-back` testid |
| `components/MaintPage.tsx` | 实页接入 2：原 `text-2xl font-semibold` 手写头 → PageHeader |
| `components/quality/QualityDashboardPage.tsx` | 实页接入 3：PROOFROOM · 校对室 |
| `components/knowledge/KnowledgeLibraryPage.tsx` | 实页接入 4：CATALOG ROOM · 编目室 + 数据源印章（footer） |
| `components/knowledge/KnowledgeHubPage.tsx` | 实页接入 5：KNOWLEDGE HUB · 资料库前厅 + 数据源印章 |
| `components/events/EventsReviewBlocks.tsx` | 实页接入 6：WIRE DESK · 通稿审核 + 数据源印章 |
| `components/sync/SyncStatusBadge.tsx` | 返工二：改为 `primitives/StatusBadge` 薄封装（success→ok / error→risk / skipped→warn / unknown→neutral），使 `.badge` 词汇进入真实构建图；调用方 `SyncStatusPanel` / `SyncHistory` 零改动 |
| `components/TodoItem.tsx` | 返工二：分类 chip 由裸 `className="badge"` → `className="tag"`（demo §3 分类标签语义，化解与状态徽章的类名冲突；`.tag` 无 CSS 规则，视觉零变化） |
| `primitives/primitives.css`（修订） | 返工二：`.b-part` 底色由 `--info-weak`（实为薄荷 tint）改为 `color-mix(in srgb, var(--info) 10%, transparent)`，消除色相错配 |

后 4 处收敛前后 DOM 顺序与类名逐字不变（kicker → h1 → `.ed-sub` → 印章），仅引入原子调用。

### 17.4 R-3 / R-4 判定（无需改动，附证据）

- **R-3 印章组件化**：`components/shared/editorial/Stamp.tsx` 已存在，色值全部取自 token（`--ok/--warn/--err/--info`），并被 6 个业务文件 + 自带 test 消费（grep 实测 7 处引用）→ 实质已完成。
- **R-4 壳层微调**：`shell/shell.css` 的 `.masthead / .mh-nav / .pipe-block / .beat-lights / .cmdbar / .bandnav` 与 demo 壳同构（B6-d 已按业务流拆分）→ 无改动价值，本批未动。

### 17.5 门禁（本批实测）

```bash
cd frontend && npx tsc --noEmit                      # TSC_EXIT=0
cd frontend && npx vitest run --reporter=basic       # 110 files / 784 tests 全通过
cd frontend && npx vite build --logLevel error       # BUILD_EXIT=0
```

### 17.6 体积（观测项，口径 A = 入口 + vendor-react + SentinelHomePage）

| 项 | B6-c | B7（返工二后） | Δ |
|---|---|---|---|
| index（入口 `index-Bn_Ywj5D.js`） | 23,205 | 23,257 | +52 |
| vendor-react | 53,816 | 53,816 | 0 |
| SentinelHomePage | 11,273 | 11,273 | 0 |
| **首屏 JS gzip** | 88,294 | **88,346** | **+52** |
| 全量 JS gzip / chunk | 563,689 / 76 | 564,612 / 77 | +923 / +1 |
| 首屏 CSS gzip（`index-*.css`） | 12,754 | 12,754 | 0 |

较 B0 基线 92,998 累计 **−4,652 B（−5.00%）**，满足 R4「每批登记且不得高于基线」。CSS 分 chunk（gzip）: index 12,754 / sentinel 3,306 / SettingsPage 3,142 / SentinelActionPage 3,456 / SentinelGraphPage 2,470 / pages 1,361 / **index-Cm1W9lCe 306（徽章，仅 `/sync` 动态加载）**。

### 17.7 未做与残留（显式声明）

① LCP 未复测 —— 首屏 JS 仅 +52 B 且无新增首屏依赖、首屏 CSS 零增长；上一批 §16.5 中位 124–156 ms 仍代表当前首屏路径。
② 其余手写 `<h1>` 未接入 PageHeader，按「两种合法页头体例」保留：`/tags` `/search` `/extract` 紧凑工具头（`text-sm` + 2px 下边线 + 返回钮）、`ReviewPage` 内联 topBar（返回 / 标题 / 刷新三分布局）、`/action` `ac-h1`、`/settings` `st-title`、`FeedMustRead` 头条、knowledge 两处紧凑头 —— 换成 24–32px 衬线大标题属视觉倒退。
③ 未做人工视觉截图比对 demo（仓库无视觉基线）；如需可对 6 个接入页补 `preview` 截图。

### 17.8 孤儿原语返工（构建产物证据，2026-11-19）

收尾审计发现 R-2 徽章词汇「声明了但没发布」：首版 `StatusBadge.tsx` 全仓零生产消费者（仅自带 test 引用），Vite tree-shake 连带丢弃 `primitives.css`。

| 阶段 | 核验命令 | 原始输出（节选） |
|---|---|---|
| 修复前 | `node -e` 遍历 `dist/assets/*.css` 判 `.badge.b-ok` | `SentinelActionPage-*.css badge.b-ok false` / `SentinelGraphPage-*.css false` / `SettingsPage-*.css false` / `index-*.css false` / `pages-*.css false` / `sentinel-*.css false` —— **6/6 全 false** |
| 修复后 | 同上 | `index-Cm1W9lCe.css len 713 badge.b-ok true ed-head false` —— 徽章进入独立 chunk（306 B gzip，仅 `/sync` 动态加载） |

修复动作（3 处，见 §17.3 后三行）：`sync/SyncStatusBadge.tsx` → `primitives/StatusBadge` 薄封装（真实消费者）；`TodoItem.tsx` 分类 chip `.badge` → `.tag`（避免徽章 CSS 命中 `/action` 分类 chip）；`.b-part` 底色改 `color-mix`。

复跑门禁：`TSC_EXIT=0` · `Test Files 110 passed / Tests 784 passed` · `BUILD_EXIT=0`。首屏 CSS 仍 12,754 B（徽章 chunk 按需加载，零首屏成本）。

## 18. B7 独立验收复核（2026-11-19，合并工作区态）

> owner 指令「检查重构情况」触发的独立复核：在未提交的 B7 合并工作区上重跑门禁 + 抽查声明，非实现侧自评。

### 18.1 门禁复跑（原始数字）

```bash
cd frontend && npx tsc --noEmit && npx vitest run && npx vite build --logLevel error
# TSC_EXIT=0 · Test Files 110 passed (110) / Tests 784 passed (784) · BUILD_EXIT=0
cd frontend && npx vitest run --coverage          # exit 0 → 阈值（57.05/57.05/57.42/76.39）未破
python scripts/generate_meta.py --check           # OK (56/19/99/155 · core_routers 67) · AGENTS 7/7
```

### 18.2 声明抽查（逐项实测）

| 声明 | 实测 | 结果 |
|---|---|---|
| `.badge.b-ok` 进入构建产物 | `grep -l badge.b-ok dist/assets/*.css` → `dist/assets/index-Cm1W9lCe.css`（与台账 hash 一致） | ✅ |
| `SyncStatusBadge` 为 `primitives/StatusBadge` 真实消费者 | grep 生产 import → `components/sync/SyncStatusBadge.tsx:8` 恰 1 处 | ✅ |
| `TodoItem` 分类 chip 改 `.tag` | `TodoItem.tsx:191` `className="tag"` | ✅ |
| 6 页接入（dashboard/maint/quality/knowledge×2/events） | `git status` 改动集与 §17.3 清单一一对应 | ✅ |
| `primitives.css` 27 行 | `wc -l` = 26（另补尾换行，原文件缺失）；§17.2/§17.3/契约 B7 行/DEV-0405/CHANGELOG 五处「27 行」已同批修正为 26 | ⚠️ 已修正 |

### 18.3 复核发现（遗留缺口逾期，已登记 §4）

G3 / G4 / G5 三项缺口在 §4 中的承诺关闭时点均为 B6，B6 已于 2026-11-19 关闭而三项实测仍在（`SentinelShell.tsx` 9 行桥 + 生产 import 6 处；`api/settings.ts` 847 行；`EmptyState`/`Toast`/`ErrorBoundary`/`Icon` 未迁 primitives）——§4 三行已改判「未按期关闭，待 owner 裁决」，不静默漂移。B7 批次本体未发现阻断项。

### 18.4 待 owner 裁决

① B7 是否按仓规「每批一个 commit」提交（工作区 16 改动 + 1 新增 + 本次复核修正，一体可回滚）；② G3/G4/G5 处置：补做（另开 B8 小批）/ 显式豁免登记；③ 复核证据入 §18 后无其他未决项。

## 19. B8 验证证据（缺口收口批：G3 / G4 / G5 补做，2026-11-19）

> owner 指令「继续任务」→ 按 §18.4 ② 的推荐路径**补做**（非豁免）。B8 一个批次含三个子批：
> **a = G4**（兼容桥物理删除）/ **b = G3**（四件原语迁入 L1 primitives）/ **c = G5**（设置域 API 单体拆分）。
> 性质：机械搬移 + import 改指，零行为变更；DOM / class / data-testid / aria / 端点 URL / method / body 逐字保留。

### 19.1 B8-a（G4 关闭）：SentinelShell 兼容桥物理删除

| 项 | 内容 |
|---|---|
| 桥文件 | `components/sentinel/SentinelShell.tsx`（9 行 re-export）**物理删除** |
| 生产 import 改指 6 处 | `components/PageLayout.tsx` → `../shell/AppShell`；`components/v1/CaseDetailPage.tsx` → `../../shell/AppShell`；`components/sentinel/SentinelActionPage.tsx` → `../../shell/AppShell`；`SentinelGraphPage.tsx` / `SentinelHomePage.tsx` → `../../shell/AppShell` + `../../shell/pipe`（`usePipeReloadOnSse` 拆独立 import）；`SentinelHomeAux.tsx` → `../../shell/pipe`（`usePipe`） |
| 测试迁移 | `components/sentinel/SentinelShell.test.tsx` → **`shell/AppShell.test.tsx`**（git mv，改 import 路径；10 个用例逐字未改） |
| 注释同步 | `hooks/realtime.ts` 的 SSE 消费者清单改为 `src/shell/pipe.tsx`；`nav4_shell.test.tsx` 头注释与 menuOf 段注释改为「壳源码集合 / `shell/AppShell.test.tsx`」表述 |
| 残留核查 | 全仓 `grep "SentinelShell'"` → 0 处 import（仅 `describe('SentinelShell')` 组件名，组件导出名未变） |

**守卫处理（断言条目与强度不变）**：`nav4_shell.test.tsx` 的 `SHELL_FILES` 本就指向 `src/shell/*` 六文件，桥删除**不触及任何断言**；`expect(src).toContain("<SentinelShell")` 三处页面级断言（`SentinelHomePage` / `SentinelActionPage` / `CaseDetailPage`）因 JSX 组件名未变而原样通过；「5 视图不得自嵌 SentinelShell」断言（`not.toContain("SentinelShell")`）不受影响。

### 19.2 B8-b（G3 关闭）：四件原语迁入 L1 primitives

| 原路径 | 新路径 | 行数 | 测试 |
|---|---|---|---|
| `components/EmptyState.tsx` | `primitives/EmptyState.tsx` | 109 | `primitives/EmptyState.test.tsx`（迁移后逐字未改） |
| `components/Toast.tsx` | `primitives/Toast.tsx` | 237 | `primitives/Toast.test.tsx` |
| `components/ErrorBoundary.tsx` | `primitives/ErrorBoundary.tsx` | 112 | `primitives/ErrorBoundary.test.tsx` |
| `components/Icon.tsx` | `primitives/Icon.tsx` | 35 | `primitives/Icon.test.tsx` |

- **import 改指 86 处 / 81 个文件**（脚本按各文件所在目录深度精确计算相对路径，非文本替换）：`App.tsx` / `main.tsx` → `./primitives/*`；`components/*`（depth 1）→ `../primitives/*`；`components/<子域>/*`（depth 2）→ `../../primitives/*`；`components/v1/__tests__/*`（depth 3）→ `../../../primitives/*`。
- **L1 分层纪律核验（B1 硬规则「无业务依赖」）**：迁入的 4 件内部依赖仅 `react` + 同目录 `./Icon`（`Toast` / `ErrorBoundary` 引用 Icon，迁后同目录相对路径不变）；`primitives/` 目录对 `components/` 的 import 仅剩 `PageHeader.tsx` 一处 CSS 引用（B7 已有的仓内约定）。
- **B1「每原子 ≥1 测试」**：4 件各自带 colocated test 且**用例逐字未改**，随迁入 `primitives/`。
- 残留核查：全仓 `grep "components/(Icon|EmptyState|Toast|ErrorBoundary)"` → 仅 5 处注释内路径（已同步改写）。

### 19.3 B8-c（G5 关闭）：设置域 API 单体按子域拆分

`src/api/settings.ts` **847 行 → 22 行薄 barrel + 11 个子模块**（按原文件自身的章节注释边界切分，函数体逐字未改）：

| 子模块 | 归属章节 | 行数 |
|---|---|---|
| `api/settings/overview.ts` | 系统总览 / 模式 / 能力门禁 | 89 |
| `api/settings/sync.ts` | 同步 | 117 |
| `api/settings/proxy.ts` | 代理 | 83 |
| `api/settings/prefs.ts` | 兴趣画像 / 内容偏好 | 134 |
| `api/settings/mcp.ts` | MCP | 48 |
| `api/settings/models.ts` | 模型 | 92 |
| `api/settings/secrets.ts` | 密钥保险箱 | 126 |
| `api/settings/intake.ts` | 自动入管 | 40 |
| `api/settings/ops.ts` | 运维 / 历史批次 | 118 |
| `api/settings/knowledge.ts` | SOUL 画像 / 联邦状态 | 33 |
| `api/settings/skillRegistry.ts` | Skill registry 读侧 | 59 |

- **零丢失校验（机械比对）**：导出函数 **82 → 82**，函数名全集 `diff` 一致；导出 `interface` / `type` 全集 `diff` 一致。
- **消费方零改动**：barrel 用 `export *` 转发，**126 处 `from '../api/settings'` 的 import 路径全部不变**（含 `type FeatureGate` / `type MCPTool` / `type AutoIntakeConfig` / `type SecretsStatusPayload` / `PoolPlatform` / `PoolRouting` / `PoolSnapshot` 等类型导入）。
- **守卫改造（条目与强度不变）**：`nav4_shell.test.tsx` 的「MaintPage 走 `/api/maintenance/*` 真实端点」用例原直读 `src/api/settings.ts` 找端点 URL，拆分后端点正文落在 `settings/ops.ts` → 改为对**域模块集合**（barrel + 11 子模块）拼接后断言，5 条断言（3 个真实端点 + 2 个已退役端点）**逐条保留**（同 B6-d CSS 拼接先例）。

### 19.4 门禁实测（合并态统一复测）

```bash
cd frontend && npx tsc --noEmit                  # exit 0
cd frontend && npx vitest run                    # 110 文件 / 784 tests 全通过
cd frontend && npx vitest run --coverage         # 58.67 / 77.42 / 60.43 / 58.67 (Stmts/Branch/Funcs/Lines)
cd frontend && npx vite build --logLevel error   # exit 0
python scripts/generate_meta.py --check          # OK (56/19/99/155 · core_routers 67) · AGENTS 7/7
```

- 覆盖率 vs B7 同机同命令实测基线（**B7 原未登记覆盖率数字，本次用独立 worktree 复现 235d9bf 构建补测**）：58.70 / 77.51 / 60.30 / 58.70 → B8 为 58.67 / 77.42 / 60.43 / 58.67，**Δ −0.03 / −0.09 / +0.13 / −0.03 pp**，四项仍全部高于 `vite.config.ts` 阈值（57.05 / 76.39 / 57.42）。
- 测试用例数 **784 = 784**（三子批均为搬移，用例零增删）。

### 19.5 体积（口径 A = 入口 + vendor-react + SentinelHomePage）

| 指标 | B7 | **B8** | Δ |
|---|---|---|---|
| 入口 chunk | 23,257 | 23,324 | **+67** |
| vendor-react | 53,816 | 53,816 | 0 |
| SentinelHomePage | 11,273 | 11,273 | 0 |
| **首屏 JS gzip** | 88,346 | **88,413** | **+67 B（+0.08%）** |
| 首屏 CSS gzip（`index-*.css`） | 12,754 | 12,754 | 0 |
| 全量 JS gzip / chunk 数 | 564,612 / 77 | **565,046 / 81** | **+434 B / +4 chunk** |

较 B0 基线 92,998 累计 **−4,585 B（−4.93%）**，仍低于基线，满足 R4「每批登记且不得高于基线」。

**chunk 变化归因（产物 diff，B7 基线由独立 worktree 复现构建取得）**：

| 变化 | 明细 |
|---|---|
| 新增 5 chunk | `ops` 436 / `overview` 307 / `secrets` 465 / `skillRegistry` 266 / `sync` 383 = 1,857 B —— **settings 子模块被多路由共享，Rollup 按共享边界各自拆出独立 chunk** |
| 消失 1 chunk | `settings` 1,848 B —— 原单体模块形成的共享 chunk |
| SettingsPage chunk | 36,653 → 37,015（+362）—— 子模块正文内联至此 |
| 入口 chunk | +67 —— barrel 的 `export *` 语句进入入口 |

即：**代码总量仅 +434 B gzip（+0.08%）**，chunk 数 +4 是 1 个模块 → 12 个模块后的 Rollup 分块边界效应，非代码膨胀。chunk 数非契约门禁项（§7.1 门禁 = LCP 单指标 + 首屏 JS 观测项）。

### 19.6 LCP 复测（R4 唯一判定指标）

`node perf/lcp_ab.mjs --runs=3`（生产 `dist` + `vite preview` 1440×900 冷缓存 + `perf/lcp-api-fixture.json` 固定回放），两个会话各 3 轮：

| 组 | 会话 1（ms） | 中位 | 会话 2（ms） | 中位 |
|---|---|---|---|---|
| with_fonts | 120 / 120 / 140 | **140** | 216 / 152 / 112 | **152** |
| no_fonts | 116 / 124 / 140 | **124** | 160 / 136 / 168 | **160** |

LCP 元素均为 `h1.headline`。基线 252 ms，目标 ≤ 201.6 ms（80%）→ **两组四次测量中位 124–160 ms，全部达标**（较基线降 36%–51%）。

### 19.7 未做与残留（显式声明）

① **§4 三项缺口已全部关闭**（G3/G4/G5），缺口表见 §4 更新行；② `api/settings.ts` 虽在 R3 契约层豁免目录内，但 G5 独立于 R3 关闭（拆分口径 = 按章节职责拆，非行数豁免）；③ 拆分成 11 个子模块后 chunk 数 +4，若后续关注请求数可合并为 4–5 个子模块（行数仍 ≤300），本批按「1 章节 = 1 子模块」的最可核对口径执行；④ 未做人工视觉截图回归（仓库无视觉基线），本批为纯搬移，DOM 逐字未变。




## 20. B9 验证证据（遗留项收口批，2026-11-19）

> owner 指令「继续处理遗留项」。承接 §18.4 / §19.7 的遗留清单，三子批：
> **a = 设置域子模块 11 → 5 合并**（回收 Rollup 共享 chunk）/ **b = L1 原子 `ToolPageHeader` + 6 页工具页头收敛** /
> **c = 视觉回归机检工具入仓**（补齐仓库无视觉基线的空缺，把「人工走查」前置为机械证据）。
> 性质：机械搬移 + 参数化收敛，**DOM 与类名逐字保留**（见 §20.4 像素级证据）。

### 20.1 B9-a：设置域子模块 11 → 5（按业务域合并）

| 子模块 | 合并来源 | 行数 |
|---|---|---|
| `api/settings/core.ts` | overview（系统总览/模式/能力门禁）+ sync（同步） | 197 |
| `api/settings/ops.ts` | ops（运维/历史批次）+ intake（自动入管）+ skillRegistry | 200 |
| `api/settings/security.ts` | secrets（密钥保险箱）+ proxy（代理） | 201 |
| `api/settings/intelligence.ts` | prefs（兴趣画像/内容偏好）+ mcp + models | 257 |
| `api/settings/knowledge.ts` | knowledge（SOUL/联邦状态） | 34 |

- 全部 ≤300（最大 257）；barrel `api/settings.ts` 17 行，`export *` 转发 → **126 处消费方 import 路径不变**。
- **零丢失三重校验（机械比对）**：导出函数 **82 → 82**（函数名全集 `diff` 一致）、导出 `interface`/`type` 全集一致、**端点 URL 全集 53 个一致**（防搬运丢端点）。
- **守卫同步**：`nav4_shell.test.tsx` 的 `SETTINGS_MODULES` 清单由 11 个文件名改为 5 个（`core/ops/security/intelligence/knowledge`），**5 条断言逐条保留**；61 tests 全通过。
- 首版合并脚本曾漏剥源模块自带 import 导致重复导入，已修正后重跑（上表为修正后产物，import 行数 2/文件）。

### 20.2 B9-b：L1 原子 `ToolPageHeader` + 6 页页头收敛

**新原子**：`primitives/ToolPageHeader.tsx`（77 行）+ `primitives/ToolPageHeader.test.tsx`（7 用例）。两种体例，DOM 与类名逐字复刻原页内实现：

| 体例 | 构成 | 收敛页 |
|---|---|---|
| `compact` | `flex items-center justify-between pb-2 mb-1` + 2px 下边线 + `text-sm font-bold tracking-wide` 标题 + 等宽前缀 + 右对齐 ghost 返回钮（`btn-ghost gap-1.5 px-2 py-1 text-[10px]` + `Icon size={11}`） | `/tags`（TAG）、`/search`（FIND）、`/extract`（EXT） |
| `bar` | `<header class="flex items-center gap-3">` + 左侧 bordered 返回钮（`h-8 px-2.5 rounded-md text-sm border`）+ `text-lg font-bold` 标题（可 `truncate`）+ 尾部槽 | `SkillStore`（计数）、`SkillDetail`（`[ON]/[OFF]` + truncate + `backLabel="返回商店"`）、`SkillBuilder` |

- **收敛前的重复面**：三页紧凑头经 `diff` 实测**除前缀（TAG/FIND/EXT）与标题文字外逐字相同**；skills 三页容器与返回钮逐字同构。
- 随收敛清理：三页失效的 `Icon` import 移除（`<Icon` 残留计数 = 0）。
- B1「每原子 ≥1 测试」：新原子自带 7 用例（体例 DOM/类名、返回钮点击、`truncate`、trailing 槽、无 `onBack` 不渲染）。

### 20.3 B9-c：视觉回归机检工具入仓

| 文件 | 说明 |
|---|---|
| `frontend/perf/visual_regress.mjs` | 逐路由截图（1440×900 fullPage）+ 导出页头 `outerHTML`；后端不在时 API 一律回放 `{}`，页面走空态/错误态（页头仍渲染 = 本批改动面）；**屏蔽壳层时钟与动画**消除非确定性 |

**非确定性处置（实测）**：首次比对时 6 页整页截图**同一构建两次即不一致**（壳层 `.clock` + 呼吸动画）→ 工具内注入 `.clock/.pulse { visibility: hidden }` 与 `animation/transition: none`，复测**同构建两次截图逐字节一致**（确定性成立）。

### 20.4 视觉回归证据（B8 对照构建 vs B9，6 路由）

对照基线由独立 worktree 复现 `e0931ae`（B8）构建取得，两构建并行 preview（4174 / 4173）同机同视口比对。

| 路由 | 页头 `outerHTML` | 整页截图 |
|---|---|---|
| `/tags` | **逐字节一致** | **逐字节一致**（107,068 B） |
| `/search` | **逐字节一致** | **逐字节一致**（60,522 B） |
| `/extract` | **逐字节一致** | **逐字节一致**（74,504 B） |
| `/skill-store` | **逐字节一致** | **逐字节一致**（155,918 B） |
| `/skill-store/new` | **逐字节一致** | **逐字节一致**（79,470 B） |
| `/skill-store/:id` | **逐字节一致** | **逐字节一致**（55,129 B） |

结论：**6 个受影响路由像素级零变化、DOM 逐字节零变化** —— 本批为纯结构收敛，无视觉回归。
（人工视觉走查仍留白给 owner：机检只覆盖 6 个改动页，非全站。）

### 20.5 门禁、体积与 LCP

```bash
cd frontend && npx tsc --noEmit                  # exit 0
cd frontend && npx vitest run --coverage         # 111 文件 / 791 tests 全通过 · 58.73 / 77.50 / 60.41 / 58.73
cd frontend && npx vite build --logLevel error   # exit 0
python scripts/generate_meta.py --check          # OK (56/19/99/155 · core_routers 67) · AGENTS 7/7
```

- 测试：111 文件 / **791 tests**（B8 为 110 / 784，+1 文件 +7 用例 = 新原子测试）。
- 覆盖率 **58.73 / 77.50 / 60.41 / 58.73**（Stmts/Branch/Funcs/Lines）vs B8 **58.67 / 77.42 / 60.43 / 58.67** → Δ +0.06 / +0.08 / −0.02 / +0.06 pp，四项仍全部高于阈值（57.05 / 76.39 / 57.42）。

| 指标 | B8 | **B9** | Δ |
|---|---|---|---|
| 入口 chunk | 23,324 | 23,317 | −7 |
| vendor-react | 53,816 | 53,816 | 0 |
| SentinelHomePage | 11,273 | 11,271 | −2 |
| **首屏 JS gzip** | 88,413 | **88,404** | **−9 B** |
| 首屏 CSS gzip | 12,754 | 12,754 | 0 |
| 全量 JS gzip / chunk | 565,046 / 81 | **565,011 / 80** | **−35 B / −1 chunk** |

较 B0 基线 92,998 累计 **−4,594 B（−4.94%）**。

**chunk 归因**：settings 共享 chunk **5 → 3**（`overview`+`sync`→`core` 541 B、`ops`+`intake`+`skillRegistry`→`ops` 707 B、`secrets`+`proxy`→`security` 546 B）；新增 `ToolPageHeader` 共享 chunk 633 B（6 页共享同一原子），抵掉 6 页各自内联的页头码 → 净 **−1 chunk / −35 B**。

**LCP（R4 唯一判定指标）**：`node perf/lcp_ab.mjs --runs=3` × 2 会话 —— with_fonts 中位 **120 / 132** ms、no_fonts 中位 **124 / 120** ms，LCP 元素均 `h1.headline`；基线 252 ms、目标 ≤ 201.6 ms → **达标**（较基线降 48%–53%）。

### 20.6 R-2 剩余面登记（新增缺口，本批未硬改）

勘察「各域平行实现」时发现 DESIGN.md §5 **R-2 的真实范围**（「StatusBadge / DataTable / 空态四态按 §3 统一替换各域实现」）远未完成 —— B7 落地的是种子（`.badge` 词汇 + `PageHeader` + `StatusBadge` 薄封装），B9 补的是页头族。剩余面实测盘点：

| 面 | 实测 | 说明 |
|---|---|---|
| **6 件孤儿原语** | `AsyncState` / `DataTable` / `Inspector` / `Panel` / `SplitPane` / `Toolbar` 生产消费者 **= 0** | 原语自 B1 起建成但从未被页面消费（`AsyncState` 唯一「引用」是 `hooks/useQuery.ts` 的一条注释，非 import） |
| 平行数据表 | **18 个文件**含 `<table>`（`secnews/pipeline` 3 · `settings` 5 · `secnews` 其他 3 · `layout/LayerTable` · `dashboard/SkillMatrix` · `events/EventsReviewBlocks` · `knowledge/KnowledgeLibraryPage` · `quality/QualityDashboardPage` · `sentinel/review/ReviewManageView`） | `primitives/DataTable` docstring 自称「统一替换 17 套原生 table」；**逐表 DOM 结构差异大（含 colspan / 自定义 thead / 卡内嵌套表）**，机械替换会改版式 |
| 空态四态 | **108 个文件**含自写「载入中/暂无/加载失败」态 | `primitives/AsyncState` 四态原语 0 消费者 |
| 域内标签 | 7 处（`editorial-badge` / `ac-badge` ×2 / `pick-badge` / `alert-unread-badge` / `source-type-tag`） | 逐条核验为**分类标签**（精选/未读/类型），**非** §3 的状态徽章语义 → 与状态徽章不是同一族；B7 刻意把 `TodoItem` 分类 chip 从 `.badge` 改 `.tag` 正是二者分族的结果 |

**处置建议（待 owner 裁决，本批不硬改）**：

1. **状态徽章族**：域内真正的「状态徽章」语义站点极少（仅 `settings/SettingsPage.tsx` 的 `st-chip ok` 一处）→ 该族统一面本身就小，可优先落地。
2. **分类标签族**：需先定义独立词汇（如 `.tag` + 语义变体）再替换 7 处，**不得回退到 `.badge`**（否则与状态徽章撞类名 —— B7 已为此返工一次）。
3. **数据表族**：18 处 DOM 差异大，建议按域分批（每域 1–3 处），逐批比对像素，**不做全量机械替换**。
4. **6 件孤儿原语**：逐件定「落地到真实页」或「退役删除」。`Inspector` 的实现假设为**右侧抽屉**，而域内既有详情交互为**中心模态**（`ItemDetailDialog`：`position: fixed; inset: 0` + overlay）→ 直接替换等于重设计，需先定交互形态。

以上登记为缺口 **G7**（R-2 词汇表替换未完成）与 **G8**（6 件孤儿原语），见 §4；不静默遗留。

### 20.7 未做与残留（显式声明）

① **人工视觉走查仍留白给 owner**：机检只覆盖 6 个改动页的像素级回归，非全站走查；② R-2 剩余面（§20.6）按上文建议分批推进，未在本批硬改；③ `ToolPageHeader` 的 `bar` 体例用 `truncate` prop 表达长名截断（`SkillDetail`），属**参数化而非新增体例**，未引入第三种版式；④ 未做移动端/弱网口径（本批零首屏依赖变化，首屏 JS −9 B）。

### 20.8 待 owner 裁决（B9 收口时的开放决策清单）

> 实现侧不自评 PASS、不自选方向；以下四项须 owner 定夺。登记于此以免只在会话中流转。

| # | 决策 | 选项 | 实现侧推荐 | 影响面 |
|---|---|---|---|---|
| **D1** | **G7**（R-2 词汇表替换未完成）如何推进 | ① 状态徽章族先行（面最小）② 分类标签族 ③ 数据表族（按域分批）④ 全量机械替换 | **① → ③ 顺序推进**（② 待 D1① 之后） | 状态徽章：域内真正的状态语义站点仅 `settings/SettingsPage.tsx` 的 `st-chip ok` 1 处，面最小可速胜；分类标签 7 处**须先定义独立词汇**（`.badge` 已被状态徽章占用，B7 已因撞类名返工一次）；数据表 18 处 DOM 差异大（含 colspan / 自定义 thead / 卡内嵌套表），④ 会改版式 |
| **D2** | **G8**（6 件孤儿原语）处置 | ① 逐件落地到真实页 ② 逐件退役删除 ③ 混合 | **③ 混合**：`DataTable` / `AsyncState` / `Panel` / `Toolbar` 随 D1 落地；`SplitPane` / `Inspector` 先定交互形态再落 | `Inspector` 原语假设**右侧抽屉**，域内既有详情交互为**中心模态**（`ItemDetailDialog` = `position:fixed; inset:0` + overlay）→ 替换等于重设计而非词汇统一；`SplitPane` 需先确认存在真实两栏场景 |
| **D3** | 视觉走查口径 | ① owner 人工全站走查 ② 机检扩到全站路由 ③ 仅保留 6 页机检 | **① + ③**（机检守回归，人工验收语义） | 机检当前只覆盖 6 个改动页；扩到全站需先把 `perf/lcp-api-fixture.json`（现 12 端点）扩成全路由夹具 —— 另属一项工程量 |
| **D4** | 下一批立项方向 | ① 开 **B10** 推进 R-2 剩余面 ② 转 **v0.8.9 发布收口**（C7-2 `git tag v0.8.9`） | **②**（v0.8.9 观测窗 2026-11-14 → 2026-12-14，满窗后方可 tag） | B10 属数周级词汇表统一工程；C7-2 是 §AGENTS 当前阶段唯一未结项 |

**无待决项的部分（已闭环，不需裁决）**：B0–B9 全部批次 + G3 / G4 / G5 三项缺口均已关闭并留痕；全站组件层超限清零；R4 LCP 单指标持续达标（B9 中位 120–132 ms，基线 252 ms）；首屏 JS 累计 −4,594 B（−4.94%）低于基线；门禁四道（`tsc` / `vitest --coverage` / `vite build` / `generate_meta --check`）全绿。
