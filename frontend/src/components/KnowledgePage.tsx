import React, { useState, useEffect, useCallback } from 'react';
import { KnowledgeItem } from '../types';
import { KnowledgeGraph } from './KnowledgeGraph';
import { SecurityGraph } from './security/SecurityGraph';
import { SecurityTimeline } from './security/SecurityTimeline';
import { ComplianceMatrix } from './security/ComplianceMatrix';
import { TermStandardizer } from './security/TermStandardizer';
import { KnowledgeFilters, FilterState } from './KnowledgeFilters';
import { HealthDashboard } from './HealthDashboard';
import { SoulViewer } from './SoulViewer';
import { LearningPanel } from './LearningPanel';
import { MasteryGauge } from './MasteryGauge';
import { ContentCalendar } from './ContentCalendar';
import { ContentDraftList } from './ContentDraftList';
import { SkillEntryGrid } from './SkillEntryGrid';
import { FederationStatus } from './FederationStatus';
import { ItemDetailDialog } from './ItemDetailDialog';
import { ConceptDetailDialog } from './ConceptDetailDialog';
import { CompileTrigger } from './CompileTrigger';
import { TaskMonitor } from './TaskMonitor';
import { BookmarkImport } from './BookmarkImport';
import { TaskSubmitDialog } from './TaskSubmitDialog';
import KnowledgeSearchBar from './KnowledgeSearchBar';

interface KnowledgePageProps {
  onBack: () => void;
}

import { Icon } from './Icon';

