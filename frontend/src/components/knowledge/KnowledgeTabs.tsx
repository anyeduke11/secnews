/**
 * KnowledgeTabs — 知识管理 4 大领域导航卡片
 *
 * Phase: 知识管理重构 (4 大领域分类)
 *
 * 4 大领域:
 *  1. 信息导入 (Import)    — Cubox / 书签 / Obsidian / 冲突
 *  2. 处理数据 (Process)   — 知识图谱 / 条目 / 联邦搜索
 *  3. 知识库编译 (Compile) — LLM 编译 / 任务监控 / SOUL / 健康度
 *  4. 知识复利 (Compound)  — 学习路径 / 掌握度 / 创作草稿 / 技能入口
 *
 * 配色 token 与各子页面 accent 对齐:
 *  - import  → --color-ai (cyan, 信息流入)
 *  - process → --color-info (info, 数据处理)
 *  - compile → --color-startup (purple, 构建/编译)
 *  - compound→ --color-success (green, 复利增长)
 */
import React from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import { Icon } from '../Icon';

export type KnowledgeAreaKey = 'import' | 'process' | 'compile' | 'compound';

export interface KnowledgeAreaMeta {
  key: KnowledgeAreaKey;
  step: 1 | 2 | 3 | 4;
  title: string;
  shortTitle: string;
  description: string;
  features: string[];
  accentVar: string; // CSS var like 'var(--color-ai)'
  path: string;
}

export const KNOWLEDGE_AREAS: KnowledgeAreaMeta[] = [
  {
    key: 'import',
    step: 1,
    title: '信息导入',
    shortTitle: '导入',
    description: '多源信息流入',
    features: ['Cubox 同步', '书签导入', 'URL 验证', 'Obsidian 入口'],
    accentVar: 'var(--color-ai)',
    path: '/knowledge/import',
  },
  {
    key: 'process',
    step: 2,
    title: '处理数据',
    shortTitle: '处理',
    description: '结构化与检索',
    features: ['知识图谱', '条目筛选', '联邦搜索', '概念详情'],
    accentVar: 'var(--color-info)',
    path: '/knowledge/process',
  },
  {
    key: 'compile',
    step: 3,
    title: '知识库编译',
    shortTitle: '编译',
    description: 'LLM 提炼与运维',
    features: ['编译触发', '任务监控', 'SOUL 画像', '健康度 + 联邦'],
    accentVar: 'var(--color-startup)',
    path: '/knowledge/compile',
  },
  {
    key: 'compound',
    step: 4,
    title: '知识复利',
    shortTitle: '复利',
    description: '学习、掌握、产出',
    features: ['学习路径', '掌握度', '创作草稿', '技能入口'],
    accentVar: 'var(--color-success)',
    path: '/knowledge/compound',
  },
];

export function findAreaByPath(pathname: string): KnowledgeAreaMeta {
  const match = KNOWLEDGE_AREAS.find(a => pathname.startsWith(a.path));
  return match || KNOWLEDGE_AREAS[0];
}

interface KnowledgeTabsProps {
  /** 自定义计数 (例如各领域条目数). 不传则不显示 count. */
  counts?: Partial<Record<KnowledgeAreaKey, number | null>>;
}

