/**
 * ActionSkillsPage — 行动层 · 技能管理
 *
 * 包装 SkillsPage 组件，添加行动层页面头部。
 * 路由: /action/skills
 */
import React from 'react';
import { useNavigate } from 'react-router-dom';
import { SkillsPage } from '../SkillsPage';
import { Icon } from '../Icon';

export function ActionSkillsPage() {
  const navigate = useNavigate();

  return (
    <div className="min-h-[50vh]">
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
        <h2 className="font-serif text-base font-bold" style={{ color: 'var(--text-primary)' }}>
          技能管理
        </h2>
        <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
          行动层 · 工具与技能注册
        </span>
      </div>

      <SkillsPage onBack={() => navigate('/action')} />
    </div>
  );
}