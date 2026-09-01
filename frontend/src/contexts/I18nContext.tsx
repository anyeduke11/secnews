import React, { createContext, useContext, useState, useEffect, useCallback, ReactNode } from 'react';

/**
 * v0.7 Batch ⑧ D6 + Batch ⑨ B9-1: 轻量 i18n 框架 (zh-CN / en-US)
 *
 * Batch ⑨ B9-1: messages dict 扩到 120+ key, 覆盖:
 * - nav (4) — 顶部导航
 * - workspace (5) — 工作台首页
 * - observability (15) — 观测面板 (D6 起 + 本批补)
 * - settings (20) — 设置 4 卡 (Pipeline/Dsh/AgentRunner/Quality)
 * - pipeline (15) — 管线观测
 * - knowledge (15) — 知识库 (Wiki/Inbox)
 * - analyze (10) — 研判 / analyze
 * - analytics (10) — 分析页 (CVE 热力图 / ATT&CK / 合规)
 * - feed (10) — Feed 视图 + 简报 + 筛选
 * - common (15) — 通用按钮/状态
 *
 * 为什么不引 react-i18next: 当前无动态内容/Plural/Gender; dict 模板能 cover
 * 所有观测/告警/设置场景, 0 依赖; 真接 i18next 的迁移点在"接入 3rd-party
 * 翻译服务"时再评估.
 *
 * 设计:
 * - 1 Context (locale / setLocale / t / toggleLocale)
 * - 2 个 messages dict (zh-CN, en-US) — 120+ key
 * - t('key.path') 用点号 lookup, 缺失返 key 自身 + console.warn
 * - localStorage 持久化, 跨刷新保持
 * - <html lang> 同步
 */
export type Locale = 'zh-CN' | 'en-US';

const STORAGE_KEY = 'hotspot-locale';

type Messages = Record<string, string>;

