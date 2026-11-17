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
| B4 | 资讯域 `/` 重写 | 首屏区块全保留 / 单文件 ≤300 行 / 包体积不增 | ⏳ 未开始 |
| B5 | 知识域 + 行动域重写 | 同上 | ⏳ 未开始 |
| B6 | 设置域 + 工具页 + 旧 CSS 删除 + 性能对比 | §7 全部指标达标 / 旧代码零残留 | ⏳ 未开始 |

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
| G3 | `EmptyState` / `Toast` / `ErrorBoundary` / `Icon` 未迁入 `primitives/`（77 处 import） | L1 原子目录不完整（功能无影响） | B6 收口 |
| G4 | `SentinelShell.tsx` 兼容桥（9 行）与 6 处旧路径 import 并存 | 双路径过渡态 | B6 全量改指后删除 |
| G5 | `src/api/settings.ts` **847 行**（B3 新建），超 §2.2「单文件 ≤300 行」 | 数据层文件超长（行为无影响；与 `api/v1.ts` 762 / `api/knowledge.ts` 572 同属历史级超长） | B6 设置域重写时按子域拆分 |
| G6 | `hooks/useQuery.ts` 无生产消费者（仅 `useQuery.test.tsx`） | 数据层接缝已交付但未接线，B3 不计入运行时收益 | B4 首个重写区块接入 + 绑 SSE 失效 |

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
2. **24 条未定位中 17 条属后端/工程纪律能力**：前端重写不承载；若重写期临时想补可见性，只能作为四菜单内区块，禁止新增一级入口。
3. **3 处零测试：SET-5（sync）/ SET-14（dsh）/ XF-15**：按「有测试=安全」推进会静默丢功能，B6 须补测试或写入显式豁免清单。