export function KnowledgePage({ onBack }: KnowledgePageProps) {
  const [items, setItems] = useState<KnowledgeItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [filters, setFilters] = useState<FilterState>({
    domain: '', topic: '', type: '', difficulty: '', timeRange: 'all',
  });
  const [selectedItemId, setSelectedItemId] = useState<string | null>(null);
  const [selectedSlug, setSelectedSlug] = useState<string | null>(null);
  const [taskRefreshKey, setTaskRefreshKey] = useState(0);
  const [taskDialogOpen, setTaskDialogOpen] = useState(false);
  const [syncToast, setSyncToast] = useState<{ kind: 'ok' | 'err'; msg: string } | null>(null);
  const [conflicts, setConflicts] = useState<Array<{ filename: string; size: number; mtime: number }> | null>(null);
  const [graphView, setGraphView] = useState<'concepts' | 'attack' | 'cve' | 'compliance'>('concepts');

  const loadItems = useCallback(() => {
    setLoading(true);
    setError(null);
    // Build query string from filters
    const params = new URLSearchParams({ limit: '50' });
    if (filters.domain) params.set('domain', filters.domain);
    if (filters.topic) params.set('topic', filters.topic);
    if (filters.type) params.set('type', filters.type);
    if (filters.difficulty) params.set('difficulty', filters.difficulty);
    if (filters.timeRange === 'week' || filters.timeRange === 'month') {
      const now = new Date();
      const start = new Date();
      if (filters.timeRange === 'week') start.setDate(now.getDate() - 7);
      else start.setMonth(now.getMonth() - 1);
      params.set('since', start.toISOString().split('T')[0]);
    }
    fetch(`/api/knowledge/items?${params}`)
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
  }, [filters]);

  useEffect(() => {
    loadItems();
  }, [loadItems]);

  const handleSync = () => {
    setSyncing(true);
    fetch('/api/knowledge/sync?source=cubox', { method: 'POST' })
      .then(async r => {
        const data = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(data?.detail || `HTTP ${r.status}`);
        return data;
      })
      .then(data => {
        const synced = data?.items_synced ?? 0;
        const concepts = data?.concepts_synced ?? 0;
        setSyncToast({
          kind: 'ok',
          msg: synced === 0 && concepts === 0
            ? '✓ 同步完成，无新条目'
            : `✓ 同步完成：${synced} 条目 / ${concepts} 概念`,
        });
        loadItems();
      })
      .catch(e => {
        setSyncToast({ kind: 'err', msg: `✗ 同步失败: ${e?.message || String(e)}` });
      })
      .finally(() => {
        setSyncing(false);
        setTimeout(() => setSyncToast(null), 3000);
      });
  };

  // Phase 1i Task 9.11: Obsidian vault 协议跳转
  const handleOpenObsidian = () => {
    fetch('/api/knowledge/obsidian/open', { method: 'POST' })
      .then(r => r.json())
      .then(data => {
        if (data?.url) {
          window.location.href = data.url;
        } else {
          setSyncToast({ kind: 'err', msg: '✗ Obsidian URL 缺失' });
          setTimeout(() => setSyncToast(null), 3000);
        }
      })
      .catch(e => {
        setSyncToast({ kind: 'err', msg: `✗ 打开 Obsidian 失败: ${e?.message || String(e)}` });
        setTimeout(() => setSyncToast(null), 3000);
      });
  };

  // Phase 1i Task 9.11: 查看冲突列表
  const handleViewConflicts = () => {
    if (conflicts !== null) {
      setConflicts(null);
      return;
    }
    fetch('/api/knowledge/obsidian/conflicts')
      .then(r => r.json())
      .then(data => {
        setConflicts(Array.isArray(data?.conflicts) ? data.conflicts : []);
      })
      .catch(e => {
        setSyncToast({ kind: 'err', msg: `✗ 加载冲突失败: ${e?.message || String(e)}` });
        setTimeout(() => setSyncToast(null), 3000);
      });
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
          <KnowledgeSearchBar />
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
          <BookmarkImport onImported={loadItems} />
          <button
            onClick={handleOpenObsidian}
            className="btn-ghost px-3 py-1.5 text-xs"
            style={{ color: 'var(--color-ai)' }}
            title="用 Obsidian 打开知识库"
            aria-label="打开 Obsidian"
          >
            Obsidian
          </button>
          <button
            onClick={handleViewConflicts}
            className="btn-ghost px-3 py-1.5 text-xs"
            style={{ color: conflicts !== null ? 'var(--color-error)' : 'var(--text-muted)' }}
            title="查看 watchdog 记录的冲突快照"
            aria-label="查看冲突"
          >
            {conflicts !== null ? '隐藏冲突' : '查看冲突'}
          </button>
          <CompileTrigger onTaskCreated={() => setTaskRefreshKey(k => k + 1)} />
          <button
            onClick={() => setTaskDialogOpen(true)}
            className="btn-ghost px-3 py-1.5 text-xs"
            style={{ color: 'var(--color-ai)' }}
            title="手动提交知识任务"
            aria-label="提交任务"
          >
            提交任务
          </button>
        </div>
      </div>

      {/* 错误条 */}
      {error && (
        <div
          className="rounded-[var(--radius-md)] p-2.5 mb-3 text-xs"
          style={{
            backgroundColor: 'color-mix(in srgb, var(--color-error) 12%, transparent)',
            border: '1px solid var(--color-error)',
            color: 'var(--color-error)',
          }}
        >
          加载失败: {error}
        </div>
      )}

      {/* 同步 toast */}
      {syncToast && (
        <div
          className="rounded-[var(--radius-md)] p-2.5 mb-3 text-xs"
          style={{
            backgroundColor: syncToast.kind === 'ok'
              ? 'color-mix(in srgb, var(--color-success) 12%, transparent)'
              : 'color-mix(in srgb, var(--color-error) 12%, transparent)',
            border: `1px solid ${syncToast.kind === 'ok' ? 'var(--color-success)' : 'var(--color-error)'}`,
            color: syncToast.kind === 'ok' ? 'var(--color-success)' : 'var(--color-error)',
          }}
        >
          {syncToast.msg}
        </div>
      )}

      {/* Phase 1i Task 9.11: 冲突快照列表 */}
      {conflicts !== null && (
        <div
          className="rounded-[var(--radius-md)] p-2.5 mb-3 text-xs"
          style={{
            backgroundColor: 'var(--bg-elevated)',
            border: '1px solid var(--border-color)',
            color: 'var(--text-primary)',
          }}
        >
          <div className="font-semibold mb-1.5">冲突快照 ({conflicts.length})</div>
          {conflicts.length === 0 ? (
            <p style={{ color: 'var(--text-muted)' }}>无冲突记录</p>
          ) : (
            <ul className="space-y-1">
              {conflicts.map(c => (
                <li key={c.filename} className="flex items-center gap-2">
                  <span style={{ color: 'var(--color-error)' }}>⚠</span>
                  <span className="flex-1 truncate" title={c.filename}>{c.filename}</span>
                  <span style={{ color: 'var(--text-muted)' }}>{(c.size / 1024).toFixed(1)} KB</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {/* 三栏布局 */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
        {/* 左: 知识图谱 + 健康度 + SOUL */}
        <div
          className="rounded-[var(--radius-md)] p-4 space-y-4"
          style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}
        >
          <div>
            <h3 className="text-sm font-semibold mb-2" style={{ color: 'var(--text-primary)' }}>
              知识图谱
            </h3>
            {/* Phase 5: Security Graph view switcher */}
            <div className="flex gap-1 mb-2 flex-wrap">
              {(['concepts', 'attack', 'cve', 'compliance'] as const).map(v => (
                <button
                  key={v}
                  onClick={() => setGraphView(v)}
                  className="text-[10px] px-2 py-0.5 rounded"
                  style={{
                    backgroundColor: graphView === v ? 'var(--bg-hover)' : 'transparent',
                    color: graphView === v ? 'var(--text-primary)' : 'var(--text-muted)',
                    border: '1px solid var(--border-color)',
                  }}
                >
                  {v === 'concepts' ? '概念' : v === 'attack' ? 'ATT&CK' : v === 'cve' ? 'CVE' : '合规'}
                </button>
              ))}
            </div>
            {graphView === 'concepts' && (
              <KnowledgeGraph domain={filters.domain || undefined} onSelectConcept={setSelectedSlug} />
            )}
            {graphView === 'attack' && <SecurityGraph view="attack" />}
            {graphView === 'cve' && <SecurityGraph view="cve" />}
            {graphView === 'compliance' && <ComplianceMatrix />}
          </div>
          <div>
            <h3 className="text-sm font-semibold mb-2" style={{ color: 'var(--text-primary)' }}>
              健康度
            </h3>
            <HealthDashboard />
          </div>
          <div>
            <h3 className="text-sm font-semibold mb-2" style={{ color: 'var(--text-primary)' }}>
              角色画像
            </h3>
            <SoulViewer />
          </div>
          <div>
            <h3 className="text-sm font-semibold mb-2" style={{ color: 'var(--text-primary)' }}>
              联邦状态
            </h3>
            <FederationStatus />
          </div>
        </div>

        {/* 中: 学习路径 */}
        <div
          className="rounded-[var(--radius-md)] p-4 space-y-4"
          style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}
        >
          <div>
            <h3 className="text-sm font-semibold mb-2" style={{ color: 'var(--text-primary)' }}>
              学习路径
            </h3>
            <LearningPanel />
          </div>
          <div>
            <h3 className="text-sm font-semibold mb-2" style={{ color: 'var(--text-primary)' }}>
              掌握度
            </h3>
            <MasteryGauge />
          </div>
        </div>

        {/* 右: 内容创作 */}
        <div
          className="rounded-[var(--radius-md)] p-4 space-y-4"
          style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}
        >
          <div>
            <h3 className="text-sm font-semibold mb-2" style={{ color: 'var(--text-primary)' }}>
              创作日历
            </h3>
            <ContentCalendar />
          </div>
          <div>
            <h3 className="text-sm font-semibold mb-2" style={{ color: 'var(--text-primary)' }}>
              草稿箱
            </h3>
            <ContentDraftList />
          </div>
          <div>
            <h3 className="text-sm font-semibold mb-2" style={{ color: 'var(--text-primary)' }}>
              技能入口
            </h3>
            <SkillEntryGrid />
          </div>
        </div>
      </div>

      {/* 筛选器 */}
      <div className="mb-3">
        <KnowledgeFilters onFilterChange={setFilters} />
      </div>

      {/* 任务监控 */}
      <TaskMonitor refreshKey={taskRefreshKey} />

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
                onClick={() => setSelectedItemId(item.id)}
                className="flex items-center gap-3 p-3 rounded-[var(--radius-md)] text-xs"
                style={{
                  backgroundColor: 'var(--bg-elevated)',
                  border: '1px solid var(--border-color)',
                  cursor: 'pointer',
                }}
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

      {/* 弹窗 */}
      <ItemDetailDialog item_id={selectedItemId} onClose={() => setSelectedItemId(null)} />
      <ConceptDetailDialog
        slug={selectedSlug}
        onClose={() => setSelectedSlug(null)}
        onSelectItem={setSelectedItemId}
      />
      <TaskSubmitDialog
        open={taskDialogOpen}
        onClose={() => setTaskDialogOpen(false)}
        onSubmitted={() => setTaskRefreshKey(k => k + 1)}
      />
    </div>
  );
}