const messages_zhCN: Messages = {
  // ── nav (顶部) ──
  'nav.home': '首页',
  'nav.workspace': '工作台',
  'nav.observability': '观测',
  'nav.settings': '设置',
  'nav.refresh': '刷新',
  'nav.refreshing': '刷新中...',
  'nav.brand': '安全看板',
  // ── workspace 首页 ──
  'workspace.welcome': '欢迎回到 SecNews',
  'workspace.subtitle': '今日安全资讯、研判、知识库总览',
  'workspace.open_kb': '打开知识库',
  'workspace.open_pipeline': '打开管线',
  'workspace.open_analyze': '打开研判',
  // ── observability (D6 + B9-1 补) ──
  'observability.title': '观测面板 — 实时 API 健康度',
  'observability.last_1h': '最近 1 小时',
  'observability.total': '总请求',
  'observability.errors_5xx': '5xx 错误',
  'observability.error_rate': '错误率',
  'observability.p50': 'p50 延迟',
  'observability.p95': 'p95 延迟',
  'observability.top_slow_paths': 'Top 5 慢路径 (按 p95)',
  'observability.recent_events': '最近告警事件',
  'observability.loading': '正在加载观测数据…',
  'observability.error': '观测数据获取失败',
  'observability.no_data': '暂无数据',
  'observability.path_label': '路径',
  'observability.recent_20_5s': '最近 20 条 (5s 自动刷新)',
  'observability.no_events': '暂无事件',
  'observability.col_time': '时间',
  'observability.col_method': '方法',
  'observability.col_path': '路径',
  'observability.col_status': '状态',
  'observability.col_duration': '耗时',
  // ── settings 总 ──
  'settings.title': '设置',
  'settings.refresh': '刷新',
  'settings.refreshing': '刷新中...',
  'settings.load_failed': '设置面板加载失败: 后端不可达',
  'settings.load_failed_network': '设置面板加载失败: 网络或后端不可达',
  'settings.kl_pipeline': 'KL 管线',
  'settings.kl_stages': '阶段: kl:raw → refine → link → structure → publish',
  'settings.kl_meta': '重试上限: 5 次 · Kickoff 延迟: 45s · 批大小: 20',
  'settings.kl_heartbeat': '心跳消费: 每 60s drain_due(50) + 每 10min sweep',
  'settings.queue_pending': '待处理',
  'settings.queue_running': '运行中',
  'settings.queue_failed': '失败',
  'settings.model_tier': '模型档位',
  'settings.llm_master': 'LLM 总开关',
  'settings.refine_flash': 'refine / 打标',
  'settings.flash_tier': 'flash 档',
  'settings.heavy_tier': 'heavy 档（点击触发）',
  'settings.sources_count': '采集源 · {n}',
  'settings.no_sources': '暂无源数据',
  'settings.token_budget': 'token 预算',
  'settings.no_budget': '暂无预算配置（Phase 5 实装; 当前用量见底部状态栏 token 日用量）',
  // ── dsh / agent runner ──
  'dsh.connected': '已连接',
  'dsh.running_no_endpoint': '运行中 (endpoint 未响应)',
  'dsh.stopped': '已停止',
  'dsh.not_configured': '未配置启动命令',
  'dsh.cognitive_brain': 'dsh 认知大脑',
  'dsh.disabled_hint': 'dsh 扩展未启用 (feature_gates.toml dsh=false, /api/dsh/* 返回 404)。',
  'dsh.fallback_llm': '业务自动降级 LLM 直连。',
  'dsh.status_load_failed': '状态加载失败',
  'dsh.status_load_failed_network': '状态加载失败: 网络或后端不可达',
  'dsh.op_rejected': '操作被拒绝',
  'dsh.op_failed': '操作失败',
  'dsh.op_failed_network': '操作失败: 网络或后端不可达',
  'dsh.started': '已启动',
  'dsh.stopped_action': '已停止',
  'dsh.restarted': '已重启',
  'dsh.save_failed': '保存失败',
  'dsh.saved': '配置已保存',
  'dsh.save_failed_network': '保存失败: 网络或后端不可达',
  'dsh.starting': '启动中...',
  'dsh.start': '启动',
  'dsh.stopping': '停止中...',
  'dsh.stop': '停止',
  'dsh.restarting': '重启中...',
  'dsh.restart': '重启',
  'dsh.endpoint_placeholder': 'endpoint (如 http://localhost:3210)',
  'dsh.cmd_placeholder': '启动命令 (如 node /path/to/dsh/dev.mjs)',
  'dsh.autostart': 'app 启动时自动拉起',
  'dsh.saving': '保存中...',
  'dsh.save_config': '保存配置',
  'dsh.fallback_hint': 'dsh 不可达时深度分析自动降级 LLM 直连; 意外退出自动复活 (上限 3 次)',
  'dsh.pid_info': 'pid {pid} · 运行 {uptime}',
  'dsh.restart_count': ' · 自动重启 {n} 次',
  'dsh.uptime_unknown': '–',
  // ── agent runner ──
  'runner.cli_not_installed': 'CLI 未安装',
  'runner.builtin_tag': ' (内置)',
  'runner.unavailable_tag': ' ✗',
  'runner.auto_route': '自动路由 (默认 {default})',
  'runner.task_input_builtin': '任务输入 (builtin → ai_hub LLM)...',
  'runner.task_input_external': '任务书 (由 {name} 执行, timeout {timeout}s)...',
  'runner.workspace_placeholder': 'workspace (可选, 仅 codegarden/<project>/)',
  'runner.executing': '执行中...',
  'runner.execute': '执行',
  'runner.load_failed': 'runner 面板加载失败',
  'runner.load_failed_network': 'runner 面板加载失败: 网络或后端不可达',
  'runner.execute_failed': '执行失败',
  'runner.execute_failed_network': '执行失败: 网络或后端不可达',
  'runner.card_title': '执行 Agent',
  'runner.card_subtitle': 'dsh 决策 → CLI agent 执行 (三层架构执行层)',
  // ── pipeline 管线 ──
  'pipeline.title': '管线观测',
  'pipeline.data_load_failed': '管线数据加载失败',
  'pipeline.data_load_failed_network': '管线数据加载失败: 网络或后端不可达',
  'pipeline.loading': '加载中...',
  'pipeline.funnel': '管线漏斗',
  'pipeline.alive_check': '书签存活检测',
  'pipeline.alive': '存活',
  'pipeline.dead': '失效',
  'pipeline.unknown': '未知',
  'pipeline.batch_scan': '立即批扫',
  'pipeline.scanning': '批扫中...',
  'pipeline.bookmark_total': '共 {n} 条书签',
  'pipeline.queue_status': '队列状态',
  'pipeline.dlq_count': '死信队列 ({n})',
  'pipeline.col_stage': '阶段',
  'pipeline.col_item': '条目',
  'pipeline.col_error': '错误',
  'pipeline.col_retry': '重试',
  'pipeline.status_token_ledger': 'Token 台账',
  'pipeline.no_token_usage': '暂无消耗记录',
  'pipeline.col_model': '模型',
  'pipeline.col_calls': '调用',
  'pipeline.col_total': '总计',
  'pipeline.pipeline_queue': '管线队列:',
  'pipeline.token_daily': 'token 日用量:',
  // ── knowledge 知识库 ──
  'kb.title': '知识库',
  'kb.stats_load_failed': '知识库统计加载失败',
  'kb.stats_load_failed_network': '知识库统计加载失败: 网络或后端不可达',
  'kb.loading': '加载中...',
  'kb.items': '知识条目',
  'kb.concepts': '概念卡',
  'kb.lifecycle_dist': '生命周期分布',
  'kb.inbox_scanner': 'Inbox 投递区',
  'kb.inbox_hint': '将 .md 文件放入 inbox 目录，点击扫描后有效条目移入知识库，无效文件隔离到 quarantine',
  'kb.inbox_pending': '待处理 ({n})',
  'kb.scan': '扫描入库{n}',
  'kb.scanning': '扫描中...',
  'kb.scan_result_ok': '✓ 入库 {moved} 条{quarantined}',
  'kb.scan_result_quarantined': ' · 隔离 {n} 条',
  'kb.wiki_items_all': '全部 wiki items',
  'kb.search_placeholder': '搜索 wiki items...',
  'kb.no_match': '无匹配项',
  'kb.no_items': '暂无条目',
  'kb.items_load_failed_network': '条目加载失败: 网络或后端不可达',
  'kb.review_due': '复习到期 · {n}',
  // ── analyze 研判 ──
  'analyze.title': '研判',
  'analyze.url_import': 'URL 导入',
  'analyze.importing': '导入中...',
  'analyze.import': '导入',
  'analyze.import_failed_status': '导入失败 ({status})',
  'analyze.import_failed_network': '导入失败: 网络或后端不可达',
  'analyze.dsh_failed': 'dsh 研判失败 ({status})',
  'analyze.llm_failed': 'LLM 评测失败 ({status})',
  'analyze.llm_call_failed': 'LLM 调用失败',
  'analyze.failed_network': '研判失败: 网络或后端不可达',
  'analyze.placeholder': '粘贴待研判的文本...',
  'analyze.deep_analyzing': '研判中...',
  'analyze.start': '开始研判',
  'analyze.deep_dual': '深度研判 (dsh / LLM 双轨)',
  'analyze.deep_single': '深度研判 (LLM 单轨 — dsh 桥接未启用)',
  'analyze.not_executed': '未执行',
  // ── analytics 分析 ──
  'analytics.cve_heatmap': 'CVE 热力图',
  'analytics.attack_mapping': 'ATT&CK 映射',
  'analytics.compliance_matrix': '合规矩阵',
  'analytics.cve_heatmap_12w': 'CVE 时序热力图 (近 12 周)',
  'analytics.cve_heatmap_hint': '行 = severity, 列 = week; 颜色深浅 = 该周该 severity CVE 数量',
  'analytics.mitre_title': 'MITRE ATT&CK 技术映射',
  'analytics.mitre_hint': '基于 CVE → CWE → ATT&CK technique 静态映射 (嵌入 STIX 子集)',
  'analytics.mitre_data_source': ' · 数据源: 最近 {n} 条 CVE 实体',
  'analytics.mitre_empty': '知识库暂无 CVE 实体 — 先经采集/安全图谱同步入库后再刷新本页',
  'analytics.compliance_title': '合规矩阵 (等保 2.0 + GDPR + ISO 27001)',
  'analytics.compliance_hint': '事件类型 ↔ 合规条款交叉表，点击单元格查看控制项',
  'analytics.compliance_standard': '等保 2.0',
  'analytics.cve_load_failed': 'CVE 清单加载失败',
  'analytics.cve_load_failed_network': 'CVE 清单加载失败: 网络或后端不可达',
  'analytics.attack_nav_loading': '加载中...',
  'analytics.attack_nav_refresh': '刷新映射',
  'analytics.attack_nav_matched': '命中 {cves} 个 CVE, {techniques} 个技术',
  'analytics.compliance_loading': '加载合规矩阵…',
  'analytics.compliance_event_type': '事件类型',
  // ── feed ──
  'feed.headlines': '◆ 头条',
  'feed.security_news': '安全资讯',
  'feed.total_count': '共 {total} 条 · 显示 {shown} 条',
  'feed.laying_out': '正在排版…',
  'feed.check_backend': '检查后端服务后点击右上角刷新重试',
  'feed.empty_title': '暂无资讯',
  'feed.empty_hint': '调整筛选条件或等待采集管线入库',
  'feed.load_failed_status': '资讯加载失败 ({status})',
  'feed.load_failed_network': '资讯加载失败: 网络或后端不可达',
  'feed.filter_all': '全部',
  'feed.filter_security': '安全',
  'feed.filter_general': '综合',
  'feed.filter_finance': '金融',
  'feed.filter_bidding': '标讯',
  'feed.search_placeholder': '搜索关键词...',
  'feed.digest_title': '官方每日简报',
  'feed.digest_generating': '生成中...',
  'feed.digest_generate': '生成',
  'feed.digest_no_llm': '⚠ LLM 叙事未生成 (provider 不可用或生成失败) — 以下为模板摘要',
  'feed.digest_related': '关联条目: {n}',
  'feed.digest_empty': '暂无简报，点击「生成」',
  // ── common ──
  'common.refresh': '刷新',
  'common.cancel': '取消',
  'common.save': '保存',
  'common.delete': '删除',
  'common.confirm': '确认',
  'common.disabled': '已禁用',
  'common.enabled': '已启用',
  'common.search': '搜索',
  'common.filter': '筛选',
  'common.all': '全部',
  'common.loading': '加载中...',
  'common.retry': '重试',
  'common.close': '关闭',
  'common.export': '导出',
  'common.import': '导入',
  'common.yes': '是',
  'common.no': '否',
  'common.seconds': '秒',
  'common.minutes': '分钟',
};

