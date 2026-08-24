/**
 * KnowledgeActionBar — 知识·执行按钮组 (v0.5 c4 hotspot 竞争方案)
 *
 * 6 个执行按钮，每个映射到现有 /api 端点或路由跳转：
 *  - 出题复习     → /knowledge/review (ReviewMode 复用 SM-2 抽认卡)
 *  - 概念卡       → /knowledge/process (KnowledgeProcess 概念详情)
 *  - 写日报周报   → /api/digests/generate (POST) 触发 ai_hub 日报
 *  - 转待办       → /api/todos (POST)
 *  - KL 进度可视化 → /knowledge/compile (LifecycleProgress 复用)
 *  - 研判流打通   → /knowledge/process (KnowledgeProcess KL 阶段详情)
 *
 * 设计意图 (2026-08-23 Duke 拍板)：
 *  hotspot 仓库内的独立运行方案，与 dsh-SecNews 仓库的 AI 按钮组并列存在，
 *  作为竞争案例。不调 dsh / 不走 MCP / 不依赖外部 monorepo，
 *  全部经 hotspot 现有后端 /api/* 端点（最小化新代码）。
 *
 * 设计边界：
 *  - 纯前端按钮条组件，不引入新 store / 不发新 API
 *  - 每个按钮要么跳路由，要么 fetch 既有 /api/* 端点
 *  - 复用 Icon / 现有 mode / 现有面板
 */
import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Icon } from '../Icon';

export interface ActionButton {
  key: string;
  label: string;
  description: string;
  /** SVG 路径 (Icon size=14) */
  iconPath: React.ReactNode;
  /** 路由跳转 */
  to?: string;
  /** 调 /api/* (POST) */
  apiEndpoint?: string;
  /** api 调用方法 */
  apiMethod?: 'POST' | 'GET';
  /** api 调用 body (JSON) */
  apiBody?: Record<string, unknown>;
  /** 成功后是否显示 toast */
  showToast?: boolean;
  /** accent 颜色 (CSS var) */
  accent: 'ai' | 'info' | 'startup' | 'success' | 'warning';
}

export const KNOWLEDGE_ACTION_BUTTONS: ActionButton[] = [
  {
    key: 'review',
    label: '出题复习',
    description: 'SM-2 抽认卡，到期条目复习',
    to: '/knowledge/review',
    iconPath: (
      <>
        <path d="M9 11l3 3L22 4" />
        <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11" />
      </>
    ),
    accent: 'success',
  },
  {
    key: 'concept-card',
    label: '概念卡',
    description: '查看概念详情 + 关联条目',
    to: '/knowledge/process',
    iconPath: (
      <>
        <rect x="3" y="3" width="18" height="18" rx="2" />
        <line x1="9" y1="9" x2="15" y2="9" />
        <line x1="9" y1="13" x2="15" y2="13" />
      </>
    ),
    accent: 'info',
  },
  {
    key: 'digest',
    label: '写日报周报',
    description: 'POST /api/digests/generate',
    apiEndpoint: '/api/digests/generate',
    apiMethod: 'POST',
    apiBody: { item_ids: [], summary: '' },
    showToast: true,
    iconPath: (
      <>
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
        <polyline points="14 2 14 8 20 8" />
      </>
    ),
    accent: 'startup',
  },
  {
    key: 'todo',
    label: '转待办',
    description: 'POST /api/todos',
    apiEndpoint: '/api/todos',
    apiMethod: 'POST',
    apiBody: { source_type: 'manual', content: '从知识管理转待办', status: 'pending' },
    showToast: true,
    iconPath: (
      <>
        <polyline points="9 11 12 14 22 4" />
        <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11" />
      </>
    ),
    accent: 'warning',
  },
  {
    key: 'kl-progress',
    label: 'KL 进度',
    description: 'LifecycleProgress 可视化',
    to: '/knowledge/compile',
    iconPath: (
      <>
        <circle cx="12" cy="12" r="10" />
        <polyline points="12 6 12 12 16 14" />
      </>
    ),
    accent: 'ai',
  },
  {
    key: 'judge-flow',
    label: '研判流',
    description: 'KL T1-T4 阶段推进',
    to: '/knowledge/process',
    iconPath: (
      <>
        <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
      </>
    ),
    accent: 'ai',
  },
];

