/**
 * LayerNav — 三层顶层导航 (v2)
 *
 * Phase 5: 设计治理
 * 加入流程箭头 (data → judge → action)，层色标识，作为主导航。
 * [资料层] → [判断层] → [行动层]  │ [设置]
 */
import React from 'react';
import { useLocation, useNavigate } from 'react-router-dom';

export type LayerKey = 'data' | 'judge' | 'action';

interface LayerMeta {
  key: LayerKey;
  label: string;
  subtitle: string;
  path: string;
  color: string;        /* 层色调 */
  colorSoft: string;    /* 激活态底色 */
}

const LAYER_FLOW_COLORS = {
  data:   { color: 'var(--color-info)',   soft: 'color-mix(in srgb, var(--color-info) 10%, transparent)' },
  judge:  { color: 'var(--color-warning)', soft: 'color-mix(in srgb, var(--color-warning) 10%, transparent)' },
  action: { color: 'var(--color-general)', soft: 'color-mix(in srgb, var(--color-general) 10%, transparent)' },
} as const;

const LAYERS: LayerMeta[] = [
  { key: 'data',   label: '资料层', subtitle: '信息采集与组织',  path: '/data',   color: LAYER_FLOW_COLORS.data.color, colorSoft: LAYER_FLOW_COLORS.data.soft },
  { key: 'judge',  label: '判断层', subtitle: '筛选、分析、关联', path: '/judge',  color: LAYER_FLOW_COLORS.judge.color, colorSoft: LAYER_FLOW_COLORS.judge.soft },
  { key: 'action', label: '行动层', subtitle: '计划、学习、创作', path: '/action', color: LAYER_FLOW_COLORS.action.color, colorSoft: LAYER_FLOW_COLORS.action.soft },
];

function getCurrentLayer(pathname: string): LayerKey | null {
  if (pathname.startsWith('/data')) return 'data';
  if (pathname.startsWith('/judge')) return 'judge';
  if (pathname.startsWith('/action')) return 'action';
  return null;
}

interface LayerNavProps {
  currentLayer?: LayerKey;
  contextCategory?: string;
  /** 管线各层数据量（可选） */
  pipelineSummary?: { data: number; judge: number; action: number };
}

/** 层间箭头图标 */
function FlowArrow() {
  return (
    <span className="flex items-center shrink-0" aria-hidden="true" style={{ color: 'var(--border-color)' }}>
      <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <path d="M6 4l4 4-4 4" />
      </svg>
    </span>
  );
}

export function LayerNav({ currentLayer: forcedLayer, contextCategory, pipelineSummary }: LayerNavProps) {
  const location = useLocation();
  const navigate = useNavigate();
  const currentLayer = forcedLayer ?? getCurrentLayer(location.pathname);

  const handleLayerClick = (layer: LayerMeta) => {
    if (layer.key === currentLayer) {
      navigate(layer.path);
    } else {
      const params = contextCategory ? `?category=${contextCategory}` : '';
      navigate(layer.path + params);
    }
  };

  const isSettings = location.pathname.startsWith('/settings')
    || location.pathname.startsWith('/sync')
    || location.pathname.startsWith('/secrets');

  return (
    <nav
      className="flex items-center gap-0 overflow-x-auto max-w-full"
      style={{ scrollbarWidth: 'none' }}
      aria-label="三层导航"
    >
      {LAYERS.map((layer, i) => {
        const count = pipelineSummary?.[layer.key];
        return (
          <React.Fragment key={layer.key}>
            {/* 层间箭头（除第一个外） */}
            {i > 0 && <FlowArrow />}

            <button
              onClick={() => handleLayerClick(layer)}
              className="focus-ring transition-all flex items-center gap-1"
              style={{
                padding: '6px 12px',
                border: 'none',
                background: 'none',
                cursor: 'pointer',
                fontFamily: 'var(--font-sans)',
                fontSize: '12px',
                lineHeight: 1.4,
                borderRadius: 'var(--radius-sm)',
                color: currentLayer === layer.key ? layer.color : 'var(--text-secondary)',
                backgroundColor: currentLayer === layer.key ? layer.colorSoft : 'transparent',
                fontWeight: currentLayer === layer.key ? 700 : 400,
                letterSpacing: '0.02em',
                whiteSpace: 'nowrap',
              }}
              aria-current={currentLayer === layer.key ? 'page' : undefined}
              title={layer.subtitle}
            >
              {layer.label}
              {count !== undefined && count > 0 && (
                <span className="font-mono tabular-nums" style={{ fontSize: '10px', opacity: 0.6 }}>
                  {count}
                </span>
              )}
            </button>
          </React.Fragment>
        );
      })}

      <span className="mx-1" style={{ color: 'var(--border-color)' }} aria-hidden="true">│</span>

      <button
        onClick={() => navigate('/settings')}
        className="focus-ring transition-all"
        style={{
          padding: '6px 12px',
          border: 'none',
          background: 'none',
          cursor: 'pointer',
          fontFamily: 'var(--font-sans)',
          fontSize: '12px',
          lineHeight: 1.4,
          borderRadius: 'var(--radius-sm)',
          color: isSettings ? 'var(--accent)' : 'var(--text-muted)',
          backgroundColor: isSettings ? 'var(--accent-soft)' : 'transparent',
          fontWeight: isSettings ? 700 : 400,
          letterSpacing: '0.02em',
          whiteSpace: 'nowrap',
        }}
        aria-current={isSettings ? 'page' : undefined}
      >
        设置
      </button>
    </nav>
  );
}