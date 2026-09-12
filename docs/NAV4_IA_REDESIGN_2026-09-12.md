# 四大菜单 IA 重设计 — 资讯 / 知识 / 行动 / 设置

- 日期: 2026-09-12; 状态: **设计完成待裁决** (本轮不动任何代码)
- 指令来源: owner 2026-09-12 「将整个系统调整成 4 大菜单: 资讯, 知识, 行动, 设置」
- 性质: **信息架构(IA)一级重构** — 替代 v0.8.5 的「Sentinel 三层唯一壳」裁决; 本方案获 owner 批准后, v0.8.5_PLAN §5 将出 2026-09-12 第三条修订注, frontend/src/AGENTS.md 的「禁止新一级入口」硬规则随本裁决改写
- 复利叙事存续声明: 三层「资料→判断→行动」不被推翻, 而是升级为 **资讯→知识→行动 的复利闭环**(知识首次升为一级概念, 此前埋在工具页) + **设置**横切;「判断」不再是一级层, 其能力拆解归位(§3)

## 0. 结论先行

| 菜单 | 路径 | 定位 | 吸收的现有能力 |
|---|---|---|---|
| **资讯** | `/` (默认落地) | 看什么 — 资讯流、质量筛选、采集管道、深读 | 资料层 Feed + SignalPanel + **判读台(质量漏斗)** + secnews feed/pipeline/analytics + 深读 + 浏览历史 + 质量拒绝样本 |
| **知识** | `/knowledge` | 沉淀什么 — 知识库、图谱、能力资产、加工工具 | 知识库 9 子路由 + knowledge/v1 + **图谱(自 /judge/graph)** + skill-store + 技能看板 + 标签/提取/搜索 + 间隔复习 + secnews wiki |
| **行动** | `/action` | 做什么 — 案件、待办、今日行动、产出 | 行动层(今日行动+ExecOverview) + **CaseQueue/CaseDetail(自判断层)** + 待办 + 周报月报 + CodeGarden 泳道 + secnews 研判 |
| **设置** | `/settings` | 怎么配 — 全局配置、密钥、同步、扩展域 | SettingsHub(17 cat) + 密钥 + 同步备份 + 技能库配置 + 观测 + codegarden/crm 扩展页 |

壳改造一句话: `SentinelShell` 三 tab 改四 tab(心跳条保留), 全部工具页按上表归位进菜单内导航, 「更多菜单」与 `SecNewsShell` 双壳退役。

## 1. 现状盘点 (2026-09-12 代码事实)

### 1.1 壳的三套并存

| 壳 | 载体 | 导航 | 状态 |
|---|---|---|---|
| SentinelShell | 三层页(`/` `/judge` `/action` `/garden` `/cases/:id`) | 3 tab(资料/判断/行动)+ 更多菜单 + 心跳条 | v0.8.5 唯一主壳 |
| PageLayout | ~20 工具页 | = `<SentinelShell layer={null}>`(顶部三层导航 + 更多高亮) | 2026-09-10 壳统一产物 |
| SecNewsShell | `/secnews/*` 6 tab | 独立品牌导航 + StatusBar | **双壳遗留**, 本方案收敛 |

### 1.2 更多菜单三分组(SentinelShell UTILITY_GROUPS, 全量 17 项)

- 情报输出: `/report` `/search` `/history` `/reviews` `/secnews`
- 知识资产: `/knowledge` `/skill-store` `/dashboard` `/tags` `/extract` `/skills` `/todos`
- 运维与配置: `/garden` `/secrets` `/sync` `/settings`

### 1.3 关键约束

- 守卫测试 `routes/__tests__/v085_route_shell.test.tsx` 锁定三层壳 + AppNav 删除断言 — 必须随本重构重写
- v0.8.5_PLAN §5 是路由唯一权威, 冲突须同 commit 修订
- `/knowledge` 已有 9 个嵌套子路由(import/process/compile/compound/imported/deep-read/:id/review/heatmap), 新父级导航不得破坏
- 心跳条 SSE Provider 链有已知坑(usePipeReloadOnSse 在 Provider 外不刷新, DEV-0167 遗留), 壳改造时防回归
- gate 页(`/garden` codegarden、`/crm`)路由注册受 feature gate, 归属变更不动 gate 语义

## 2. 目标 IA