const messages_enUS: Messages = {
  // ── nav ──
  'nav.home': 'Home',
  'nav.workspace': 'Workspace',
  'nav.observability': 'Observability',
  'nav.settings': 'Settings',
  'nav.refresh': 'Refresh',
  'nav.refreshing': 'Refreshing...',
  'nav.brand': 'SecNews',
  // ── workspace ──
  'workspace.welcome': 'Welcome back to SecNews',
  'workspace.subtitle': 'Today\u2019s security news, analysis, and knowledge base overview',
  'workspace.open_kb': 'Open Knowledge Base',
  'workspace.open_pipeline': 'Open Pipeline',
  'workspace.open_analyze': 'Open Analyze',
  // ── observability ──
  'observability.title': 'Observability — Real-time API Health',
  'observability.last_1h': 'Last 1 hour',
  'observability.total': 'Total requests',
  'observability.errors_5xx': '5xx errors',
  'observability.error_rate': 'Error rate',
  'observability.p50': 'p50 latency',
  'observability.p95': 'p95 latency',
  'observability.top_slow_paths': 'Top 5 slow paths (by p95)',
  'observability.recent_events': 'Recent alert events',
  'observability.loading': 'Loading observability data…',
  'observability.error': 'Failed to load observability data',
  'observability.no_data': 'No data',
  'observability.path_label': 'Path',
  'observability.recent_20_5s': 'Recent 20 (auto-refresh 5s)',
  'observability.no_events': 'No events',
  'observability.col_time': 'Time',
  'observability.col_method': 'Method',
  'observability.col_path': 'Path',
  'observability.col_status': 'Status',
  'observability.col_duration': 'Duration',
  // ── settings ──
  'settings.title': 'Settings',
  'settings.refresh': 'Refresh',
  'settings.refreshing': 'Refreshing...',
  'settings.load_failed': 'Settings load failed: backend unreachable',
  'settings.load_failed_network': 'Settings load failed: network or backend unreachable',
  'settings.kl_pipeline': 'KL Pipeline',
  'settings.kl_stages': 'Stages: kl:raw → refine → link → structure → publish',
  'settings.kl_meta': 'Max retries: 5 · Kickoff delay: 45s · Batch: 20',
  'settings.kl_heartbeat': 'Heartbeat: 60s drain_due(50) + 10min sweep',
  'settings.queue_pending': 'Pending',
  'settings.queue_running': 'Running',
  'settings.queue_failed': 'Failed',
  'settings.model_tier': 'Model tier',
  'settings.llm_master': 'LLM master switch',
  'settings.refine_flash': 'refine / tagging',
  'settings.flash_tier': 'flash tier',
  'settings.heavy_tier': 'heavy tier (click to trigger)',
  'settings.sources_count': 'Sources · {n}',
  'settings.no_sources': 'No source data',
  'settings.token_budget': 'Token budget',
  'settings.no_budget': 'No budget configured (Phase 5 TBD; see bottom status bar for daily token usage)',
  // ── dsh / agent runner ──
  'dsh.connected': 'Connected',
  'dsh.running_no_endpoint': 'Running (endpoint unresponsive)',
  'dsh.stopped': 'Stopped',
  'dsh.not_configured': 'Startup command not configured',
  'dsh.cognitive_brain': 'dsh Cognitive Brain',
  'dsh.disabled_hint': 'dsh extension disabled (feature_gates.toml dsh=false, /api/dsh/* returns 404).',
  'dsh.fallback_llm': 'Auto-fallback to direct LLM.',
  'dsh.status_load_failed': 'Status load failed',
  'dsh.status_load_failed_network': 'Status load failed: network or backend unreachable',
  'dsh.op_rejected': 'Operation rejected',
  'dsh.op_failed': 'Operation failed',
  'dsh.op_failed_network': 'Operation failed: network or backend unreachable',
  'dsh.started': 'Started',
  'dsh.stopped_action': 'Stopped',
  'dsh.restarted': 'Restarted',
  'dsh.save_failed': 'Save failed',
  'dsh.saved': 'Config saved',
  'dsh.save_failed_network': 'Save failed: network or backend unreachable',
  'dsh.starting': 'Starting...',
  'dsh.start': 'Start',
  'dsh.stopping': 'Stopping...',
  'dsh.stop': 'Stop',
  'dsh.restarting': 'Restarting...',
  'dsh.restart': 'Restart',
  'dsh.endpoint_placeholder': 'endpoint (e.g. http://localhost:3210)',
  'dsh.cmd_placeholder': 'startup command (e.g. node /path/to/dsh/dev.mjs)',
  'dsh.autostart': 'Auto-start with app launch',
  'dsh.saving': 'Saving...',
  'dsh.save_config': 'Save config',
  'dsh.fallback_hint': 'When dsh is unreachable, deep analysis auto-falls back to direct LLM; auto-respawn on unexpected exit (cap 3)',
  'dsh.pid_info': 'pid {pid} · uptime {uptime}',
  'dsh.restart_count': ' · auto-restart {n} times',
  'dsh.uptime_unknown': '–',
  // ── agent runner ──
  'runner.cli_not_installed': 'CLI not installed',
  'runner.builtin_tag': ' (builtin)',
  'runner.unavailable_tag': ' ✗',
  'runner.auto_route': 'Auto-route (default {default})',
  'runner.task_input_builtin': 'Task input (builtin → ai_hub LLM)...',
  'runner.task_input_external': 'Task spec (executed by {name}, timeout {timeout}s)...',
  'runner.workspace_placeholder': 'workspace (optional, only codegarden/<project>/)',
  'runner.executing': 'Executing...',
  'runner.execute': 'Execute',
  'runner.load_failed': 'Runner panel load failed',
  'runner.load_failed_network': 'Runner panel load failed: network or backend unreachable',
  'runner.execute_failed': 'Execution failed',
  'runner.execute_failed_network': 'Execution failed: network or backend unreachable',
  'runner.card_title': 'Execute Agent',
  'runner.card_subtitle': 'dsh decision → CLI agent execution (3-tier architecture exec layer)',
  // ── pipeline ──
  'pipeline.title': 'Pipeline',
  'pipeline.data_load_failed': 'Pipeline data load failed',
  'pipeline.data_load_failed_network': 'Pipeline data load failed: network or backend unreachable',
  'pipeline.loading': 'Loading...',
  'pipeline.funnel': 'Pipeline funnel',
  'pipeline.alive_check': 'Bookmark alive check',
  'pipeline.alive': 'Alive',
  'pipeline.dead': 'Dead',
  'pipeline.unknown': 'Unknown',
  'pipeline.batch_scan': 'Batch scan now',
  'pipeline.scanning': 'Scanning...',
  'pipeline.bookmark_total': 'Total {n} bookmarks',
  'pipeline.queue_status': 'Queue status',
  'pipeline.dlq_count': 'Dead-letter queue ({n})',
  'pipeline.col_stage': 'Stage',
  'pipeline.col_item': 'Item',
  'pipeline.col_error': 'Error',
  'pipeline.col_retry': 'Retry',
  'pipeline.status_token_ledger': 'Token Ledger',
  'pipeline.no_token_usage': 'No token usage yet',
  'pipeline.col_model': 'Model',
  'pipeline.col_calls': 'Calls',
  'pipeline.col_total': 'Total',
  'pipeline.pipeline_queue': 'Pipeline queue:',
  'pipeline.token_daily': 'Daily token usage:',
  // ── knowledge ──
  'kb.title': 'Knowledge Base',
  'kb.stats_load_failed': 'KB stats load failed',
  'kb.stats_load_failed_network': 'KB stats load failed: network or backend unreachable',
  'kb.loading': 'Loading...',
  'kb.items': 'Knowledge items',
  'kb.concepts': 'Concept cards',
  'kb.lifecycle_dist': 'Lifecycle distribution',
  'kb.inbox_scanner': 'Inbox drop zone',
  'kb.inbox_hint': 'Drop .md files into inbox; click scan to move valid items into KB, invalid files into quarantine',
  'kb.inbox_pending': 'Pending ({n})',
  'kb.scan': 'Scan & ingest{n}',
  'kb.scanning': 'Scanning...',
  'kb.scan_result_ok': '✓ Ingested {moved}{quarantined}',
  'kb.scan_result_quarantined': ' · quarantined {n}',
  'kb.wiki_items_all': 'All wiki items',
  'kb.search_placeholder': 'Search wiki items...',
  'kb.no_match': 'No match',
  'kb.no_items': 'No items yet',
  'kb.items_load_failed_network': 'Items load failed: network or backend unreachable',
  'kb.review_due': 'Review due · {n}',
  // ── analyze ──
  'analyze.title': 'Analyze',
  'analyze.url_import': 'URL import',
  'analyze.importing': 'Importing...',
  'analyze.import': 'Import',
  'analyze.import_failed_status': 'Import failed ({status})',
  'analyze.import_failed_network': 'Import failed: network or backend unreachable',
  'analyze.dsh_failed': 'dsh analysis failed ({status})',
  'analyze.llm_failed': 'LLM evaluation failed ({status})',
  'analyze.llm_call_failed': 'LLM call failed',
  'analyze.failed_network': 'Analysis failed: network or backend unreachable',
  'analyze.placeholder': 'Paste text to analyze...',
  'analyze.deep_analyzing': 'Analyzing...',
  'analyze.start': 'Start',
  'analyze.deep_dual': 'Deep analysis (dsh / LLM dual track)',
  'analyze.deep_single': 'Deep analysis (LLM single track — dsh bridge not enabled)',
  'analyze.not_executed': 'Not executed',
  // ── analytics ──
  'analytics.cve_heatmap': 'CVE Heatmap',
  'analytics.attack_mapping': 'ATT&CK Mapping',
  'analytics.compliance_matrix': 'Compliance Matrix',
  'analytics.cve_heatmap_12w': 'CVE time-series heatmap (last 12 weeks)',
  'analytics.cve_heatmap_hint': 'rows = severity, cols = week; color depth = CVE count for that week × severity',
  'analytics.mitre_title': 'MITRE ATT&CK Technique Mapping',
  'analytics.mitre_hint': 'Static mapping from CVE → CWE → ATT&CK technique (embedded STIX subset)',
  'analytics.mitre_data_source': ' · data source: recent {n} CVE entities',
  'analytics.mitre_empty': 'No CVE entities in KB yet — run collection/security graph sync first, then refresh',
  'analytics.compliance_title': 'Compliance Matrix (MLPS 2.0 + GDPR + ISO 27001)',
  'analytics.compliance_hint': 'Event type ↔ compliance clause cross-table; click cell for controls',
  'analytics.compliance_standard': 'MLPS 2.0',
  'analytics.cve_load_failed': 'CVE list load failed',
  'analytics.cve_load_failed_network': 'CVE list load failed: network or backend unreachable',
  'analytics.attack_nav_loading': 'Loading...',
  'analytics.attack_nav_refresh': 'Refresh mapping',
  'analytics.attack_nav_matched': 'matched {cves} CVEs, {techniques} techniques',
  'analytics.compliance_loading': 'Loading compliance matrix…',
  'analytics.compliance_event_type': 'Event type',
  // ── feed ──
  'feed.headlines': '◆ Headlines',
  'feed.security_news': 'Security News',
  'feed.total_count': '{total} total · showing {shown}',
  'feed.laying_out': 'Laying out…',
  'feed.check_backend': 'Check backend and click refresh in the top-right',
  'feed.empty_title': 'No news yet',
  'feed.empty_hint': 'Adjust filters or wait for the pipeline to ingest',
  'feed.load_failed_status': 'News load failed ({status})',
  'feed.load_failed_network': 'News load failed: network or backend unreachable',
  'feed.filter_all': 'All',
  'feed.filter_security': 'Security',
  'feed.filter_general': 'General',
  'feed.filter_finance': 'Finance',
  'feed.filter_bidding': 'Bidding',
  'feed.search_placeholder': 'Search keywords...',
  'feed.digest_title': 'Official Daily Digest',
  'feed.digest_generating': 'Generating...',
  'feed.digest_generate': 'Generate',
  'feed.digest_no_llm': '⚠ LLM narrative not generated (provider unavailable or generation failed) — template summary below',
  'feed.digest_related': 'Related items: {n}',
  'feed.digest_empty': 'No digest yet, click "Generate"',
  // ── common ──
  'common.refresh': 'Refresh',
  'common.cancel': 'Cancel',
  'common.save': 'Save',
  'common.delete': 'Delete',
  'common.confirm': 'Confirm',
  'common.disabled': 'Disabled',
  'common.enabled': 'Enabled',
  'common.search': 'Search',
  'common.filter': 'Filter',
  'common.all': 'All',
  'common.loading': 'Loading...',
  'common.retry': 'Retry',
  'common.close': 'Close',
  'common.export': 'Export',
  'common.import': 'Import',
  'common.yes': 'Yes',
  'common.no': 'No',
  'common.seconds': 's',
  'common.minutes': 'min',
};

