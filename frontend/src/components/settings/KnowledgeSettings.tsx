/**
 * settings/KnowledgeSettings — 知识库设置。
 *
 * 拆自原 SettingsPage.tsx (1065 行) 中 KnowledgeSettings (~501-548 行)。
 * 纯结构拆分: 状态与 fetch/渲染逻辑逐字迁移。
 */
import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';

export function KnowledgeSettings() {
  const navigate = useNavigate();
  const [stats, setStats] = useState<{ items?: number; concepts?: number; last_sync?: string } | null>(null);

  useEffect(() => {
    fetch('/api/knowledge/health')
      .then(r => r.json())
      .then(d => setStats({
        items: d.total_items || 0,
        concepts: d.total_concepts || 0,
        last_sync: undefined,
      }))
      .catch(() => {});
  }, []);

  return (
    <div className="space-y-2">
      <div className="card-base">
        <div className="px-2.5 py-1.5">
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-[11px] font-medium" style={{ color: 'var(--text-primary)' }}>知识库状态</span>
            {stats && (
              <span className="text-[9px] font-mono" style={{ color: 'var(--text-muted)' }}>
                {stats.items} 条目 · {stats.concepts} 概念
              </span>
            )}
          </div>
          {stats?.last_sync && (
            <p className="text-[9px] mb-1.5" style={{ color: 'var(--text-muted)' }}>
              最近同步: {stats.last_sync.slice(0, 16).replace('T', ' ')}
            </p>
          )}
          {!stats?.last_sync && (
            <p className="text-[9px] mb-1.5" style={{ color: 'var(--text-muted)' }}>
              知识库通过知识页面的同步功能更新
            </p>
          )}
          <button
            onClick={() => navigate('/knowledge')}
            className="btn-secondary btn-sm w-full text-center"
          >
            进入知识库
          </button>
        </div>
      </div>
    </div>
  );
}