```
┌──────────────────────────────────────────────────────┐
│  [品牌]   资讯   知识   行动   设置        ♥ 心跳条   │  ← 唯一全局壳 (4 tab)
├──────────────────────────────────────────────────────┤
│ 资讯 /        │ 知识 /knowledge │ 行动 /action │ 设置 /settings │
│ ├ 情报流      │ ├ 知识库(9 tab) │ ├ 今日行动   │ ├ 17 配置分区   │
│ ├ 质量与漏斗  │ ├ 图谱          │ ├ 案件队列   │ ├ 密钥/同步     │
│ │ (原判读台)  │ ├ 能力资产      │ ├ 待办       │ ├ 技能库配置    │
│ ├ 采集管道    │ │ (store/看板)  │ ├ 报告输出   │ ├ 观测          │
│ ├ 分析统计    │ ├ 加工工具      │ ├ 泳道       │ └ 扩展域        │
│ └ 深读/历史   │ └ 复习/wiki     │ └ 研判       │    (codegarden  │
│              │                 │              │     /crm)       │
└──────────────────────────────────────────────────────┘
  复利闭环: 资讯(输入+筛选) → 知识(沉淀) → 行动(产出) → 反哺资讯(兴趣引擎)
```

设计原则:
1. **4 tab 即 4 顶级路径, 全部复用既有路径**(`/` `/knowledge` `/action` `/settings`), 变更面最小; 仅 `/judge` 需拆解(§4)。
2. **菜单内导航用页内次级导航**(tab/侧栏, 沿用 KnowledgeTabs 模式), 全局「更多菜单」退役。
3. **一个路由一个壳**: 4 菜单壳全站唯一, SecNewsShell 并入(其 6 视图拆归各菜单)。
4. **URL 稳定性**: 既有深链(`/deep/:type/:id`、`/cases/:id`、`/knowledge/*`)全部保留原路径; 被归位的页面优先**保路径、改归属高亮**, 路径变更是少数且全部 redirect。

## 3. 「判断层」拆解 — 本方案唯一的概念手术

SentinelJudgePage 现承载三块异质能力, 拆解如下:

| 现有能力 | 归属 | 形态 |
|---|---|---|
| 判读台主体(质量门禁统计/今日收录/分类分布/trend 点阵) | **资讯** → `/` 页内「质量」区(tab 或折叠区块, 与 Feed 并列) | 组件复用, 不重写 |
| CaseQueuePanel(案件队列) + `/cases/:id` 深链 | **行动** → /action 页内区块 + 保留 `/cases/:id` 路径 | 仅导航高亮变化 |
| `/judge/graph`(知识图谱) | **知识** → 路径改为 `/knowledge/graph`(旧路径 redirect) | 组件不动 |

`/judge` 与 `/cases`(列表) 路径 redirect: `/judge` → `/`(判读台语义融入资讯质量区), `/cases` → `/action`。判断作为**动作**无处不在(资讯筛选/案件研判), 不再需要一级容器 — 这是本重构的核心理由: 「判断」是动词不是房间。

## 4. 全量路由归属映射表 (27 项逐一处置)

### 4.1 资讯 `/` (默认落地)

| 路径 | 现状 | 处置 |
|---|---|---|
| `/` | SentinelHomePage(Feed+SignalPanel) | **保留**, tab=资讯; 页内新增「质量」次级区(吸收判读台主体) |
| `/judge` | SentinelJudgePage | **redirect → `/`**(透传 query); 主体拆解见 §3 |
| `/secnews/feed` `/secnews/pipeline` | SecNewsShell | P1 改挂资讯壳, 路径保留 |
| `/secnews/analytics` | SecNewsShell | 同上(内容统计归资讯) |
| `/quality/rejection` | PageLayout | 归属资讯(质量), 路径保留, 高亮资讯 |
| `/deep/:type/:id` | DeepReadPage | 归属资讯(深读), 路径保留 |
| `/history` | PageLayout | 归属资讯, 路径保留 |
| `/category/:cat` | redirect `/` | 不变 |

### 4.2 知识 `/knowledge`

| 路径 | 现状 | 处置 |
|---|---|---|
| `/knowledge`(+9 嵌套子路由) | KnowledgePage/KnowledgeTabs | **保留**, tab=知识, 成为知识菜单主页 |
| `/knowledge/v1` | KnowledgeV1Page | 保留 |
| `/judge/graph` | SentinelGraphPage | **改路径 `/knowledge/graph`**; 旧路径 redirect |
| `/skill-store`(+`/:id` `/new`) | SkillStore 系 | 归属知识(能力资产), 路径保留 |
| `/dashboard` | 技能看板 | 归属知识, 路径保留 |
| `/tags` `/extract` `/search` | 三工具页 | 归属知识(加工工具), 路径保留 |
| `/reviews` | 间隔复习 | 归属知识, 路径保留 |
| `/secnews/knowledge` | WikiBrowser | P1 改挂知识壳, 路径保留 |

