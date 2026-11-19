/**
 * 设置域 API 客户端 — 薄 barrel (前端重构 V1 · B8-c 拆分 / B9-a 合并, 2026-11-19)
 *
 * 契约: 组件不得直接 import getJSON/postJSON/apiFetch, 所有取数经本模块具名函数。
 * 本文件原为 847 行单体 (G5 缺口), 已按业务域拆分为 settings/* 子模块 (B8-c 11 个 →
 * B9-a 合并为 5 个); 函数体逐字未改, 消费方 import 路径保持 '../api/settings' 不变。
 *
 * 端点分组: core(系统总览/模式/能力门禁/同步) / ops(运维/历史批次/自动入管/Skill registry)
 *          / security(密钥保险箱/代理) / intelligence(兴趣画像/内容偏好/MCP/模型)
 *          / knowledge(SOUL/联邦)。
 * 质量规则与 LLM provider 切换见 ./settingsQuality。
 */
export * from './settings/core';
export * from './settings/ops';
export * from './settings/security';
export * from './settings/intelligence';
export * from './settings/knowledge';