const MESSAGES: Record<Locale, Messages> = {
  'zh-CN': messages_zhCN,
  'en-US': messages_enUS,
};

interface I18nContextValue {
  locale: Locale;
  setLocale: (l: Locale) => void;
  t: (key: string, paramsOrFallback?: Record<string, string | number> | string, fallback?: string) => string;
  toggleLocale: () => void;
}

const I18nContext = createContext<I18nContextValue>({
  locale: 'zh-CN',
  setLocale: () => {},
  t: (k) => k,
  toggleLocale: () => {},
});

export function useI18n() {
  return useContext(I18nContext);
}

function getInitialLocale(): Locale {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved === 'zh-CN' || saved === 'en-US') return saved;
  } catch {}
  try {
    if (typeof navigator !== 'undefined' && navigator.language?.startsWith('en')) {
      return 'en-US';
    }
  } catch {}
  return 'zh-CN';
}

/**
 * v0.7 Batch ⑨ B9-1: 支持 {n} / {name} 等占位符替换.
 * 用法: t('pipeline.bookmark_total', { n: 42 })
 */
function interpolate(template: string, params?: Record<string, string | number>): string {
  if (!params) return template;
  return template.replace(/\{(\w+)\}/g, (_, k) =>
    Object.prototype.hasOwnProperty.call(params, k) ? String(params[k]) : `{${k}}`,
  );
}