### 4.3 行动 `/action`

| 路径 | 现状 | 处置 |
|---|---|---|
| `/action` | SentinelActionPage(+ExecOverview) | **保留**, tab=行动; 页内新增 CaseQueue 区块 |
| `/cases/:caseId` | CaseDetailPage | **保留路径**, 壳从 judge 改 action 高亮 |
| `/cases` | redirect → `/judge` | **改 redirect → `/action`** |
| `/todos` | TodosPage | 归属行动, 路径保留 |
| `/report` | 周报/月报 | 归属行动(产出物), 路径保留 |
| `/garden` | SentinelGardenPage(gate) | 归属行动(泳道=工作流), 路径保留 |
| `/secnews/analyze` | 研判 tab | P1 改挂行动壳, 路径保留 |

### 4.4 设置 `/settings`

| 路径 | 现状 | 处置 |
|---|---|---|
| `/settings` | SettingsHub(17 cat) | **保留**, tab=设置 |
| `/sentinel/settings` | redirect `?cat=sentinel` | 不变 |
| `/secrets` `/sync`(gate) | 两工具页 | 归属设置, 路径保留 |
| `/skills` | 技能库(配置) | 归属设置(与 skill-store 内容库区分: 此页是开关/参数), 路径保留 |
| `/secnews/observability` | 观测 tab | P1 改挂设置壳(系统运维观测), 路径保留 |
| `/codegarden`(+`/phase2b`)(gate) | CodegardenPage | 归属设置「扩展域」区(低频配置视图; 泳道操作在 /garden 归行动), 路径保留 |
| `/crm`(gate) | CrmPage | 归属设置「扩展域」, 路径保留 |
| `/oauth-callback` | OAuth 回调 | 不变(无导航) |
| `*` | redirect `/` | 不变 |

### 4.5 退役清单

| 项 | 处置 |
|---|---|
| SentinelShell「更多菜单」(UTILITY_GROUPS 17 项) | P0 保留过渡(防断链), P1 随归位完成**物理删除**(全部入口已由 4 菜单承接) |
| SecNewsShell(独立品牌导航+StatusBar) | P1 视图拆归后**退役**; StatusBar 心跳能力并入全局心跳条 |
| `/secnews`(index) | redirect → `/secnews/feed`(P1) → P2 评估直接并入 `/` 采集管道区 |
| 三层 LAYER_DEFS / SentinelLayer 类型 | P0 改 4 tab 定义; `layer` prop 语义改为菜单 key(data/knowledge/action/settings) |

## 5. 壳与导航改造细节

### 5.1 SentinelShell(P0)

- `LAYER_DEFS` 3 项 → 4 项: `{key:'news',label:'资讯',to:'/'}` `{key:'knowledge',…,to:'/knowledge'}` `{key:'action',…,to:'/action'}` `{key:'settings',…,to:'/settings'}`; active 规则按路径前缀(工具页高亮其归属菜单 — 新增 `menuOf(path)` 纯函数, 单测覆盖)
- 心跳条/管道可视化**原样保留**(全站常驻不动)
- 移动端窄屏折叠逻辑(DEV-0171)适配 4 tab
- i18n: `nav.news/knowledge/action/settings` 双语键

### 5.2 菜单内次级导航(P1)

- 知识菜单主页 = KnowledgeTabs 扩展为「库 / 图谱 / 能力 / 工具 / 复习」5 段(库=既有 9 子路由不动, 其余段以卡片入口跳转既有路径 — **不强行嵌套路由**, 保 URL 稳定)
- 资讯菜单主页 = Feed(默认) + 「质量」折叠区(判读台组件) + 「管道」入口(secnews pipeline)
- 行动菜单主页 = 今日行动 + 案件队列区块 + 待办/报告/泳道入口卡
- 设置 = SettingsHub 左侧分区列表追加「扩展域」分组

### 5.3 测试与守卫重写(P0 随壳)

- `v085_route_shell.test.tsx` → 重写为 `nav4_shell.test.tsx`: 4 tab 断言 + /judge /cases redirect 断言 + 更多菜单退役断言(P1 后)+ 每菜单高亮 `menuOf` 断言
- ROUTE_REGISTRY.md 第四次重写(按 4 菜单分组)
- 组件测试路径断言全量过一遍(grep `/judge` 前端测试引用)

