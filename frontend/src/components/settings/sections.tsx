/**
 * settings/sections — 设置页面区段定义 (SectionKey / SectionDef / SECTIONS)。
 *
 * 拆自原 SettingsPage.tsx (1065 行): 侧边导航的区段元数据。
 * 纯结构拆分, 定义与原文件逐字等价。
 */
import React from 'react';
import { Icon } from '../Icon';

// v0.7.x SettingsHub V2: 新增 dashboard 作为首屏"体检面板", 一眼看完所有子系统状态
//   dashboard       — 首屏, 哨兵式体检: 4 系统子状态 + 8 区段跳转 + 最近 24h 趋势 (用户裁决 V2)
//   pipeline        — 原 /secnews/settings (KL/model tier/dsh/agent/源健康/token)
//   sentinel        — 原 /sentinel/settings (只读控制台 4 子面板)
//   image_models    — 原 /secnews/image (ScenarioModelsPanel 复用)
// image/sentinel/settings 三个旧路由永久 redirect → /settings?cat=...
export type SectionKey =
  | 'dashboard'
  | 'general'
  | 'collection'
  | 'network'
  | 'sync'
  | 'integration'
  | 'secrets'
  | 'alerts'
  | 'knowledge'
  | 'export'
  | 'maintenance'
  | 'pipeline'
  | 'sentinel'
  | 'image_models'
  | 'about'
  | 'feedback';

export interface SectionDef {
  key: SectionKey;
  label: string;
  icon: React.ReactNode;
  desc?: string;
}

export const SECTIONS: SectionDef[] = [
  // v0.7.x SettingsHub V2: 首屏体检面板 — 默认 cat=dashboard
  // 用途: 不点进各分类也能看到"系统还好吗", 8 张 st-tile 跳转对应 cat, 哨兵式体检
  // 不加的代价: 用户需逐个点 cat 才能确认系统状态, 心智负担大
  {
    key: 'dashboard',
    label: '总览',
    icon: <Icon size={12}><rect x="3" y="3" width="7" height="7" /><rect x="14" y="3" width="7" height="7" /><rect x="14" y="14" width="7" height="7" /><rect x="3" y="14" width="7" height="7" /></Icon>,
    desc: '首屏体检 · 8 区段快速跳转',
  },
  {
    key: 'general',
    label: '通用',
    icon: <Icon size={12}><circle cx="12" cy="12" r="3" /><path d="M12 1v3M12 20v3M4.22 4.22l2.12 2.12M17.66 17.66l2.12 2.12M1 12h3M20 12h3M4.22 19.78l2.12-2.12M17.66 6.34l2.12-2.12" /></Icon>,
    desc: '主题 / 刷新 / 维护',
  },
  {
    key: 'collection',
    label: '采集',
    icon: <Icon size={12}><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z" /></Icon>,
    desc: '质量 / 信源 / 调度',
  },
  {
    key: 'network',
    label: '网络',
    icon: <Icon size={12}><path d="M5 12.55a11 11 0 0 1 14.08 0" /><path d="M1.42 9a16 16 0 0 1 21.16 0" /><path d="M8.53 16.11a6 6 0 0 1 6.95 0" /><circle cx="12" cy="20" r="1" /></Icon>,
    desc: '代理 / 连接',
  },
  {
    key: 'sync',
    label: '同步',
    icon: <Icon size={12}><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" /></Icon>,
    desc: 'WebDAV / 跨设备',
  },
  {
    key: 'integration',
    label: '集成',
    icon: <Icon size={12}><path d="M4 17l6-6-4-4" /><path d="M12 19h8" /></Icon>,
    desc: 'MCP / 外部工具',
  },
  {
    key: 'secrets',
    label: '密钥',
    icon: <Icon size={12}><rect x="3" y="11" width="18" height="11" rx="2" ry="2" /><path d="M7 11V7a5 5 0 0 1 10 0v4" /></Icon>,
    desc: 'API Key / 凭据',
  },
  {
    key: 'alerts',
    label: '告警',
    icon: <Icon size={12}><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" /><path d="M13.73 21a2 2 0 0 1-3.46 0" /></Icon>,
    desc: '规则 / 通知',
  },
  {
    key: 'knowledge',
    label: '知识库',
    icon: <Icon size={12}><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" /><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" /></Icon>,
    desc: '同步 / 导入',
  },
  {
    key: 'export',
    label: '导出',
    icon: <Icon size={12}><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" /><polyline points="7 10 12 15 17 10" /><line x1="12" y1="15" x2="12" y2="3" /></Icon>,
    desc: '报告 / 格式',
  },
  {
    key: 'maintenance',
    label: '维护',
    icon: <Icon size={12}><path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z" /></Icon>,
    desc: 'VACUUM / 清理 / 去重',
  },
  // v0.7.x SettingsHub: 取代 /secnews/settings 独立路由
  {
    key: 'pipeline',
    label: '管线',
    icon: <Icon size={12}><path d="M3 3h18v4H3zM3 10h18v4H3zM3 17h18v4H3z" /></Icon>,
    desc: 'KL 队列 / 模型档位 / dsh / Agent / 源健康 / token 预算',
  },
  // v0.7.x SettingsHub: 取代 /sentinel/settings 独立路由 (只读, 保留 st-* 视觉)
  {
    key: 'sentinel',
    label: '哨兵',
    icon: <Icon size={12}><circle cx="12" cy="12" r="9" /><circle cx="12" cy="12" r="4" /></Icon>,
    desc: '只读控制台: 采集 / 能力 / 模型 / 危险区',
  },
  // v0.7.x SettingsHub: 取代 /secnews/image 独立路由 (ScenarioModelsPanel 同源)
  {
    key: 'image_models',
    label: '图片模型',
    icon: <Icon size={12}><rect x="3" y="3" width="18" height="18" rx="2" /><circle cx="8.5" cy="8.5" r="1.5" /><path d="M21 15l-5-5L5 21" /></Icon>,
    desc: '深度/轻度/图片 三场景模型选择',
  },
  {
    key: 'about',
    label: '关于',
    icon: <Icon size={12}><circle cx="12" cy="12" r="10" /><line x1="12" y1="16" x2="12" y2="12" /><line x1="12" y1="8" x2="12.01" y2="8" /></Icon>,
    desc: '版本 / 运行状态',
  },
  {
    key: 'feedback',
    label: '反馈画像',
    icon: <Icon size={12}><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" /></Icon>,
    desc: '点赞/点踩记录 + 角色倾向总结',
  },
];
