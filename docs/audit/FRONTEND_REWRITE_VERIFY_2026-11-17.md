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
| B6 | 设置域 + 工具页 + 旧 CSS 删除 + **组件层剩余 17 件超限拆分** + 性能对比 | §7 全部指标达标 / 旧代码零残留 | ⏳ 未开始 |

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



