
## [DEV-0074] UI/UX — 统一科技风样式重构（第二阶段）
- **时间**: 2026-07-22 10:45
- **类型**: 重构
- **关联文件**: 
  - `frontend/src/index.css`
  - `frontend/src/components/CategoryNav.tsx`
  - `frontend/src/components/SearchBar.tsx`
  - `frontend/src/components/StatsPanel.tsx`
  - `frontend/src/components/HotspotGrid.tsx`
  - `frontend/src/App.tsx`
  - `frontend/src/components/RegionFilter.tsx`
- **问题描述**: 
  - 上一阶段（DEV-0073）完成了 CSS 设计系统（index.css）以及 HotspotCard、Header 的重构，但 CategoryNav、SearchBar、StatsPanel、HotspotGrid、App footer 和 RegionFilter 仍使用大量内联样式
  - 参考上一阶段 checkpoint 列出的剩余任务，逐一完成
- **实现思路**:
  - 组件统一使用 `.cat-pill` / `.search-box` / `.time-toggle` / `.stat-card` / `.pagination-btn` / `.page-indicator` / `.tech-divider` 等 CSS 类
  - 所有内联 `style={{}}` 的 border/background/color/padding 等样式移至 CSS 类
  - 仅保留动态颜色（如分类色 `cat.color`）通过 `style={{}}` 传入
- **核心变更**:
  - `CategoryNav.tsx`: 按钮改用 `cat-pill` + `active` CSS 类，替换 inline style + onMouseEnter/onMouseLeave 手写 hover
  - `SearchBar.tsx`: 输入框改用 `search-box` 容器 + `search-icon`/`search-clear`，时间按钮改用 `time-toggle` 容器
  - `StatsPanel.tsx`: 改用 `stat-card` CSS 类替换原有内联样式
  - `HotspotGrid.tsx`: 分页按钮改用 `pagination-btn`，页码改用 `page-indicator`
  - `App.tsx`: `<footer>` 改用 `tech-divider` CSS 类替换手写 borderTop+伪元素
  - `RegionFilter.tsx`: 修复 `var(--surface-2)` → `var(--bg-card)`
- **测试验证**:
  - 测试命令: `npx tsc --noEmit`（TypeScript 编译检查，0 新错误）
  - 验证结果: dev server (localhost:8898) HTTP 200，Vite HMR 正常加载
- **潜在风险**: 动态颜色传递依赖 `style={{}}` 注入，确保 color 未定义时 CSS 类默认值生效

## [DEV-0075] P1 架构优化 — 路由级代码分割 + 统一测试策略
- **时间**: 2026-07-22 07:55
- **类型**: 重构
- **关联文件**:
  - `frontend/src/App.tsx`
  - `frontend/src/App.test.tsx`（新增）
  - `backend/tests/conftest.py`（新增）
  - `backend/pytest.ini`（新增）
  - `backend/tests/`（61 个文件添加 pytest markers）
- **问题描述**: 架构评审后识别两个 P1 级别的程序问题：前端首屏 bundle 包含全部 CodeGarden/Knowledge/Security 页面代码；后端 70+ 测试文件无共享 fixture、无类型标记
- **实现思路**:
  - **P1-1 路由级代码分割**: 11 个重量级页面组件（CodegardenPage/KnowledgePage/TodosPage/SkillsPage 等）改为 `React.lazy()` 动态导入，首页/分类页等核心页面保持静态导入。添加 Suspense 边界和加载回退，不影响现有用户体验
  - **P1-2 统一测试策略**:
    - `conftest.py`: 提供 `temp_db`（基于 config.db_path monkeypatch）和 `e2e_api_client`（独立 FastAPI + TestClient）两个共享 fixture
    - `pytest.ini`: 注册 `unit`/`integration`/`e2e` 三种标记，提供过滤基准
    - 61 个测试文件按类型标记：`unit` (19个) / `integration` (37个) / `e2e` (6个)
    - `App.test.tsx`: 新增前端路由冒烟测试（11 条，全部通过），mock hooks 避免真实 API 调用