interface KnowledgeActionBarProps {
  /** 自定义按钮集合 (测试用) */
  buttons?: ActionButton[];
  /** 紧凑布局 (默认 false = 标准) */
  compact?: boolean;
}

export function KnowledgeActionBar({ buttons = KNOWLEDGE_ACTION_BUTTONS, compact = false }: KnowledgeActionBarProps) {
  const navigate = useNavigate();
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);

  const handleClick = async (btn: ActionButton) => {
    if (busyKey) return;
    if (btn.to) {
      navigate(btn.to);
      return;
    }
    if (btn.apiEndpoint) {
      setBusyKey(btn.key);
      try {
        const res = await fetch(btn.apiEndpoint, {
          method: btn.apiMethod ?? 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: btn.apiBody ? JSON.stringify(btn.apiBody) : undefined,
        });
        if (btn.showToast) {
          setToast(res.ok ? `${btn.label} 已触发` : `${btn.label} 失败 (${res.status})`);
          setTimeout(() => setToast(null), 2500);
        }
      } catch (e) {
        setToast(`${btn.label} 异常: ${(e as Error).message}`);
        setTimeout(() => setToast(null), 3000);
      } finally {
        setBusyKey(null);
      }
    }
  };

  return (
    <div
      className="knowledge-action-bar mb-4"
      data-testid="knowledge-action-bar"
      style={{
        backgroundColor: 'var(--bg-elevated)',
        border: '1px solid var(--border-color)',
        borderRadius: 'var(--radius-md)',
        padding: compact ? '8px 12px' : '12px 16px',
      }}
    >
      <div className="flex items-center gap-2 mb-2">
        <span
          className="text-[10px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded"
          style={{
            color: 'var(--text-muted)',
            backgroundColor: 'var(--bg-hover)',
            fontFamily: 'var(--font-mono)',
          }}
        >
          c4 · hotspot 独立方案
        </span>
        <span className="text-[10px]" style={{ color: 'var(--text-muted)' }}>
          知识·执行按钮组（与 dsh-SecNews P3 并列竞争）
        </span>
      </div>

      <div className={`flex flex-wrap gap-2 ${compact ? '' : 'gap-3'}`}>
        {buttons.map(btn => {
          const accentVar = `var(--color-${btn.accent})`;
          const isBusy = busyKey === btn.key;
          return (
            <button
              key={btn.key}
              type="button"
              data-button-key={btn.key}
              disabled={!!busyKey}
              onClick={() => handleClick(btn)}
              className="focus-ring"
              title={btn.description}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '6px',
                padding: compact ? '4px 10px' : '6px 14px',
                borderRadius: 'var(--radius-sm)',
                fontSize: '12px',
                fontWeight: 500,
                color: isBusy ? 'var(--text-muted)' : accentVar,
                backgroundColor: `color-mix(in srgb, ${accentVar} 8%, transparent)`,
                border: `1px solid color-mix(in srgb, ${accentVar} 40%, transparent)`,
                cursor: busyKey ? 'wait' : 'pointer',
                opacity: busyKey && !isBusy ? 0.5 : 1,
                transition: 'all var(--duration-fast) var(--ease-out)',
              }}
            >
              <Icon size={12}>{btn.iconPath}</Icon>
              <span>{btn.label}</span>
              {isBusy && (
                <span style={{ fontSize: '10px', color: 'var(--text-muted)' }}>...</span>
              )}
            </button>
          );
        })}
      </div>

      {toast && (
        <div
          role="status"
          aria-live="polite"
          style={{
            marginTop: '8px',
            padding: '6px 10px',
            borderRadius: 'var(--radius-sm)',
            fontSize: '11px',
            color: 'var(--text-secondary)',
            backgroundColor: 'var(--bg-hover)',
            border: '1px solid var(--border-color)',
          }}
        >
          {toast}
        </div>
      )}
    </div>
  );
}

export default KnowledgeActionBar;