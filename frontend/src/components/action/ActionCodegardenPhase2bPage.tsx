/**
 * ActionCodegardenPhase2bPage — 行动层 · CodeGarden 服务网格
 *
 * 包装 CodegardenPhase2bPage 组件，添加行动层页面头部。
 * 路由: /action/codegarden/phase2b
 */
import React from 'react';
import { useNavigate } from 'react-router-dom';
import { CodegardenPhase2bPage } from '../CodegardenPhase2bPage';
import { Icon } from '../Icon';

export function ActionCodegardenPhase2bPage() {
  const navigate = useNavigate();

  return (
    <div className="min-h-[50vh]">
      <div className="flex items-center gap-3 mb-4 pb-3" style={{ borderBottom: '2px solid var(--text-primary)' }}>
        <button
          onClick={() => navigate('/action/codegarden')}
          className="btn-ghost px-2.5 py-1.5 text-xs"
          title="返回 CodeGarden"
          aria-label="返回 CodeGarden"
        >
          <Icon size={14}>
            <line x1="19" y1="12" x2="5" y2="12" />
            <polyline points="12 19 5 12 12 5" />
          </Icon>
          返回
        </button>
        <h2 className="font-serif text-base font-bold" style={{ color: 'var(--text-primary)' }}>
          服务网格 · 资源中枢 · 联动引擎
        </h2>
        <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
          行动层 · CodeGarden Phase 2b
        </span>
      </div>

      <CodegardenPhase2bPage onBack={() => navigate('/action/codegarden')} />
    </div>
  );
}