- **核心变更**:
  - `App.tsx`: 新增 `Suspense` 导入 + 11 个 `React.lazy()` 定义 + `PageFallback` 组件 + 路由元素包裹 `<Suspense fallback={...}>`
  - `backend/tests/conftest.py`: `temp_db` fixture（关闭旧连接+初始化 schema+清理）+ `e2e_api_client` fixture（挂载全部 router）
  - `backend/pytest.ini`: 标记注册 + 警告过滤
  - 61 个测试文件: 每个文件添加 `pytestmark = pytest.mark.{type}`
- **测试验证**:
  - 测试命令: `cd frontend && npx vitest run src/App.test.tsx`
  - 验证结果: 11/11 PASS（首页×2 + 9 个懒加载路由 × 1）
- **潜在风险**:
  - `React.lazy()` 依赖组件模块的 default export，当前所有页面都是 named export，通过 `.then(m => ({ default: m.X }))` 转换，无兼容性问题
  - conftest 的 `temp_db` 与 test_db.py 等文件自己的同名 fixture 不冲突（pytest 就近规则）
  - 标记分类基于代码分析和文件结构判断，个别文件若跨越多种类型需要后续手动调整

## [DEV-0076] v1.7 完整 PRD 设计方案（增强版）
- **时间**: 2026-07-22 16:20
- **类型**: 功能开发
- **关联文件**: `docs/hotspot_v1.7_PRD.md`
- **实现思路**:
  - 在已有 v1.7 PRD 雏形（848 行）基础上进行增强，新增以下内容：
    1. **用户旅程分析**: 以 IT 安全从业者为视角，梳理 08:00-17:30 一天工作流，映射 11 个 M 模块
    2. **第一性原理分析**: 拆解"信息→知识→行动"完整认知链路，识别 6 个环节中 4 个断裂点
    3. **额外遗漏点**: 阅读状态跨设备同步、快速捕捉(Quick Capture)、离线间隔摘要、注意力热图、决策日志、上下文感知阅读流
    4. **完整 API 设计**: 31 个新增端点的 Method/Path/请求参数/响应说明 完整覆盖
    5. **架构设计决策**: 8 条关键技术决策（FTS5 vs ES，规则引擎 vs ML，SM-2 vs Anki 等）
    6. **迁移与测试策略**: 10 张新表的迁移脚本规划、10 个后端测试 + 7 个前端测试文件
    7. **Phase 规划**: 5 个 Phase、~20 天总预估、每个 Phase 的可交付清单
    8. **功能开关**: 8 个 feature flag，渐进式上线策略
- **核心变更**:
  - `docs/hotspot_v1.7_PRD.md`: 完整重写（848 行），增加目录、用户旅程、第一性原理分析、完整 API Schema、前端组件树、hooks 清单
- **测试验证**: N/A（文档类变更）
- **潜在风险**: 功能开关默认关闭的 Phase (复习/告警/推荐/个性化) 需要手动开通，需在 RUNBOOK 中注明


