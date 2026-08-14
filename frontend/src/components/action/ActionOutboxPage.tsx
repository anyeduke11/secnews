/**
 * ActionOutboxPage — 行动层 · 待整理
 *
 * 包装 OutboxMode 组件，添加行动层页面头部。
 * 路由: /action/outbox
 */
import React from 'react';
import { useNavigate } from 'react-router-dom';
import { OutboxMode } from '../knowledge/OutboxMode';
import { Icon } from '../Icon';

export function ActionOutboxPage() {
  const navigate = useNavigate();

  return (
    <div className="min-h-[50vh]">
      {/* 页面头部 */}
      <div className="flex items-center gap-3 mb-4 pb-3" style={{ borderBottom: '2px solid var(--text-primary)' }}>
        <button
          onClick={() => navigate('/action')}
          className="btn-ghost px-2.5 py-1.5 text-xs"
          title="返回行动层"
          aria-label="返回行动层"
        >
          <Icon size={14}>
            <line x1="19" y1="12" x2="5" y2="12" />
            <polyline points="12 19 5 12 12 5" />
          </Icon>
          返回
        </button>
        <h2 className="font-mono text-base font-bold" style={{ color: 'var(--text-primary)' }}>
          待整理
        </h2>
        <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
          行动层 · 知识整理与归档
        </span>
      </div>

      <OutboxMode />
    </div>
  );
}