## 6. spec 与治理文档修订(同 commit, 防漂移)

| 文档 | 修订 |
|---|---|
| `docs/v0.8.5/V0.8.5_PLAN.md` §5 | 追加 **2026-09-12 修订注③**(owner 裁决: 四大菜单 IA): §5 表逐行按 §4 映射改写或标注; §10 一致性门指向新守卫测试 |
| 根 `AGENTS.md` | 首段「三层唯一壳」改「四菜单壳(v0.9 IA)」; 历史决策入 PROJECT.md |
| `frontend/src/AGENTS.md` | 「禁止新一级入口/新壳」硬规则改写为「4 菜单之外禁止新一级入口」 |
| `PROJECT.md` / `PROGRESS.md` | 三层→四菜单裁决记录归档 |
| `docs/ARCHITECTURE.md` | 前端壳描述段同步(不动数字门禁 — 无 router/service 增减) |

## 7. 分期实施

### P0 — 壳与重定向(半天~1 天, 零页面重写)

1. SentinelShell 4 tab + `menuOf()` + i18n + 窄屏适配
2. 路由变更仅 4 条: `/judge`→redirect `/`; `/cases`→redirect `/action`(原→/judge); `/judge/graph`→新路径 `/knowledge/graph`(旧 redirect); `/secnews` index→feed
3. 判读台/CaseQueue **暂留原位**(挂新壳高亮), 页面迁移留给 P1 — P0 结束时全站可走查, 无死链
4. 守卫测试重写 + ROUTE_REGISTRY 重写 + v0.8.5 修订注③ + AGENTS×2
5. 验收: vitest/tsc 全绿; 走查 4 菜单各 3 条路径; 全部旧路径 curl 级 redirect 验证

### P1 — 页面归位与双壳收敛(1~2 天)

1. 判读台主体迁入 `/` 质量区; CaseQueue 迁入 `/action`; graph 组件挂 `/knowledge/graph`
2. 17 个工具页逐页挂归属菜单高亮; 各菜单主页建次级导航(§5.2)
3. SecNewsShell 6 视图拆挂对应菜单壳; StatusBar 退役(心跳条已有等价能力)
4. 更多菜单物理删除
5. 验收: 独立 agent 走查(4 菜单 × 全部子页可达性 + SSE 心跳条在 Provider 内刷新); vitest 全绿

### P2 — 清理与收尾(0.5 天)

1. SecNewsShell/AppNav/UTILITY_GROUPS 死代码删除; lazy-imports 清理
2. 文档终稿(PROJECT/PROGRESS/USER_GUIDE); DEV_LOG 收口
3. 验收: 死代码 grep 零残留; e2e 冒烟

## 8. 风险与防护

| 风险 | 防护 |
|---|---|
| `/judge` redirect 丢 query(判读台带筛选深链) | redirect 统一透传 query(v0.8.5 §5 既有约定) |
| 心跳条 SSE 在新壳布局下断链(DEV-0167 已知坑) | P1 迁移时 SSE Provider 包裹范围列为走查必检项 |
| `/knowledge` 9 嵌套子路由被父级改版破坏 | 知识菜单主页只加外壳导航, 库区组件与子路由零改动 |
| 更多菜单先删后迁造成入口真空 | P0 保留更多菜单过渡, P1 归位完成才物理删除(§4.5) |
| gate 页归属变化误伤注册语义 | 归属仅改导航高亮, 路由注册/gate 断言零变更 |
| 守卫测试与 spec 漂移 | §6 修订与代码同 commit(仓库既有纪律) |

## 9. 裁决清单(确认后即开工 P0)

| # | 问题 | 推荐 |
|---|---|---|
| ① | 判读台(质量漏斗)归**资讯**(质量区) vs 保留独立子菜单 | 资讯质量区(判断是动词不是房间) |
| ② | skill-store/技能看板归**知识**(能力资产) vs 行动(工具) | 知识 |
| ③ | `/todos` `/report` 归**行动** | 行动(工作项+产出物) |
| ④ | SecNews 双壳 **P1 拆归** vs 保留独立入口 | 拆归(否则 4 菜单名不副实) |
| ⑤ | codegarden 配置页/crm 归**设置·扩展域**; 泳道 /garden 归**行动** | 如左 |
| ⑥ | 菜单命名定稿: 资讯/知识/行动/设置(路径 `/` `/knowledge` `/action` `/settings`) | 如左(全复用现有路径) |
| ⑦ | `/skills`(技能配置)归**设置**(与 skill-store 内容库分离) | 设置 |