## [DEV-0077] v1.7 PRD 完整重写 — Hotspot ↔ Agent 双向环架构 + OKF + LLM-Wiki 2.0 统一存储
- **时间**: 2026-07-22 22:30
- **类型**: 功能开发
- **关联文件**: `docs/hotspot_v1.7_PRD.md`
- **实现思路**:
  - 在已有 DEV-0076 基础上，汇总全部讨论决策，完整重写 v1.7 PRD（1427 行）
  - 核心新增架构决策：
    1. **Hotspot ↔ Agent 双向环**: 不再是线性管道，Agent 和 Hotspot 互相生产消费
    2. **SAG 生命周期状态机**: 替换 `compiled: bool`，引入 signal → amplify:tagged → amplify:linked → amplify:complete → generate 五阶段
    3. **OKF + LLM-Wiki 2.0 统一存储**: `.md` 文件为源数据，SQLite 为 KV 缓存层 + 查询加速层
    4. **SQLite KV 缓存层**: 新增 kv_cache 表，加速 LLM-Wiki 查询，避免频繁文件 I/O
    5. **Agent 协议与任务队列**: 基于文件系统 (tasks/pending/) 的异步通知协议，Phase-locked polling
    6. **CLI 工具层整合到 Agent**: 统一入口 `hotspot-agent`，所有子命令通过 Agent 调用
    7. **收藏→知识提升 (M12)**: 收藏文章自动写入 knowledge/items/，触发 SAG 生命周期
    8. **Agent Skill 配置**: Agent 原生能力，Hotspot 只存储配置，不调度执行
    9. **Phase-locked polling 延迟考量**: 轮询间隔、延迟分析、弊端对策表
    10. **36 个新增 API 端点**: 含 3 个 Agent 通信端点
  - 章节结构：0-版本概述 → 1-用户旅程 → 2-架构 → 3-数据模型 → 4-API → 5-Agent 协议 → 6-功能规格 → 7-调度器 → 8-前端 → 9-跨端同步 → 10-迁移 → 11-测试 → 12-Phase 规划 → 13-验收 → 14-风险 → 15-术语表
- **核心变更**:
  - `docs/hotspot_v1.7_PRD.md`: 从 847 行完整重写为 1427 行，新增 580 行核心内容（Agent 协议、SAG 生命周期、KV 缓存、CLI 整合、M12 收藏→知识提升）
- **测试验证**: N/A（文档类变更）
- **潜在风险**: 无（纯文档变更）

## [DEV-0130] PRD v1.7.7: 吸收 SAG 设计强化 LLM-Wiki 2.0 + OKF 架构
- **时间**: 2026-07-26 18:30
- **类型**: 功能开发
- **关联文件**: `docs/hotspot_v1.7_PRD.md`, `backend/services/sag_service.py`
- **实现思路**: 全面分析 Zleap-AI/SAG 核心设计思想（Event-Entity 模型、查询时动态超边、增量处理），将其设计原则吸收到 LLM-Wiki 2.0 + OKF 架构中，而不引入 SAG 全平台。同时基于多轮架构讨论更新 PRD 为 v1.7.7 版本。
- **核心变更**: 
  - PRD 头版更新: v1.7.6 -> v1.7.7, 定位增加"互联网资讯知识化平台"
  - 新增 §0.6-0.8: SAG 设计思想吸收分析、KL 生命周期命名变更、认知链路补充
  - 架构更新: 增加双向生产环、事件-实体模型、crawl4ai 采集层
  - 数据模型更新: 新增 item_entities, collector_sources, agent_poll_config 三张表
  - §5.6-5.7: Hotspot ↔ AI Agent 双向生产环 + 定时轮询设计
  - §6.13: 采集层升级 (传统爬虫/crawl4ai/标讯)
  - §17: 完整 SAG 吸收实现架构 + 事件-实体模型 + 动态超边 + Agent CLI + 实施任务清单
  - SAG -> KL 生命周期重命名 (kl:raw -> kl:refine -> kl:link -> kl:structure -> kl:publish)
  - 全部附录更新，增加 H-L 共 6 个新附录
- **设计决策**: 
  - 不引入 SAG 全平台, 吸收其 event-entity 模型到 OKF
  - SAG 生命周期 -> KL 生命周期 (避 Zleap 命名冲突)
  - Agent -> Hotspot: MCP 协议 (v1.7.6 保留)
  - Hotspot -> Agent: CLI 调用 (v1.7.7 新增)
  - 轮询: 双向定时, 遵循 KL 刷新周期, 可自定义
- **潜在风险**: item_entities 表需要与现有 tags/concepts 协调数据一致性
