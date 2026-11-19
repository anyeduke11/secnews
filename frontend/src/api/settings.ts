/**
 * 设置域 API 客户端 — 薄 barrel (前端重构 V1 · B8-c, 2026-11-19)
 *
 * 契约: 组件不得直接 import getJSON/postJSON/apiFetch, 所有取数经本模块具名函数。
 * 本文件原为 847 行单体 (G5 缺口: 数据层文件超长), 已按子域拆分为 settings/* 子模块;
 * 函数体逐字未改, 消费方 import 路径保持 '../api/settings' 不变。
 *
 * 端点分组: overview(系统总览/模式/能力门禁) / sync / proxy / prefs / mcp / models /
 *          secrets / intake / ops(运维+历史批次) / knowledge(SOUL+联邦) / skillRegistry。
 * 质量规则与 LLM provider 切换见 ./settingsQuality。
 */
export * from './settings/overview';
export * from './settings/sync';
export * from './settings/proxy';
export * from './settings/prefs';
export * from './settings/mcp';
export * from './settings/models';
export * from './settings/secrets';
export * from './settings/intake';
export * from './settings/ops';
export * from './settings/knowledge';
export * from './settings/skillRegistry';
