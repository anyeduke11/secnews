/**
 * DataImportPage — 资料层知识导入页面
 *
 * Phase 2: 将 KnowledgeImport 以独立页面形式展示在资料层。
 * 添加资料层回退导航，复用 KnowledgeImport 全部功能。
 */
import React from 'react';
import { useNavigate } from 'react-router-dom';
import { Icon } from '../Icon';
import { KnowledgeImport } from '../knowledge/KnowledgeImport';

export function DataImportPage() {
  const navigate = useNavigate();

  return (
    <div className="min-h-[50vh]">
      {/* 页面头部 */}
      <div className="flex items-center gap-3 mb-4 pb-3" style={{ borderBottom: '2px solid var(--text-primary)' }}>
        <button
          onClick={() => navigate('/data')}
          className="btn-ghost px-2.5 py-1.5 text-xs"
          title="返回资料层"
          aria-label="返回资料层"
        >
          <Icon size={14}>
            <line x1="19" y1="12" x2="5" y2="12" />
            <polyline points="12 19 5 12 12 5" />
          </Icon>
          返回
        </button>
        <h2 className="font-mono text-base font-bold" style={{ color: 'var(--text-primary)' }}>
          知识导入
        </h2>
        <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
          资料层 · 信息采集
        </span>
      </div>

      {/* 复用 KnowledgeImport 全部功能 */}
      <KnowledgeImport />
    </div>
  );
}