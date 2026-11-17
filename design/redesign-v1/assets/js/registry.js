/* ============================================================
 * Hotspot 全站重构 demo — 路由注册表 + PRD 能力清单（数据底账）
 * 数据源：frontend/src/routes/index.tsx（60 路由实测）、
 *        design/_research/routes-status.md、design/_research/prd-capabilities.md
 * 状态口径：✅ ok 已上线 ｜ ◐ partial 部分/后端就绪前端未接/观测中
 *           ○ none 未实现·规划 ｜ ↷ redirect 重定向兼容 ｜ ◈ disc 纪律生效
 * 本文件为纯静态演示数据（演示样例 · 非真实数据），不连任何后端。
 * ============================================================ */
window.HS = (function () {
  'use strict';

  /* ---------- 四菜单 ---------- */
  var LAYERS = [
    { key: 'data',      label: '资讯', en: 'DATA',      root: '/' },
    { key: 'knowledge', label: '知识', en: 'KNOWLEDGE', root: '/knowledge' },
    { key: 'action',    label: '行动', en: 'ACTION',    root: '/action' },
    { key: 'settings',  label: '设置', en: 'SETTINGS',  root: '/settings' }
  ];

  /* ---------- 版面条二级域 chips（对应壳 bandnav） ---------- */
  var BANDS = {
    data: [
      { t: '资讯流', p: '/' }, { t: '安全资讯', p: '/secnews/feed' },
      { t: '管线观测', p: '/secnews/pipeline' }, { t: '校对室', p: '/quality' },
      { t: '分析', p: '/secnews/analytics' }, { t: '历史', p: '/history' }
    ],
    knowledge: [
      { t: '知识库', p: '/knowledge' }, { t: '前厅', p: '/knowledge/khub' },
      { t: '编目室', p: '/knowledge/library' }, { t: '图谱', p: '/knowledge/graph' },
      { t: '复习', p: '/reviews' }, { t: '能力包', p: '/skill-store' },
      { t: '工具', p: '/dashboard' }
    ],
    action: [
      { t: '今日行动', p: '/action' }, { t: '案件', p: '/cases/case-0117' },
      { t: '通稿审核', p: '/action/events' }, { t: '研判', p: '/secnews/analyze' },
      { t: '产出', p: '/report' }
    ],
    settings: [
      { t: '总览', p: '/settings' }, { t: '维护', p: '/maint' },
      { t: '密钥', p: '/secrets' }, { t: '同步', p: '/sync' },
      { t: 'CodeGarden', p: '/codegarden', gate: 'codegarden' },
      { t: '观测', p: '/secnews/observability' }
    ]
  };

  /* ---------- Feature Gates：16 gate（开 15 / 关 1 mcp） ---------- */
  var GATES = [
    { k: 'codegarden', on: true }, { k: 'codegarden_phase2b', on: true },
    { k: 'sync', on: true }, { k: 'tech_stack', on: true },
    { k: 'security_graph', on: true }, { k: 'secnews', on: true },
    { k: 'dsh', on: true }, { k: 'info_filter', on: true },
    { k: 'skill_registry', on: true }, { k: 'trigger_gate', on: true },
    { k: 'user_skills', on: true }, { k: 'interest_engine', on: true },
    { k: 'semantic_filter', on: true }, { k: 'ai_classify', on: true },
    { k: 'pipeline_ner', on: true },
    { k: 'mcp', on: false, note: 'extension gate 只管调试路由；server 本体 is_mcp_enabled() 双开关' }
  ];

  /* ---------- 页面路由（44 条，全部 ✅ 组件实测存在） ----------
   * v: 富视图 key（home/action/case/knowledge/khub/graph/settings/quality/pipeline/maint/skillstore/reader）
   *    未标 v 的为「页面档案视图」（统一风格骨架 + 状态/API/依据）
   * l: 档案视图布局类型  caps: 本页涉及的 PRD 未实现/部分项
   * g: gate 依赖（关闭时路由不渲染） */
  var ROUTES = [
    /* —— 资讯 data（7）—— */
    { p: '/', t: '情报流首页', c: 'SentinelHomePage', m: 'data', s: 'ok', v: 'home',
      d: '四阅读模式（全量/精选/深度/告警）资讯流 + 受管信号区块 + 优先情报摘要卡',
      api: ['/api/hotspots', '/api/hotspots/picked', '/api/alerts/v2', '/api/v1/signals', '/api/v1/cases', '(SSE) /api/events'],
      e: 'index.tsx L94 + components/sentinel/SentinelHomePage.tsx', caps: ['DATA-8', 'DATA-9', 'DATA-10'] },
    { p: '/history', t: '浏览历史', c: 'HistoryPage', m: 'data', s: 'ok', l: 'list',
      d: '按批次聚合的浏览历史，可回灌知识库', api: ['/api/history/batches', '/api/knowledge/import-from-history'],
      e: 'components/HistoryPage.tsx' },
    { p: '/quality', t: '校对室', c: 'QualityDashboardPage', m: 'data', s: 'ok', v: 'quality',
      d: '门禁统计全貌 + 信息过滤规则表 + 拒绝样本（人话解释）', api: ['/api/quality/summary', '/api/info-filter/rules'],
      e: 'components/quality/QualityDashboardPage.tsx（UNIMPLEMENTED #5 已闭环）' },
    { p: '/deep/:type/:id', t: '跨实体深读', c: 'DeepReadPage', m: 'data', s: 'ok', l: 'detail',
      d: '跨实体 AI 判读流深读', api: ['/api/deep-read'], e: 'components/DeepReadPage.tsx' },
    { p: '/secnews/feed', t: '安全资讯流', c: 'FeedView', m: 'data', s: 'ok', l: 'feed',
      d: 'SecNews 资讯流（赞/踩挂载点）', api: ['/api/secnews/feed'], e: 'components/secnews/feed/FeedView.tsx' },
    { p: '/secnews/pipeline', t: '管线观测', c: 'PipelineView', m: 'data', s: 'ok', v: 'pipeline',
      d: '采集管线生命周期漏斗 + 来源矩阵', api: ['/api/secnews/*', '/api/kl/pipeline/stats'],
      e: 'components/secnews/pipeline/PipelineView.tsx', caps: ['DATA-19'] },
    { p: '/secnews/analytics', t: '分析视图', c: 'SecNewsAnalytics', m: 'data', s: 'ok', l: 'stats',
      d: 'CVE 近况分析', api: ['/api/cve/recent'], e: 'components/secnews/analytics/SecNewsAnalytics.tsx' },

    /* —— 知识 knowledge（23）—— */
    { p: '/knowledge', t: '知识库', c: 'KnowledgePage', m: 'knowledge', s: 'ok', v: 'knowledge',
      d: '知识库主页（嵌套壳，默认子路由 → /knowledge/import）', api: ['/api/knowledge'],
      e: 'components/KnowledgePage.tsx（嵌套 index → import）', caps: ['KNOW-6', 'KNOW-13'] },
    { p: '/knowledge/import', t: '信息导入', c: 'KnowledgeImport', m: 'knowledge', s: 'ok', l: 'form',
      d: 'URL/目录导入（Cubox *.json + 递归 *.md、Obsidian）', api: ['/api/knowledge/sync', '/api/knowledge/cubox/*', '/api/knowledge/obsidian/*'],
      e: 'components/knowledge/KnowledgeImport.tsx', caps: ['KNOW-11'] },
    { p: '/knowledge/process', t: '处理数据', c: 'KnowledgeProcess', m: 'knowledge', s: 'ok', l: 'table',
      d: '知识条目处理（域/主题/类型/难度）', api: ['/api/knowledge/items'], e: 'components/KnowledgeProcess.tsx' },
    { p: '/knowledge/compile', t: '知识库编译', c: 'KnowledgeCompile', m: 'knowledge', s: 'ok', l: 'board',
      d: '编译计划与任务监控', api: ['子组件：CompileTrigger / TaskMonitor'], e: 'components/KnowledgeCompile.tsx' },
    { p: '/knowledge/compound', t: '知识库复利', c: 'KnowledgeCompound', m: 'knowledge', s: 'ok', l: 'stats',
      d: '学习面板（kl 域）', api: ['子组件：LearningPanel 等'], e: 'components/KnowledgeCompound.tsx' },
    { p: '/knowledge/imported', t: '已导入收藏', c: 'KnowledgeFavoritesView', m: 'knowledge', s: 'ok', l: 'list',
      d: '收藏与已导入视图', api: ['hook useImported'], e: 'components/KnowledgeFavoritesView.tsx' },
    { p: '/knowledge/v1', t: 'v1 知识目录', c: 'KnowledgeV1Page', m: 'knowledge', s: 'ok', l: 'table',
      d: '复盘沉淀目录 + 采用/复查链', api: ['/api/v1/knowledge'], e: 'components/v1/V1Prototype.tsx（KnowledgeV1Page 导出）', caps: ['KNOW-2', 'KNOW-6'] },
    { p: '/knowledge/deep-read/:id', t: '条目深读', c: 'DeepReadMode', m: 'knowledge', s: 'ok', l: 'detail',
      d: '知识条目深读（4 cognitive mode 删除后保留主路径）', api: ['/api/knowledge', '/api/recommend/knowledge', '/api/attention/events'],
      e: 'components/DeepReadMode.tsx' },
    { p: '/knowledge/review', t: '条目复习', c: 'ReviewMode', m: 'knowledge', s: 'ok', l: 'detail',
      d: 'SM-2 复习（到期/评分）', api: ['/api/reviews/due', '/api/reviews/grade'], e: 'components/ReviewMode.tsx' },
    { p: '/knowledge/heatmap', t: '关注度热力图', c: 'AttentionHeatmap', m: 'knowledge', s: 'ok', l: 'stats',
      d: '注意力事件热力图', api: ['/api/attention/events'], e: 'components/knowledge/AttentionHeatmap.tsx' },
    { p: '/knowledge/graph', t: '知识图谱', c: 'SentinelGraphPage', m: 'knowledge', s: 'ok', v: 'graph',
      d: '图谱（SVG 直排默认 + 画布模式开关）', api: ['graph 域（/api 根前缀）'],
      e: 'components/sentinel/SentinelGraphPage.tsx', caps: ['DATA-16', 'DATA-17', 'KNOW-9'] },
    { p: '/knowledge/khub', t: '资料库前厅', c: 'KnowledgeHubPage', m: 'knowledge', s: 'ok', v: 'khub',
      d: '六源聚合统计（编目/chunks/复习/漏斗/队列/门禁）', api: ['/api/knowledge/hub-stats', '/api/kl/pipeline/stats', '/api/quality/summary'],
      e: 'components/knowledge/KnowledgeHubPage.tsx（C3/DEV-0191 闭环）' },
    { p: '/knowledge/library', t: '编目室', c: 'KnowledgeLibraryPage', m: 'knowledge', s: 'ok', l: 'table',
      d: '四维筛选 + 翻页 + 掌握度列（SM-2 代理）', api: ['/api/knowledge/items', '/api/knowledge/topics', '/api/wiki/search'],
      e: 'components/knowledge/KnowledgeLibraryPage.tsx（C1/DEV-0189 闭环）' },
    { p: '/reader/:id', t: '清样深读', c: 'DeepReaderPage', m: 'knowledge', s: 'ok', v: 'reader',
      d: 'wiki 条目阅读流 + B+ 锚点批注（三态侧栏）', api: ['/api/wiki/read', '/api/annotations'],
      e: 'components/reader/DeepReaderPage.tsx（C2/DEV-0190 闭环）' },
    { p: '/reviews', t: '间隔复习', c: 'ReviewPage', m: 'knowledge', s: 'ok', l: 'list',
      d: 'SM-2 间隔复习入口', api: ['hook useReviews（/api/reviews）'], e: 'components/ReviewPage.tsx' },
    { p: '/skill-store', t: '能力包', c: 'SkillStore', m: 'knowledge', s: 'ok', v: 'skillstore',
      d: '能力资产商店（SK-01~06 + 20 内置技能）', api: ['/api/skill-registry'], e: 'components/skills/SkillStore.tsx' },
    { p: '/skill-store/:skillId', t: '技能详情', c: 'SkillDetail', m: 'knowledge', s: 'ok', l: 'detail',
      d: '技能详情 + 运行历史回放', api: ['/api/skill-registry/*'], e: 'components/skills/SkillDetail.tsx' },
    { p: '/skill-store/new', t: '创建技能', c: 'SkillBuilder', m: 'knowledge', s: 'ok', l: 'form',
      d: '4 步创建向导 + 校验', api: ['/api/skill-builder', '/api/skill-builder/validate'], e: 'components/skills/SkillBuilder.tsx' },
    { p: '/dashboard', t: '技能看板', c: 'Dashboard', m: 'knowledge', s: 'ok', l: 'board',
      d: '技能状态矩阵 / 时间线 / 健康', api: ['/api/skill-registry/runs', '/api/trigger/tickets'], e: 'components/Dashboard.tsx' },
    { p: '/tags', t: '标签加工', c: 'TagsPage', m: 'knowledge', s: 'ok', l: 'table',
      d: '标签维护与建议', api: ['/api/tags', '/api/tags/suggest'], e: 'components/TagsPage.tsx' },
    { p: '/extract', t: '抽取工具', c: 'ExtractPage', m: 'knowledge', s: 'ok', l: 'form',
      d: '正文/实体抽取预览', api: ['/api/extract', '/api/extract/hotspot', '/api/extract/knowledge', '/api/extract/preview'],
      e: 'components/ExtractPage.tsx' },
    { p: '/search', t: '统一搜索', c: 'UnifiedSearchPage', m: 'knowledge', s: 'ok', l: 'form',
      d: '跨域统一搜索（wiki FTS 7,734 条）', api: ['/api/search', '/api/wiki/search'], e: 'components/UnifiedSearchPage.tsx' },
    { p: '/secnews/knowledge', t: 'wiki 浏览', c: 'WikiBrowser', m: 'knowledge', s: 'ok', l: 'list',
      d: 'wiki 条目浏览（SecNewsShell 拆挂）', api: ['/api/secnews/knowledge', '/api/wiki'], e: 'components/WikiBrowser.tsx' },

    /* —— 行动 action（5）—— */
    { p: '/action', t: '今日行动', c: 'SentinelActionPage', m: 'action', s: 'ok', v: 'action',
      d: '四段执行指挥台 + 审批收件箱 + 副驾四卡 + SM-2 复习 + planning-actions',
      api: ['/api/kl/planning-actions', '/api/reviews/*', '/api/v1/cases', '/api/v1/proposals'],
      e: 'components/sentinel/SentinelActionPage.tsx（不再消费 /api/todos，R-13）',
      caps: ['ACT-13', 'ACT-14', 'ACT-17'] },
    { p: '/cases/:caseId', t: '案件详情', c: 'CaseDetailPage', m: 'action', s: 'ok', v: 'case',
      d: '案件工作区（overview/evidence/judgments/actions/artifacts/review 六节）',
      api: ['/api/v1/cases/{id}/aggregate', '/api/v1/judgments/*', '/api/v1/actions/*', '/api/v1/runs/*', '/api/v1/artifacts/*', '/api/v1/knowledge*'],
      e: 'components/v1/CaseDetail.tsx（壳 layer=action，?section= 定位）', caps: ['ACT-3', 'ACT-7', 'ACT-12'] },
    { p: '/action/events', t: '通稿审核', c: 'EventsReviewPage', m: 'action', s: 'ok', l: 'table',
      d: 'MP-2 事件类型候选人工审定（通过/驳回/批量）', api: ['/api/event-technique（七端点）'],
      e: 'components/events/EventsReviewPage.tsx（UNIMPLEMENTED #3 闭环）', caps: ['DATA-17'] },
    { p: '/report', t: '周报月报', c: 'ReportPage', m: 'action', s: 'ok', l: 'board',
      d: '日/周/月报告产出物', api: ['子组件：DailyReport / WeeklyReport / MonthlyReport'], e: 'components/report/ReportPage.tsx' },
    { p: '/secnews/analyze', t: '研判视图', c: 'SecNewsAnalyze', m: 'action', s: 'ok', l: 'detail',
      d: 'LLM 评估 + URL 导入 + dsh 任务', api: ['/api/llm/evaluate', '/api/kl/import/url', '/api/dsh/task'], e: 'components/SecNewsAnalyze.tsx' },

    /* —— 设置 settings（8）—— */
    { p: '/settings', t: '设置', c: 'SettingsPage', m: 'settings', s: 'ok', v: 'settings',
      d: '7 配置分区（overview/general/models/collection/network/connectivity/ops）',
      api: ['/api/settings/*', '/api/interest/*', '/api/ops/*'], e: 'components/settings/SettingsPage.tsx（修订注⑤）',
      caps: ['SET-9', 'SET-10', 'XF-25'] },
    { p: '/skills', t: '技能库配置', c: 'SkillsPage', m: 'settings', s: 'ok', l: 'list',
      d: '技能库配置（Phase 41）', api: ['hook useSkills（/api/skills）'], e: 'components/SkillsPage.tsx' },
    { p: '/secrets', t: '密钥管理', c: 'SecretsPage', m: 'settings', s: 'ok', l: 'list',
      d: '密钥保险箱（解锁/轮换/OAuth）', api: ['hook useSecrets（/api/secrets）'], e: 'components/secrets/SecretsPage.tsx' },
    { p: '/sync', t: '同步与备份', c: 'SyncPage', m: 'settings', s: 'ok', l: 'panel',
      d: 'WebDAV 同步（bundle 仅 config namespace）', api: ['/api/sync/*'], e: 'components/sync/index.tsx', g: 'sync' },
    { p: '/maint', t: '维护诊断', c: 'MaintPage', m: 'settings', s: 'ok', v: 'maint',
      d: '四卡：健康（权威契约 fail-loud）/ 清理（三档滚动）/ 索引 / 备份（compact）',
      api: ['/api/maintenance/*'], e: 'components/MaintPage.tsx（DEV-0317~0324 契约修正）' },
    { p: '/codegarden', t: 'CodeGarden', c: 'CodegardenPage', m: 'settings', s: 'ok', l: 'board',
      d: 'CodeGarden 扩展域项目板', api: ['hook useCodegardenProjects'], e: 'components/codegarden/CodegardenPage.tsx',
      g: 'codegarden', caps: ['ACT-15'] },
    { p: '/codegarden/phase2b', t: 'Phase 2b 服务网格', c: 'CodegardenPhase2bPage', m: 'settings', s: 'ok', l: 'board',
      d: '服务网格拓扑（phase2b 删除裁决待定）', api: ['hook useCodegardenServices'], e: 'components/codegarden/CodegardenPhase2bPage.tsx', g: 'codegarden_phase2b' },
    { p: '/secnews/observability', t: 'API 观测', c: 'ObservabilityTab', m: 'settings', s: 'ok', l: 'stats',
      d: 'middleware 落表可视化 + 拒收回放区块', api: ['/api/observability'], e: 'components/ObservabilityTab.tsx', caps: ['DATA-12'] },

    /* —— 无菜单（1）—— */
    { p: '/oauth-callback', t: 'OAuth 回调', c: 'OAuthCallbackPage', m: null, s: 'ok', l: 'status',
      d: '全屏授权回调状态页', api: ['/api/secrets/oauth-exchange', '/api/secrets/unlock-with-oauth'], e: 'routes/oauth-callback.tsx' }
  ];

  /* ---------- 重定向兼容（16 条，○；目标均已声明，零死链） ---------- */
  var REDIRECTS = [
    { p: '/judge', to: '/', note: 'NAV4 判断层拆解（SentinelJudgePage 物理删除）' },
    { p: '/judge/graph', to: '/knowledge/graph', note: 'NAV4 图谱迁知识菜单' },
    { p: '/cases', to: '/action', note: 'NAV4 案件列表归行动（修订注④）' },
    { p: '/garden', to: '/action', note: 'v0.8.8 R-14 泳道页退役' },
    { p: '/todos', to: '/action', note: 'v0.8.8 R-13 待办域退役（/api/todos 已删）' },
    { p: '/category/:cat', to: '/', note: 'v0.6.3 兼容' },
    { p: '/sentinel/settings', to: '/settings?cat=general', note: '兼容重定向' },
    { p: '/quality/rejection', to: '/settings?cat=ops', note: '2026-10-01 拒收日志迁设置运维区' },
    { p: '/knowledge/canvas', to: '/knowledge/graph', note: 'DEV-0295 画布 demo 退役' },
    { p: '/knowledge', to: '/knowledge/import', note: '嵌套子路由默认页', inner: true },
    { p: '/secnews', to: '/secnews/feed', note: 'SecNewsShell 拆挂兼容' },
    { p: '/secnews/image', to: '/settings?cat=models', note: '模型配置并入设置页' },
    { p: '/secnews/settings', to: '/settings?cat=collection', note: '采集配置并入设置页' },
    { p: '/workbench', to: '/', note: 'v1 四入口降级（透传 query，spec §5）' },
    { p: '/intel', to: '/', note: 'v1 四入口降级（透传 query，spec §5）' },
    { p: '*', to: '/', note: 'v0.7.1 兜底（扩展关闭时旧深链不白屏）' }
  ];

  /* ---------- 后端就绪 · 前端未接（4 个 ◐ API 域） ---------- */
  var UNCONSUMED = [
    { api: '/api/catchup', file: 'backend/api/catchup.py', note: '前端全量 grep 引用 = 0；调用方反查待做' },
    { api: '/api/feedback', file: 'backend/api/feedback_api.py', note: '前端引用 = 0' },
    { api: '/api/image', file: 'backend/api/image.py', note: '前端引用 = 0（/secnews/image 页已重定向设置页）' },
    { api: '/api/tech-stack', file: 'backend/api/tech_stack.py', note: 'gate tech_stack 默认开但无页面消费' }
  ];

  /* ---------- PRD 能力清单（92 条，源：主 PRD + v0.8.6-A + v0.8.9 PRD） ----------
   * s: ok 已上线 ｜ partial 部分/观测中 ｜ none 未实现 ｜ disc 纪律生效
   * ui: demo 落点（↗ canvas.html 对应节点） */
  var CAPS = [
    { id: 'DATA-1', d: '资讯门禁管线：质量门禁→内容门禁→规则筛选，失败 outcome 显式可追踪', s: 'ok', prd: '主PRD §3.2/§1.3 · DEV-0286', ui: '/secnews/pipeline · /quality' },
    { id: 'DATA-2', d: '首页四阅读模式后端语义（全量/精选/深度/告警）', s: 'ok', prd: '主PRD §2.4 · DEV-0236/0237', ui: '/' },
    { id: 'DATA-3', d: '精选 pick_score（quality+域boost×25+收藏源+10+时效衰减，Top-30）', s: 'ok', prd: '主PRD §2.4 · 迁移129', ui: '/' },
    { id: 'DATA-4', d: '告警=需读者执行动作（4 词表→pi 复核 action_hint→alert_events；fail-open）', s: 'ok', prd: '主PRD §2.4', ui: '/' },
    { id: 'DATA-5', d: '资讯赞/踩：状态型信号、全条目持久化、不回滚乐观态', s: 'ok', prd: '主PRD 变更记录 DEV-0311/0326', ui: '/' },
    { id: 'DATA-6', d: '兴趣引擎域归因三层化（tags→标题关键词→category 兜底）', s: 'ok', prd: '主PRD DEV-0313', ui: '/' },
    { id: 'DATA-7', d: '内容偏好三层（统计自动学习+LLM 建议+手动高级；只升降不删）', s: 'ok', prd: '主PRD DEV-0315/0316', ui: '/settings?cat=general' },
    { id: 'DATA-8', d: '非安全内容偏好通道（三案候选，未实现待裁决）', s: 'none', prd: '主PRD DEV-0314 第三批', ui: '—' },
    { id: 'DATA-9', d: 'SK-01 每日优先情报：后端/API/首页已接线；摘要缺原文/事项动作', s: 'partial', prd: '主PRD §2.4', ui: '/' },
    { id: 'DATA-10', d: '摘要降级可见性（mode/降级原因展示缺口）', s: 'none', prd: '主PRD §3.4/§7 R5', ui: '/' },
    { id: 'DATA-11', d: '拒收日志人话化（词典兜底+LLM explain）+ 迁设置运维区', s: 'ok', prd: '主PRD DEV-0238', ui: '/settings?cat=ops' },
    { id: 'DATA-12', d: '拒收回放（strict 拒绝 JOIN raw_items；缺失诚实「未留存」）', s: 'ok', prd: 'AI-Native P1-5 · DEV-0273', ui: '/secnews/observability' },
    { id: 'DATA-13', d: '语义门禁 post-ingest 化（tick 尾 LLM 判别；fail-open；reject 隐藏+flag）', s: 'ok', prd: '主PRD §2.4 · DEV-0289-F', ui: '/secnews/pipeline' },
    { id: 'DATA-14', d: '智能分类 ai_classify（规则 miss LLM 补 domain；词表严格校验）', s: 'ok', prd: '主PRD §2.4 · DEV-0270', ui: '/secnews/pipeline' },
    { id: 'DATA-15', d: 'NER 实体抽取落 knowledge_items.entities', s: 'ok', prd: '主PRD §2.4 · 迁移119', ui: '/secnews/pipeline' },
    { id: 'DATA-16', d: 'MP-1 图谱点火（244 techniques / 714 cwe_map / 17,616 edges）', s: 'ok', prd: '主PRD §2.5', ui: '/knowledge/graph' },
    { id: 'DATA-17', d: 'MP-2 事件类型 11 类（基础设施落地；候选池 owner 人审进行中）', s: 'partial', prd: '主PRD §2.5 · DEV-0328', ui: '/action/events' },
    { id: 'DATA-18', d: '类型识别与 AI 预填（历史产品定义；建项必须用户确认）', s: 'partial', prd: '主PRD 九章版 §3.2/§5.1', ui: '/action' },
    { id: 'DATA-19', d: '采集真实供给/新鲜度验收（代码已接线；运行证据未验收）', s: 'partial', prd: '主PRD §2.7 R02/§4 F0-5', ui: '/secnews/pipeline' },

    { id: 'KNOW-1', d: 'wiki-first 存储（md 真源 + FTS 7,734 条嵌入 HOT）', s: 'ok', prd: '主PRD §2.3/§6.3', ui: '/knowledge' },
    { id: 'KNOW-2', d: 'Knowledge 域对象 7 端点（发布/复查/采用）', s: 'ok', prd: '主PRD §2.2 · 迁移102', ui: '/knowledge/v1' },
    { id: 'KNOW-3', d: 'SK-05 自动召回（同类 Case 浮现已发布知识）', s: 'ok', prd: '主PRD §2.4', ui: '/cases/:caseId' },
    { id: 'KNOW-4', d: 'SK-06 复查到期 job（04:00 Shanghai）+ case blocker', s: 'ok', prd: '主PRD §2.4', ui: '/knowledge' },
    { id: 'KNOW-5', d: 'SK-04 复盘回流（case 关闭事件直连→提案→draft→publish→召回；演练⑥ PASS）', s: 'ok', prd: 'v0.8.9 §4.5 R-5 · DEV-0388', ui: '/action · /knowledge' },
    { id: 'KNOW-6', d: '知识适用条件与真实复用验证（召回/采用已有；跨案验证待做）', s: 'partial', prd: '主PRD §1.2 G4/§4 F5', ui: '/knowledge' },
    { id: 'KNOW-7', d: '资料库前厅 hub-stats 六源聚合（C3 闭环）', s: 'ok', prd: '主PRD DEV-0183/0191', ui: '/knowledge/khub' },
    { id: 'KNOW-8', d: '编目室四维筛选+翻页（复用 knowledge/items，不建新表）', s: 'ok', prd: '主PRD DEV-0183/0189', ui: '/knowledge/library' },
    { id: 'KNOW-9', d: 'InfiniteCanvas 无限画布（平移/光标锚定缩放/双击重置/点阵网格）', s: 'ok', prd: '主PRD DEV-0184', ui: '/knowledge/graph · ↗ canvas.html' },
    { id: 'KNOW-10', d: '清样深读批注（B+ 锚点四步解析/三态侧栏；migration 118 quote）', s: 'ok', prd: '主PRD DEV-0183/0190', ui: '/reader/:id' },
    { id: 'KNOW-11', d: 'Cubox 导入目录支持递归 .md（frontmatter 解析、报数透传）', s: 'ok', prd: '主PRD DEV-0327', ui: '/knowledge/import' },
    { id: 'KNOW-12', d: '真源缺列补齐（entities/compiled 进 frontmatter；roundtrip 测试）', s: 'ok', prd: 'AI-Native P2-2 · DEV-0278', ui: 'md 真源' },
    { id: 'KNOW-13', d: '旧库 3800 行 knowledge_items 迁移（待授权+备份前置）', s: 'none', prd: '主PRD §7 R9', ui: '—' },
    { id: 'KNOW-14', d: 'AI 副驾知识摘要/证据卡（实际落位 /action CopilotCards，与 /knowledge 规划有差异）', s: 'partial', prd: 'AI-Native §6.1/P1-3 · DEV-0271', ui: '/action' },

    { id: 'ACT-1', d: 'v1 九对象账本 + 3 receipt（Signal 只读无写端点）', s: 'ok', prd: '主PRD §2.2 · 迁移096~102', ui: '/action · /cases/:caseId' },
    { id: 'ACT-2', d: '审批收件箱（类型/发起方/证据数/prompt 版本/两步批准/驳回必填）', s: 'ok', prd: 'AI-Native §6.2 · DEV-0265', ui: '/action' },
    { id: 'ACT-3', d: 'AI 起草研判（ai_hub HEAVY→proposal→双签 Run→md sha256 登记）', s: 'ok', prd: 'AI-Native 用例A · DEV-0264/0267', ui: '/cases/:caseId' },
    { id: 'ACT-4', d: '副驾四卡全走提案通道（研判/知识摘要/证据召回/复盘）', s: 'ok', prd: 'AI-Native M3 · DEV-0271', ui: '/action' },
    { id: 'ACT-5', d: '四段执行指挥台（R-15）', s: 'ok', prd: 'v0.8.8 P4.5 · v0.8.9 R-1', ui: '/action' },
    { id: 'ACT-6', d: 'Run 人工回执四端点（claim/start/finish/cancel；CAS；人登记=人担保）', s: 'ok', prd: 'v0.8.9 §4.1 R-1 · DEV-0384', ui: '/action' },
    { id: 'ACT-7', d: 'Action 收口端点（running→succeeded/failed，校验 run 终态）', s: 'ok', prd: 'v0.8.9 §4.1 R-1', ui: '/cases/:caseId' },
    { id: 'ACT-8', d: 'ExecutionPlan 边界协议（默认拒绝+approve 即冻结+boundary_hash；迁移136 三列）', s: 'ok', prd: 'v0.8.9 §4.2 R-2 · DEV-0385', ui: '/action' },
    { id: 'ACT-9', d: 'pi 边界内执行（确定性 argv；pi_executor_enabled 默认关，生产开启须 owner 授权）', s: 'partial', prd: 'v0.8.9 §4.3 R-3 · DEV-0386', ui: '/action' },
    { id: 'ACT-10', d: 'L3 系统层（sandbox-exec+ulimit；仅 macOS；RLIMIT_AS 未实现）', s: 'partial', prd: 'v0.8.9 §4.4 R-4 · DEV-0387', ui: 'audit 留痕' },
    { id: 'ACT-11', d: 'L4 argv 审计+越界告警（executor.boundary_violation critical 按 run 去重）', s: 'ok', prd: 'v0.8.9 §6 · DEV-0387', ui: '/settings?cat=ops' },
    { id: 'ACT-12', d: 'Case 关闭闭环（四守卫反证演练⑤全过；运营型真实关闭）', s: 'ok', prd: 'v0.8.9 §4.5 R-5 · DEV-0384/0388', ui: '/cases/:caseId' },
    { id: 'ACT-13', d: '五类标准事项模板（历史产品定义；建项必须用户确认）', s: 'partial', prd: '主PRD 九章版 §3.2', ui: '/action' },
    { id: 'ACT-14', d: '自定义事项类型完整配置（字段/步骤/门禁/审批/模板可配）', s: 'none', prd: '主PRD §1.0/九章版 §3.2', ui: '—' },
    { id: 'ACT-15', d: 'CodeGarden 安全实践域 CP-1~4（practice_domain 列与 S1 提取未落地）', s: 'none', prd: '主PRD §2.6/§5.2', ui: '/codegarden' },
    { id: 'ACT-16', d: 'P1-0 执行器四期（由 v0.8.9 R-1~R-4 对应落地）', s: 'ok', prd: '主PRD §5.1 · v0.8.9 D1', ui: '/action' },
    { id: 'ACT-17', d: '完整事项队列可达性（CaseQueuePanel 遮蔽；总览仅前 8 条不含 blocked）', s: 'none', prd: '主PRD §2.1/§4 F0-3', ui: '/action' },
    { id: 'ACT-18', d: '观测收口（artifact_yield 口径修复+run 事件；M-9/M-10 观测窗待满）', s: 'partial', prd: 'v0.8.9 §4.6 R-6 · DEV-0384', ui: '/settings?cat=ops' },
    { id: 'ACT-19', d: '30 天主干流量目标（G2/G3/G4 ✅；G1 观测中 runs=4/artifacts=3；tag 待 owner）', s: 'partial', prd: 'v0.8.9 §1.4/§8 · DEV-0389', ui: '/settings?cat=ops' },

    { id: 'SET-1', d: '设置 7 cat/5 组 IA（纯配置心智）', s: 'ok', prd: '主PRD 九章版 §3.4 · DEV-0227', ui: '/settings' },
    { id: 'SET-2', d: '16 gate 单源（TOML 写入+audit；env 覆盖 409）', s: 'ok', prd: '主PRD 九章版 §3.4', ui: '/settings?cat=general' },
    { id: 'SET-3', d: '模型配置唯一入口（Provider/密钥/模型池/三场景；pi 主力）', s: 'ok', prd: '主PRD 九章版 §3.4 · DEV-0244/0245', ui: '/settings?cat=models' },
    { id: 'SET-4', d: 'MCP 设置（23 工具 16读+7写；gate 关零暴露双锁）', s: 'ok', prd: '主PRD 九章版 §3.4 · DEV-0289-B', ui: '/settings?cat=connectivity' },
    { id: 'SET-5', d: 'WebDAV 同步（bundle 仅 config namespace；webhook.secret 加密）', s: 'ok', prd: '主PRD 九章版 §3.4', ui: '/settings?cat=connectivity' },
    { id: 'SET-6', d: '自动入管配置 + 今日已入管数', s: 'ok', prd: '主PRD 九章版 §3.4 · DEV-0231', ui: '/settings?cat=collection' },
    { id: 'SET-7', d: '失败面板（24h failed/missed/needs_human 优先视图；空态区分真空/加载失败）', s: 'ok', prd: 'AI-Native M5/P0-5', ui: '/settings?cat=ops' },
    { id: 'SET-8', d: '/maint 四卡（健康权威契约 fail-loud/清理三档/索引/备份 compact）', s: 'ok', prd: '主PRD DEV-0317~0324', ui: '/maint' },
    { id: 'SET-9', d: '设置治理四件套（审计/策略快照已落；数据分级与出站策略未实现承诺）', s: 'partial', prd: '主PRD 九章版 §3.2/§1.1', ui: '/settings' },
    { id: 'SET-10', d: '鉴权全入口 S1（TokenAuth 覆盖 /mcp/sse /docs /openapi.json；P0 批次）', s: 'partial', prd: 'AI-Native §9.4 P0-3', ui: '后端' },
    { id: 'SET-11', d: '出站与路径加固（SSRF 阻断/0600/绝对路径；P0 批次）', s: 'partial', prd: 'AI-Native §9.4 P0-9', ui: '后端' },
    { id: 'SET-12', d: 'run.py 单实例守卫（pgid 锁+端口探活双检）', s: 'ok', prd: '主PRD DEV-0293/0294', ui: '启动闸' },
    { id: 'SET-13', d: '备份与热冷分层（backup API+manifest+sha256；主库 794→111MB）', s: 'ok', prd: '主PRD §2.3 · v0.8.8 P2.5', ui: '/maint' },
    { id: 'SET-14', d: 'dsh 启停与 :3210 降级链（not_configured→mock→ai_hub）', s: 'ok', prd: '主PRD 九章版 §3.4 · DEV-0178', ui: '/settings?cat=ops' },
    { id: 'SET-15', d: '单用户边界（组织协作/租户隔离不纳入承诺，D6）', s: 'disc', prd: '主PRD 九章版 §2.1', ui: '—' },

    { id: 'XF-1', d: 'SentinelShell 四菜单唯一壳（壳冻结 C-1；v1 对象仅以区块进入）', s: 'ok', prd: '主PRD v0.8.9 状态段', ui: '全站' },
    { id: 'XF-2', d: '管道心跳条全站常驻（pressbar：五 pipe-block + 16 源灯 + LIVE）', s: 'ok', prd: '主PRD v0.8.9 状态段', ui: '全站' },
    { id: 'XF-3', d: 'PageLayout+menuOf 自动归属（全 lazy；UTILITY_GROUPS 已物理删除）', s: 'ok', prd: '主PRD §2.1 · DEV-0168/0175', ui: '工具页' },
    { id: 'XF-4', d: '主题三态 light/dark/paper（T8 三主题人工走查未闭）', s: 'ok', prd: '主PRD DEV-0175', ui: '壳 + /settings' },
    { id: 'XF-5', d: '对话式命令栏（四类意图模板；不可识别显式列出；command_log）', s: 'ok', prd: 'AI-Native 用例B · DEV-0272', ui: 'CommandBar' },
    { id: 'XF-6', d: '质量规则两层模型（11 内置 gate + 专家规则 + AI 语义规则）', s: 'ok', prd: 'v0.8.6 · DEV-0280', ui: '/quality' },
    { id: 'XF-7', d: '三类 receipt 一等公民（证据/修订 append-only/采用回执）', s: 'ok', prd: '主PRD §2.2/§2.7 R16', ui: 'Artifact · 知识 · Case' },
    { id: 'XF-8', d: 'CAS 幂等语义（重复终态 409；revision+old_status 原子比较）', s: 'ok', prd: '主PRD R09 · v0.8.9 R-1/R-5', ui: '写路径' },
    { id: 'XF-9', d: '人主律（Agent 产出提案、人负责审批；未经审批不得成为事实）', s: 'ok', prd: '主PRD §1.3 · AI-Native §3.5', ui: '/action 审批收件箱' },
    { id: 'XF-10', d: '失败三形态收口+零静默（gate fail-open/写库失败/job misfire 显式 outcome）', s: 'ok', prd: 'v0.8.6 · DEV-0286', ui: '/settings?cat=ops' },
    { id: 'XF-11', d: 'run record 统一埋点（G1/G2 从 v1_runs/proposals/command_log 聚合）', s: 'ok', prd: 'AI-Native §4.1/§9.3', ui: '/settings?cat=ops' },
    { id: 'XF-12', d: '安全底线八条×四层防线（L1/L2/L4 全交付；L3 仅 macOS；内存上限未实现）', s: 'partial', prd: '主PRD §1.0 · v0.8.9 §6', ui: '/action · ops' },
    { id: 'XF-13', d: 'ai_hub 红线（gateway._try_order / _resolve_provider 未裁决勿动）', s: 'disc', prd: '主PRD 头部红线', ui: '后端红线' },
    { id: 'XF-14', d: 'pi 主力引擎（default_provider: pi + fallback 兜底不删除）', s: 'ok', prd: '主PRD §2.4 2026-09-27', ui: '模型层' },
    { id: 'XF-15', d: 'dsh 受管子进程（mock/ai_hub 降级可用；真 vendor 死路已裁决）', s: 'partial', prd: '主PRD §2.4 · v0.8.9 §1.1', ui: '/settings?cat=ops' },
    { id: 'XF-16', d: '存储哲学（HOT 唯一可写/WARM 只读/COLD 审计/wiki-first）', s: 'ok', prd: '主PRD §2.3 · AI-Native §4.3', ui: '数据层' },
    { id: 'XF-17', d: '迁移器幂等（duplicate column 跳过继续；X-6 只加不改）', s: 'partial', prd: 'AI-Native P0-4 · v0.8.9 §5', ui: '后端' },
    { id: 'XF-18', d: 'sync apply_bundle 事务化（deferred_commit 原子注入/整体回滚）', s: 'ok', prd: 'AI-Native P1-6 · DEV-0274', ui: '/sync' },
    { id: 'XF-19', d: 'fetch 竞态守卫（第一批 24 文件 113 处；第二批未做）', s: 'partial', prd: 'AI-Native P1-7 · DEV-0275', ui: '全站 fetch' },
    { id: 'XF-20', d: '状态库裁决（先修竞态不引 react-query/swr；lib/api+realtime.ts）', s: 'disc', prd: '主PRD §3.4 · D5', ui: '—' },
    { id: 'XF-21', d: 'i18n 维持中文硬编码（存量 120+ keys 另议）', s: 'disc', prd: 'AI-Native D4', ui: '—' },
    { id: 'XF-22', d: 'KPI 口径（分诊时延 P50/P90 + artifact 产出率；七段埋点；R-11 envelope）', s: 'ok', prd: 'v0.8.8 C · DEV-0289', ui: '/settings?cat=ops' },
    { id: 'XF-23', d: '工程纪律组（权威 PRD/架构数字门禁/core 分类/assets lint）', s: 'disc', prd: '主PRD 头部各节', ui: 'CI' },
    { id: 'XF-24', d: 'SSE 实时失效（统一 realtime 注册；生产断网恢复未验收）', s: 'partial', prd: '主PRD §2.7 R18', ui: '全站' },
    { id: 'XF-25', d: '出站诚实声明（本地运行≠数据不出域；分级/离线/外部推理限制未实现承诺）', s: 'none', prd: '主PRD §1.1/§4.3', ui: '/settings?cat=connectivity' }
  ];

  /* ---------- menuOf(pathname)：按 SentinelShell.tsx:215-234 口径简化 ---------- */
  function menuOf(p) {
    if (p === '/' || p.indexOf('/judge') === 0) return 'data';
    if (p.indexOf('/cases/') === 0) return 'action';           /* CaseDetail 壳 layer=action */
    if (/^\/(knowledge|deep|reviews|reader)/.test(p)) return 'knowledge';
    if (/^\/(action|report)/.test(p)) return 'action';
    if (/^\/(settings|secrets|sync|skills|codegarden|maint)/.test(p)) return 'settings';
    if (/^\/(tags|extract|search|dashboard|skill-store)/.test(p)) return 'knowledge';
    if (/^\/(quality|history)/.test(p)) return 'data';
    if (p.indexOf('/secnews/') === 0) {
      if (p.indexOf('/secnews/knowledge') === 0) return 'knowledge';
      if (p.indexOf('/secnews/analyze') === 0) return 'action';
      if (p.indexOf('/secnews/observability') === 0) return 'settings';
      return 'data';
    }
    return null;
  }

  return { LAYERS: LAYERS, BANDS: BANDS, GATES: GATES, ROUTES: ROUTES, REDIRECTS: REDIRECTS, UNCONSUMED: UNCONSUMED, CAPS: CAPS, menuOf: menuOf };
})();