export function KnowledgeTabs({ counts }: KnowledgeTabsProps) {
  const location = useLocation();
  const active = findAreaByPath(location.pathname);

  const MODE_ITEMS = [
    { key: 'briefing', label: '简报', path: '/knowledge/briefing' },
    { key: 'scan', label: '快速扫描', path: '/knowledge/scan' },
    { key: 'deep-read', label: '深度阅读', path: '/knowledge/deep-read' },
    { key: 'alert', label: '告警', path: '/knowledge/alert' },
    { key: 'outbox', label: '整理', path: '/knowledge/outbox' },
    { key: 'review', label: '复习', path: '/knowledge/review' },
  ] as const;

  return (
    <>
      <nav
        className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2.5 mb-4"
        aria-label="知识管理 4 大领域"
      >
      {KNOWLEDGE_AREAS.map(area => {
        const isActive = active.key === area.key;
        const count = counts?.[area.key];
        return (
          <NavLink
            key={area.key}
            to={area.path}
            data-area={area.key}
            data-active={isActive ? 'true' : 'false'}
            className="knowledge-area-card group focus-ring"
            style={
              {
                '--area-accent': area.accentVar,
              } as React.CSSProperties
            }
          >
            {/* 顶部 step + 标题行 */}
            <div className="flex items-center gap-2 mb-1.5">
              <span
                className="knowledge-area-step shrink-0"
                style={{
                  color: 'var(--area-accent)',
                  borderColor: 'color-mix(in srgb, var(--area-accent) 40%, transparent)',
                  backgroundColor: 'color-mix(in srgb, var(--area-accent) 8%, transparent)',
                }}
              >
                0{area.step}
              </span>
              <span
                className="text-sm font-bold truncate"
                style={{ color: 'var(--text-primary)' }}
                title={area.title}
              >
                {area.title}
              </span>
              {count != null && (
                <span
                  className="ml-auto text-[10px] font-mono tabular-nums px-1.5 py-0.5 rounded"
                  style={{
                    color: 'var(--area-accent)',
                    backgroundColor: 'color-mix(in srgb, var(--area-accent) 10%, transparent)',
                  }}
                  title="条目数"
                >
                  {count}
                </span>
              )}
            </div>

            {/* 副标题 + 描述 */}
            <p
              className="text-[11px] leading-snug mb-2"
              style={{ color: 'var(--text-secondary)' }}
            >
              {area.description}
            </p>

            {/* 特性 chips */}
            <ul className="flex flex-wrap gap-1">
              {area.features.map(f => (
                <li
                  key={f}
                  className="text-[10px] px-1.5 py-0.5 rounded-[var(--radius-sm)] font-mono"
                  style={{
                    color: isActive ? 'var(--area-accent)' : 'var(--text-muted)',
                    backgroundColor: 'var(--bg-hover)',
                    border: '1px solid var(--border-color)',
                  }}
                >
                  {f}
                </li>
              ))}
            </ul>

            {/* 激活状态指示 — 右下箭头 */}
            <span
              className="absolute right-2.5 top-2.5"
              style={{
                color: isActive ? 'var(--area-accent)' : 'var(--text-disabled)',
                opacity: isActive ? 1 : 0.45,
                transition: 'all var(--duration-fast) var(--ease-out)',
              }}
              aria-hidden="true"
            >
              <Icon size={12}>
                <polyline points="9 18 15 12 9 6" />
              </Icon>
            </span>
          </NavLink>
        );
      })}
    </nav>

      {/* Phase 13: 4 种快捷阅读模式 */}
      <div className="mb-4">
        <div className="text-[11px] font-medium mb-2" style={{ color: 'var(--text-muted)' }}>
          快捷模式
        </div>
        <div className="flex flex-wrap gap-2">
          {MODE_ITEMS.map(mode => {
            const isActive = location.pathname.startsWith(`/knowledge/${mode.key}`);
            return (
              <NavLink
                key={mode.key}
                to={mode.path}
                className="focus-ring"
                data-active={isActive ? 'true' : 'false'}
                style={{
                  padding: '5px 12px',
                  borderRadius: 'var(--radius-sm)',
                  fontSize: '12px',
                  fontWeight: 500,
                  color: isActive ? 'var(--accent)' : 'var(--text-secondary)',
                  backgroundColor: isActive ? 'color-mix(in srgb, var(--accent) 10%, transparent)' : 'var(--bg-hover)',
                  border: '1px solid',
                  borderColor: isActive ? 'color-mix(in srgb, var(--accent) 40%, transparent)' : 'var(--border-color)',
                  transition: 'all var(--duration-fast) var(--ease-out)',
                }}
              >
                {mode.label}
              </NavLink>
            );
          })}
        </div>
      </div>
    </>
  );
}