export function I18nProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(getInitialLocale);

  useEffect(() => {
    document.documentElement.setAttribute('lang', locale);
    try { localStorage.setItem(STORAGE_KEY, locale); } catch {}
  }, [locale]);

  const setLocale = useCallback((l: Locale) => setLocaleState(l), []);

  const toggleLocale = useCallback(() => {
    setLocaleState((cur) => (cur === 'zh-CN' ? 'en-US' : 'zh-CN'));
  }, []);

  const t = useCallback(
    (key: string, paramsOrFallback?: Record<string, string | number> | string, fallback?: string) => {
      // B9-1: 兼容 (key, fallback) 旧调用 (D6 测试) + (key, params) 新调用
      const params: Record<string, string | number> | undefined =
        typeof paramsOrFallback === 'object' && paramsOrFallback !== null
          ? paramsOrFallback
          : undefined;
      const fb: string | undefined =
        typeof paramsOrFallback === 'string' ? paramsOrFallback : fallback;

      const msg = MESSAGES[locale][key];
      if (msg) return interpolate(msg, params);
      if (locale !== 'zh-CN' && MESSAGES['zh-CN'][key]) {
        // eslint-disable-next-line no-console
        console.warn(`[i18n] key "${key}" missing in ${locale}, falling back to zh-CN`);
        return interpolate(MESSAGES['zh-CN'][key], params);
      }
      if (!MESSAGES['zh-CN'][key]) {
        // eslint-disable-next-line no-console
        console.warn(`[i18n] key "${key}" missing in all locales`);
      }
      return fb ?? key;
    },
    [locale],
  );

  return React.createElement(
    I18nContext.Provider,
    { value: { locale, setLocale, t, toggleLocale } },
    children,
  );
}
