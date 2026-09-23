/**
 * settings/sections — 设置页面区段定义 (2026-09-22 IA 重构: 17 cat → 7 cat / 5 组)
 *
 * 第一性原理: 设置页 = 用户对系统可持久化偏好的低频写入口。
 * 只读监控/数据浏览/一次性动作已按裁决迁出或删除 (见设计稿 docs/superpowers/specs/2026-09-22-settings-refactor-design.md §2)。
 *
 * overview   — 总览: 体检 + 版本/运行状态 + 跳转 (原 dashboard+about)
 * general    — 通用: 主题/模式/刷新/兴趣画像/能力开关 (原 general + sentinel tab2)
 * models     — 模型配置: LLM Provider/密钥/模型池/三场景 (新, 收 image_models+pipeline 模型部分)
 * collection — 采集与管线: 信源/质量规则/调度/KL 队列/资讯门禁
 * network    — 网络: 代理
 * connectivity — 集成与凭据: 同步/MCP/密钥状态
 * ops        — 运维: 维护/导出动作/dsh 启停
 *
 * 旧 cat 映射: dashboard→overview · image_models/pipeline(模型)→models · pipeline(队列)→collection
 *             sync/integration/secrets→connectivity · maintenance/export→ops · about→overview
 *             sentinel→general(能力开关) · feedback/knowledge/alerts→已删除
 */
import React from 'react';
import { Icon } from '../Icon';

export type SectionKey =
  | 'overview'
  | 'general'
  | 'models'
  | 'collection'
  | 'network'
  | 'connectivity'
  | 'ops';

export interface SectionDef {
  key: SectionKey;
  label: string;
  icon: React.ReactNode;
  desc?: string;
  /** B1 (DEV-0192): 内容版式提示 — form=单列全宽 (默认, 表格/表单类);
   *  mixed=多卡并排网格 (宽屏 ≥2 列, 窄屏自动回落单列, 见 settings-shell.css .set-content-mixed) */
  layout?: 'form' | 'mixed';
  /** c8: 侧边栏分组 — 仅影响导航展示, 不改 SECTIONS 顺序与内容区行为 */
  group: SectionGroup;
}

export type SectionGroup = 'overview' | 'general' | 'system' | 'connectivity' | 'ops';

export const SECTION_GROUP_LABELS: Array<{ group: SectionGroup; label: string }> = [
  { group: 'overview', label: '' },
  { group: 'general', label: '通用偏好' },
  { group: 'system', label: '系统配置' },
  { group: 'connectivity', label: '连接与凭据' },
  { group: 'ops', label: '运维' },
];

export const SECTIONS: SectionDef[] = [
  {
    key: 'overview',
    label: '总览',
    icon: <Icon size={12}><rect x="3" y="3" width="7" height="7" /><rect x="14" y="3" width="7" height="7" /><rect x="14" y="14" width="7" height="7" /><rect x="3" y="14" width="7" height="7" /></Icon>,
    desc: '体检 · 版本 · 快速跳转',
    group: 'overview',
  },
  {
    key: 'general',
    label: '通用',
    icon: <Icon size={12}><circle cx="12" cy="12" r="3" /><path d="M12 1v3M12 20v3M4.22 4.22l2.12 2.12M17.66 17.66l2.12 2.12M1 12h3M20 12h3M4.22 19.78l2.12-2.12M17.66 6.34l2.12-2.12" /></Icon>,
    desc: '主题 / 模式 / 能力开关',
    layout: 'mixed',
    group: 'general',
  },
  {
    key: 'models',
    label: '模型配置',
    icon: <Icon size={12}><rect x="4" y="4" width="16" height="16" rx="2" /><path d="M9 9h6v6H9z" /><path d="M9 2v2M15 2v2M9 20v2M15 20v2M2 9h2M2 15h2M20 9h2M20 15h2" /></Icon>,
    desc: 'LLM Provider / 密钥 / 场景模型',
    layout: 'mixed',
    group: 'system',
  },
  {
    key: 'collection',
    label: '采集与管线',
    icon: <Icon size={12}><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z" /></Icon>,
    desc: '信源 / 质量 / KL 队列 / 资讯门禁',
    layout: 'mixed',
    group: 'system',
  },
  {
    key: 'network',
    label: '网络',
    icon: <Icon size={12}><path d="M5 12.55a11 11 0 0 1 14.08 0" /><path d="M1.42 9a16 16 0 0 1 21.16 0" /><path d="M8.53 16.11a6 6 0 0 1 6.95 0" /><circle cx="12" cy="20" r="1" /></Icon>,
    desc: '代理 / 连接',
    group: 'connectivity',
  },
  {
    key: 'connectivity',
    label: '集成与凭据',
    icon: <Icon size={12}><rect x="3" y="11" width="18" height="11" rx="2" ry="2" /><path d="M7 11V7a5 5 0 0 1 10 0v4" /></Icon>,
    desc: '同步 / MCP / 主密钥',
    group: 'connectivity',
  },
  {
    key: 'ops',
    label: '运维',
    icon: <Icon size={12}><path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a2 2 0 0 1 7.94-7.94l-3.76 3.76z" /></Icon>,
    desc: '维护 / 导出 / dsh 启停',
    group: 'ops',
  },
];
