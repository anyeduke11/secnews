// frontend/src/components/CodegardenPage.tsx
import { useState, useMemo } from 'react';
import { useCodegardenProjects } from '../hooks/useCodegardenProjects';
import { ProjectBoard } from './codegarden/ProjectBoard';
import { ProjectList } from './codegarden/ProjectList';
import { ProjectDetail } from './codegarden/ProjectDetail';
import { GithubImportDialog } from './codegarden/GithubImportDialog';
import { FromKnowledgeDialog } from './codegarden/FromKnowledgeDialog';
import { BatchImportDialog } from './codegarden/BatchImportDialog';
import { CgProject, LifecycleStage, ProjectSourceType, ProjectType } from '../types/codegarden';
import { Icon } from './Icon';

type ViewMode = 'board' | 'list';

export function CodegardenPage() {
  const {
    items, total, loading, error,
    lifecycle, sourceType, projectType, keyword,
    setLifecycle, setSourceType, setProjectType, setKeyword,
    refresh, transition, syncUpstream, remove, batchRemove,
    importFromGithub, importFromKnowledge, listCandidates,
    scanLocal, scanGit, scanUpload, scanCleanup, batchImport,
  } = useCodegardenProjects();

  const [selected, setSelected] = useState<CgProject | null>(null);
  const [githubOpen, setGithubOpen] = useState(false);
  const [knowledgeOpen, setKnowledgeOpen] = useState(false);
  const [batchOpen, setBatchOpen] = useState(false);
  const [viewMode, setViewMode] = useState<ViewMode>('board');
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [toast, setToast] = useState<{ kind: 'ok' | 'err'; msg: string } | null>(null);

  const flash = (kind: 'ok' | 'err', msg: string) => {
    setToast({ kind, msg });
    setTimeout(() => setToast(null), 3000);
  };

  // 列表模式: 全局排序按 lifecycle 顺序 + name
  const sortedItems = useMemo(() => {
    if (viewMode !== 'list') return items;
    const order: LifecycleStage[] = [
      'ideation', 'prototype', 'development', 'testing', 'running', 'maintenance', 'archived', 'deprecated',
    ];
    const idx = (s: LifecycleStage) => order.indexOf(s);
    return [...items].sort((a, b) => {
      const d = idx(a.lifecycle_stage) - idx(b.lifecycle_stage);
      return d !== 0 ? d : a.name.localeCompare(b.name);
    });
  }, [items, viewMode]);

  const toggleSelect = (id: string) => {
    setSelectedIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleSelectAll = () => {
    setSelectedIds(prev => {
      const allSelected = items.length > 0 && items.every(p => prev.has(p.id));
      return allSelected ? new Set() : new Set(items.map(p => p.id));
    });
  };

  const clearSelection = () => setSelectedIds(new Set());

  const handleBatchDelete = async () => {
    if (selectedIds.size === 0) return;
    const ok = window.confirm(
      `确定删除选中的 ${selectedIds.size} 个项目？\n\n该操作不可撤销，相关的 stages / activities / links 记录会一并删除。`,
    );
    if (!ok) return;
    try {
      const result = await batchRemove(Array.from(selectedIds));
      clearSelection();
      if (result.failed.length > 0) {
        flash('err', `已删除 ${result.deleted_count} 个, 失败 ${result.failed_count} 个`);
      } else {
        flash('ok', `已删除 ${result.deleted_count} 个项目`);
      }
    } catch (e: any) {
      flash('err', e?.message || String(e));
    }
  };

  const handleDeleteOne = async (id: string) => {
    try {
      await remove(id);
      flash('ok', '已删除');
      setSelectedIds(prev => {
        if (!prev.has(id)) return prev;
        const next = new Set(prev);
        next.delete(id);
        return next;
      });
    } catch (e: any) {
      flash('err', e?.message || String(e));
    }
  };

  return (
    <div className="codegarden-page">
      {/* 顶部标题区 */}
      <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
        <div className="flex items-center gap-3">
          <h2 className="text-base font-bold" style={{ color: 'var(--text-primary)' }}>
            🌱 CodeGarden
          </h2>
          <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
            vibecoding 工作台 + 二开项目管理
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs" style={{ color: 'var(--text-muted)' }}>共 {total} 项</span>
          <button
            onClick={() => setKnowledgeOpen(true)}
            className="btn-ghost px-3 py-1.5 text-xs"
            style={{ color: 'var(--color-ai)' }}
          >
            + 从知识库
          </button>
          <button
            onClick={() => setGithubOpen(true)}
            className="btn-ghost px-3 py-1.5 text-xs"
            style={{ color: 'var(--color-ai)' }}
          >
            + GitHub 导入
          </button>
          <button
            onClick={() => setBatchOpen(true)}
            className="btn-ghost px-3 py-1.5 text-xs"
            style={{ color: 'var(--color-ai)', borderColor: 'var(--color-ai)' }}
            title="扫描本地目录 / Git 仓库 / 压缩包, 批量导入多个项目"
          >
            + 批量导入
          </button>
          <button
            onClick={refresh}
            className="btn-ghost px-2 py-1.5 text-xs"
            title="刷新"
          >
            <Icon>
              <polyline points="23 4 23 10 17 10" />
              <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
            </Icon>
          </button>
        </div>
      </div>

      {/* 过滤器 */}
      <div className="flex items-center gap-2 mb-3 flex-wrap">
        <select
          value={lifecycle}
          onChange={(e) => setLifecycle(e.target.value as LifecycleStage | 'all')}
          className="text-[11px] px-2 py-1 rounded"
          style={{ backgroundColor: 'var(--bg-hover)', color: 'var(--text-primary)', border: '1px solid var(--border-color)' }}
        >
          <option value="all">全部状态</option>
          <option value="ideation">构想中</option>
          <option value="prototype">原型</option>
          <option value="development">开发中</option>
          <option value="testing">测试中</option>
          <option value="running">运行中</option>
          <option value="maintenance">维护中</option>
          <option value="archived">已归档</option>
          <option value="deprecated">已废弃</option>
        </select>
        <select
          value={sourceType}
          onChange={(e) => setSourceType(e.target.value as ProjectSourceType | 'all')}
          className="text-[11px] px-2 py-1 rounded"
          style={{ backgroundColor: 'var(--bg-hover)', color: 'var(--text-primary)', border: '1px solid var(--border-color)' }}
        >
          <option value="all">全部来源</option>
          <option value="vibe">原创</option>
          <option value="fork">Fork</option>
          <option value="imported">导入</option>
          <option value="reference">参考</option>
        </select>
        <select
          value={projectType}
          onChange={(e) => setProjectType(e.target.value as ProjectType | 'all')}
          className="text-[11px] px-2 py-1 rounded"
          style={{ backgroundColor: 'var(--bg-hover)', color: 'var(--text-primary)', border: '1px solid var(--border-color)' }}
        >
          <option value="all">全部类型</option>
          <option value="web_application">web_application</option>
          <option value="api_service">api_service</option>
          <option value="cli">cli</option>
          <option value="crawler">crawler</option>
          <option value="library">library</option>
          <option value="experiment">experiment</option>
        </select>
        <input
          value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
          placeholder="搜索 name / description"
          className="text-[11px] px-2 py-1 rounded flex-1 min-w-[180px]"
          style={{ backgroundColor: 'var(--bg-hover)', color: 'var(--text-primary)', border: '1px solid var(--border-color)' }}
        />
        {/* 视图切换 */}
        <div
          className="flex items-center rounded text-[11px]"
          style={{ border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-hover)' }}
        >
          <button
            onClick={() => setViewMode('board')}
            className="px-2.5 py-1 rounded-l"
            style={{
              backgroundColor: viewMode === 'board' ? 'var(--bg-elevated)' : 'transparent',
              color: viewMode === 'board' ? 'var(--text-primary)' : 'var(--text-muted)',
            }}
            title="看板视图"
          >
            ▦ 看板
          </button>
          <button
            onClick={() => setViewMode('list')}
            className="px-2.5 py-1 rounded-r"
            style={{
              backgroundColor: viewMode === 'list' ? 'var(--bg-elevated)' : 'transparent',
              color: viewMode === 'list' ? 'var(--text-primary)' : 'var(--text-muted)',
            }}
            title="列表视图"
          >
            ☰ 列表
          </button>
        </div>
      </div>

      {/* 选择工具栏 (仅当有选中时显示) */}
      {selectedIds.size > 0 && (
        <div
          className="flex items-center gap-2 mb-2 px-3 py-1.5 rounded-[var(--radius-sm)] text-xs animate-fade-in-only"
          style={{
            backgroundColor: 'var(--bg-elevated)',
            border: '1px solid var(--color-ai)',
            color: 'var(--text-primary)',
          }}
        >
          <span className="font-mono">已选 {selectedIds.size} 项</span>
          <span style={{ color: 'var(--text-muted)' }}>·</span>
          <button
            onClick={toggleSelectAll}
            className="text-[11px] px-2 py-0.5 rounded"
            style={{ border: '1px solid var(--border-color)', color: 'var(--text-secondary)' }}
          >
            {items.every(p => selectedIds.has(p.id)) ? '取消全选' : '全选当前页'}
          </button>
          <button
            onClick={clearSelection}
            className="text-[11px] px-2 py-0.5 rounded"
            style={{ color: 'var(--text-muted)' }}
          >
            清空
          </button>
          <div className="flex-1" />
          <button
            onClick={handleBatchDelete}
            className="text-[11px] px-3 py-1 rounded font-semibold"
            style={{
              backgroundColor: '#e85d5d',
              color: '#fff',
              border: '1px solid #e85d5d',
            }}
            title="批量删除选中项目（不可撤销）"
          >
            删除 {selectedIds.size} 项
          </button>
        </div>
      )}

      {/* 主内容 */}
      {loading ? (
        <div className="text-xs text-center py-6" style={{ color: 'var(--text-muted)' }}>加载中…</div>
      ) : error ? (
        <div className="text-xs text-center py-6" style={{ color: '#e85d5d' }}>{error}</div>
      ) : items.length === 0 ? (
        <div className="text-xs text-center py-6" style={{ color: 'var(--text-muted)' }}>
          暂无项目，点击右上角 + 添加
        </div>
      ) : viewMode === 'board' ? (
        <ProjectBoard
          items={items}
          onSelect={setSelected}
          onTransition={(id, to) => transition(id, to).catch(e => flash('err', e?.message || e))}
          selectedIds={selectedIds}
          selectable
          onToggleSelect={toggleSelect}
        />
      ) : (
        <ProjectList
          items={sortedItems}
          selectedIds={selectedIds}
          onSelect={setSelected}
          onToggleSelect={toggleSelect}
          onToggleAll={toggleSelectAll}
          onTransition={(id, to) => transition(id, to).catch(e => flash('err', e?.message || e))}
        />
      )}

      {/* 详情弹窗 */}
      {selected && (
        <ProjectDetail
          project={selected}
          onClose={() => setSelected(null)}
          onTransition={transition}
          onSync={syncUpstream}
          onDelete={async (id) => { await handleDeleteOne(id); setSelected(null); }}
        />
      )}

      {/* GitHub 导入弹窗 */}
      <GithubImportDialog
        open={githubOpen}
        onClose={() => setGithubOpen(false)}
        onImported={refresh}
        importFn={importFromGithub}
      />

      {/* 从知识库导入弹窗 */}
      <FromKnowledgeDialog
        open={knowledgeOpen}
        onClose={() => setKnowledgeOpen(false)}
        onImported={refresh}
        listCandidates={listCandidates}
        importFn={importFromKnowledge}
      />

      {/* 批量导入弹窗 (Phase 1: 3 路径源 + 批量导入骨架) */}
      <BatchImportDialog
        open={batchOpen}
        onClose={() => setBatchOpen(false)}
        onImported={refresh}
        scanLocalFn={scanLocal}
        scanGitFn={scanGit}
        scanUploadFn={scanUpload}
        scanCleanupFn={scanCleanup}
        batchImportFn={batchImport}
      />

      {/* 底部 toast */}
      {toast && (
        <div
          className="fixed bottom-4 left-1/2 -translate-x-1/2 px-3 py-1.5 rounded-[var(--radius-sm)] text-xs animate-fade-in-only z-50"
          style={{
            backgroundColor: toast.kind === 'ok' ? '#00c96a' : '#e85d5d',
            color: '#fff',
          }}
        >
          {toast.msg}
        </div>
      )}
    </div>
  );
}
