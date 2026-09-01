/**
 * settings/sections — 设置页面区段定义 (SectionKey / SectionDef / SECTIONS)。
 *
 * 拆自原 SettingsPage.tsx (1065 行): 侧边导航的区段元数据。
 * 纯结构拆分, 定义与原文件逐字等价。
 */
import React from 'react';
import { Icon } from '../Icon';

export type SectionKey = 'general' | 'collection' | 'network' | 'sync' | 'integration' | 'secrets' | 'alerts' | 'knowledge' | 'export' | 'maintenance' | 'about' | 'feedback';

export interface SectionDef {
  key: SectionKey;
  label: string;
  icon: React.ReactNode;
  desc?: string;
}

export const SECTIONS: SectionDef[] = [
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
