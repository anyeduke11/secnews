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
