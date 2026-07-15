import React, { useState, useEffect, useCallback } from 'react';
import { KnowledgeItem } from '../types';

interface KnowledgePageProps {
  onBack: () => void;
}

function Icon({ children, size = 14 }: { children: React.ReactNode; size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {children}
    </svg>
  );
}

export function KnowledgePage({ onBack }: KnowledgePageProps) {
  const [items, setItems] = useState<KnowledgeItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadItems = useCallback(() => {
    setLoading(true);
    setError(null);
    fetch('/api/knowledge/items?limit=50')
      .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then(data => {
        setItems(data.items || []);
        setLoading(false);
      })
      .catch(e => {
        setError(e?.message || String(e));
        setLoading(false);
      });
  }, []);

  useEffect(() => {
    loadItems();
  }, [loadItems]);

  const handleSync = () => {
    setSyncing(true);
    fetch('/api/knowledge/sync?source=cubox', { method: 'POST' })
      .then(() => loadItems())
      .catch(() => {})
      .finally(() => setSyncing(false));
  };

  return (
    <div className="knowledge-page">
      {/* 顶部标题区 */}
      <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
        <div className="flex items-center gap-3">
          <button
            onClick={onBack}
            className="btn-ghost px-2.5 py-1.5 text-xs"
            title="返回首页"
            aria-label="返回首页"
          >
            <Icon>
              <line x1="19" y1="12" x2="5" y2="12" />
              <polyline points="12 19 5 12 12 5" />
            </Icon>
            返回首页
          </button>
          <h2 className="text-base font-bold" style={{ color: 'var(--text-primary)' }}>
            📚 知识管理
          </h2>
          <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
            知识图谱 + 学习路径 + 内容创作
          </span>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handleSync}
            disabled={syncing}
            className="btn-ghost px-3 py-1.5 text-xs"
            style={{
              color: 'var(--color-ai)',
              opacity: syncing ? 0.6 : 1,
              cursor: syncing ? 'wait' : undefined,
            }}
            title="从 Cubox 同步新条目"
            aria-label={syncing ? '同步中' : '同步 Cubox'}
          >
            {syncing ? '同步中…' : '同步 Cubox'}
          </button>
        </div>
      </div>

      {/* 错误条 */}
      {error && (
        <div
          className="rounded-[var(--radius-md)] p-2.5 mb-3 text-xs"
          style={{
            backgroundColor: 'rgba(232, 93, 93, 0.12)',
            border: '1px solid #e85d5d',
            color: '#e85d5d',
          }}
        >
          加载失败: {error}
        </div>
      )}

      {/* 三栏布局 */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
        {/* 左: 知识图谱 */}
        <div
          className="rounded-[var(--radius-md)] p-4"
          style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}
        >
          <h3 className="text-sm font-semibold mb-3" style={{ color: 'var(--text-primary)' }}>
            知识图谱
          </h3>
          <div
            className="flex items-center justify-center rounded-[var(--radius-sm)]"
            style={{ height: '300px', backgroundColor: 'var(--bg-hover)', color: 'var(--text-muted)' }}
          >
            <p className="text-xs">Phase 1b: ECharts 力导向图</p>
          </div>
        </div>

        {/* 中: 学习路径 */}
        <div
          className="rounded-[var(--radius-md)] p-4"
          style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}
        >
          <h3 className="text-sm font-semibold mb-3" style={{ color: 'var(--text-primary)' }}>
            学习路径
          </h3>
          <div
            className="flex items-center justify-center rounded-[var(--radius-sm)]"
            style={{ height: '300px', backgroundColor: 'var(--bg-hover)', color: 'var(--text-muted)' }}
          >
            <p className="text-xs">Phase 1c: 学习计划 + 掌握度</p>
          </div>
        </div>

        {/* 右: 内容创作 */}
        <div
          className="rounded-[var(--radius-md)] p-4"
          style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}
        >
          <h3 className="text-sm font-semibold mb-3" style={{ color: 'var(--text-primary)' }}>
            内容创作
          </h3>
          <div
            className="flex items-center justify-center rounded-[var(--radius-sm)]"
            style={{ height: '300px', backgroundColor: 'var(--bg-hover)', color: 'var(--text-muted)' }}
          >
            <p className="text-xs">Phase 1c: 创作日历 + 13 技能入口</p>
          </div>
        </div>
      </div>

      {/* 底部: 知识条目列表 */}
      <div>
        <h3 className="text-sm font-semibold mb-3" style={{ color: 'var(--text-primary)' }}>
          知识条目 ({items.length})
        </h3>
        {loading ? (
          <p className="text-xs py-4 text-center" style={{ color: 'var(--text-muted)' }}>
            加载中…
          </p>
        ) : items.length === 0 ? (
          <p className="text-xs py-4 text-center" style={{ color: 'var(--text-muted)' }}>
            暂无条目。请先同步 Cubox 或收藏资讯。
          </p>
        ) : (
          <div className="space-y-2">
            {items.map(item => (
              <div
                key={item.id}
                className="flex items-center gap-3 p-3 rounded-[var(--radius-md)] text-xs"
                style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}
              >
                <span
                  className="px-2 py-0.5 rounded-[var(--radius-sm)] text-[10px] font-medium shrink-0"
                  style={{ backgroundColor: 'var(--bg-hover)', color: 'var(--color-ai)' }}
                >
                  {item.source}
                </span>
                <span className="flex-1 truncate" style={{ color: 'var(--text-primary)' }} title={item.title}>
                  {item.title}
                </span>
                {item.domain && (
                  <span className="shrink-0" style={{ color: 'var(--text-muted)' }}>
                    {item.domain}
                  </span>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
