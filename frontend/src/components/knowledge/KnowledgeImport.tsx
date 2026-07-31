/**
 * KnowledgeImport — 信息导入子页面
 *
 * 涵盖多源信息采集:
 *  - Cubox 同步 (含实时进度)
 *  - 浏览器书签导入 (JSON / HTML, 可选 URL 验证)
 *  - 打开 Obsidian 知识库
 *  - 查看同步冲突快照
 */
import React, { useState, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { Icon } from '../Icon';
import { BookmarkImport } from '../BookmarkImport';
import { KNOWLEDGE_AREAS } from './KnowledgeTabs';

const PHASE_LABELS: Record<string, string> = {
  pending: '等待执行 ...',
  connecting: '连接 Cubox ...',
  fetching: '获取卡片列表 ...',
  processing: '处理条目',
  syncing_db: '同步数据库 ...',
  done: '完成',
};

export function KnowledgeImport() {
  const navigate = useNavigate();
  const [syncing, setSyncing] = useState(false);
  const [syncPhase, setSyncPhase] = useState('');
  const [syncCurrent, setSyncCurrent] = useState(0);
  const [syncTotal, setSyncTotal] = useState(0);
  const [syncElapsed, setSyncElapsed] = useState(0);
  const syncStartRef = useRef(0);
  const syncPollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const [toast, setToast] = useState<{ kind: 'ok' | 'err'; msg: string } | null>(null);
  const [conflicts, setConflicts] = useState<Array<{ filename: string; size: number; mtime: number }> | null>(null);

  const area = KNOWLEDGE_AREAS.find(a => a.key === 'import')!;

  const stopSyncProgress = () => {
    if (syncPollRef.current) {
      clearInterval(syncPollRef.current);
      syncPollRef.current = null;
    }
  };

  const flashToast = (t: { kind: 'ok' | 'err'; msg: string }) => {
    setToast(t);
    setTimeout(() => setToast(null), 5000);
  };

  const handleSync = () => {
    setSyncing(true);
    setSyncPhase('pending');
    setSyncCurrent(0);
    setSyncTotal(0);
    setSyncElapsed(0);
    syncStartRef.current = Date.now();

    const elapsedTimer = setInterval(() => {
      setSyncElapsed(Math.round((Date.now() - syncStartRef.current) / 1000));
    }, 1000);

    fetch('/api/knowledge/sync?source=cubox', { method: 'POST' })
      .then(async r => {
        const data = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(data?.detail || `HTTP ${r.status}`);
        return data;
      })
      .then(data => {
        const taskId = data?.task_id;
        if (!taskId) throw new Error('no task_id returned');
        syncPollRef.current = setInterval(() => {
          fetch(`/api/knowledge/tasks/${taskId}`)
            .then(r => r.json())
            .then(task => {
              const params = task?.params || {};
              const phase = params?.phase || task?.status || 'pending';
              setSyncPhase(phase);
              setSyncCurrent(params?.current || 0);
              setSyncTotal(params?.total || 0);
              if (task?.status === 'done') {
                clearInterval(elapsedTimer);
                stopSyncProgress();
                const result = params?.result || {};
                const newCount = result?.new ?? 0;
                const merged = result?.merged ?? 0;
                const total = newCount + merged;
                const elapsed = Math.round((Date.now() - syncStartRef.current) / 1000);
                flashToast({
                  kind: 'ok',
                  msg: total === 0
                    ? `✓ 同步完成，无新条目 (${elapsed}s)`
                    : `✓ 同步完成：${newCount} 新增 / ${merged} 合并 (${elapsed}s)`,
                });
                setSyncing(false);
                setSyncPhase('done');
                setTimeout(() => setSyncPhase(''), 1000);
              } else if (task?.status === 'failed') {
                clearInterval(elapsedTimer);
                stopSyncProgress();
                flashToast({ kind: 'err', msg: `✗ 同步失败: ${task?.error_message || '未知错误'}` });
                setSyncing(false);
              }
            })
            .catch(() => { /* 轮询网络错误忽略 */ });
        }, 1500);
      })
      .catch(e => {
        clearInterval(elapsedTimer);
        stopSyncProgress();
        flashToast({ kind: 'err', msg: `✗ 同步失败: ${e?.message || String(e)}` });
        setSyncing(false);
      });
  };

  const handleOpenObsidian = () => {
    fetch('/api/knowledge/obsidian/open', { method: 'POST' })
      .then(r => r.json())
      .then(data => {
        if (data?.url) {
          window.location.href = data.url;
        } else {
          flashToast({ kind: 'err', msg: '✗ Obsidian URL 缺失' });
        }
      })
      .catch(e => {
        flashToast({ kind: 'err', msg: `✗ 打开 Obsidian 失败: ${e?.message || String(e)}` });
      });
  };

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
        flashToast({ kind: 'err', msg: `✗ 加载冲突失败: ${e?.message || String(e)}` });
      });
  };

  return (
    <div
      className="space-y-3"
      style={
        {
          '--area-accent': area.accentVar,
        } as React.CSSProperties
      }
      data-area-page="import"
    >
      {/* 区域介绍 hero */}
      <section
        className="rounded-[var(--radius-md)] p-3.5"
        style={{
          backgroundColor: 'var(--bg-elevated)',
          border: '1px solid var(--border-color)',
          borderLeft: '3px solid var(--area-accent)',
        }}
      >
        <div className="flex items-start gap-3">
          <div
            className="w-9 h-9 rounded-md flex items-center justify-center shrink-0"
            style={{
              backgroundColor: 'color-mix(in srgb, var(--area-accent) 12%, transparent)',
              color: 'var(--area-accent)',
            }}
          >
            <Icon size={18}>
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
              <polyline points="7 10 12 15 17 10" />
              <line x1="12" y1="15" x2="12" y2="3" />
            </Icon>
          </div>
          <div className="flex-1 min-w-0">
            <h3
              className="text-sm font-bold mb-0.5"
              style={{ color: 'var(--text-primary)' }}
            >
              信息导入 · 多源采集入口
            </h3>
            <p className="text-xs leading-relaxed" style={{ color: 'var(--text-secondary)' }}>
              从 Cubox 收藏夹、浏览器书签、外部 URL 等多源采集原始素材，
              经 <span style={{ color: 'var(--area-accent)' }}>去重 + 验证</span> 后写入知识条目池。
            </p>
          </div>
        </div>
      </section>

      {/* 同步进度条 */}
      {syncing && (
        <div
          className="rounded-[var(--radius-md)] p-3 text-xs"
          style={{
            backgroundColor: 'color-mix(in srgb, var(--area-accent) 8%, transparent)',
            border: '1px solid var(--area-accent)',
          }}
        >
          <div className="flex items-center justify-between mb-1.5">
            <span className="flex items-center gap-2" style={{ color: 'var(--area-accent)' }}>
              <span className="inline-block w-3 h-3 border-2 border-current border-t-transparent rounded-full animate-spin" />
              {PHASE_LABELS[syncPhase] || syncPhase}
              {syncPhase === 'processing' && syncTotal > 0 && (
                <span style={{ color: 'var(--text-muted)' }}>
                  ({syncCurrent}/{syncTotal})
                </span>
              )}
            </span>
            <span style={{ color: 'var(--text-muted)' }}>{syncElapsed}s</span>
          </div>
          {syncPhase === 'processing' && syncTotal > 0 ? (
            <div
              className="w-full h-1.5 overflow-hidden"
              style={{ backgroundColor: 'color-mix(in srgb, var(--area-accent) 15%, transparent)' }}
            >
              <div
                className="h-full transition-all duration-500 ease-out"
                style={{
                  width: `${Math.min(100, Math.round((syncCurrent / syncTotal) * 100))}%`,
                  backgroundColor: 'var(--area-accent)',
                }}
              />
            </div>
          ) : (
            <div
              className="w-full h-1 overflow-hidden"
              style={{ backgroundColor: 'color-mix(in srgb, var(--area-accent) 15%, transparent)' }}
            >
              <div
                className="h-full animate-pulse"
                style={{ backgroundColor: 'var(--area-accent)', width: '40%' }}
              />
            </div>
          )}
        </div>
      )}

      {/* Toast */}
      {toast && (
        <div
          className="rounded-[var(--radius-md)] p-2.5 text-xs"
          style={{
            backgroundColor: toast.kind === 'ok'
              ? 'color-mix(in srgb, var(--color-success) 12%, transparent)'
              : 'color-mix(in srgb, var(--color-error) 12%, transparent)',
            border: `1px solid ${toast.kind === 'ok' ? 'var(--color-success)' : 'var(--color-error)'}`,
            color: toast.kind === 'ok' ? 'var(--color-success)' : 'var(--color-error)',
          }}
        >
          {toast.msg}
        </div>
      )}

      {/* 数据源 action cards */}
      <section className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {/* Cubox 同步 */}
        <div
          className="rounded-[var(--radius-md)] p-3.5"
          style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}
        >
          <div className="flex items-center gap-2 mb-2">
            <span
              className="w-6 h-6 rounded-md flex items-center justify-center text-[10px] font-bold"
              style={{
                backgroundColor: 'color-mix(in srgb, var(--area-accent) 12%, transparent)',
                color: 'var(--area-accent)',
              }}
            >
              <Icon size={12}>
                <path d="M21 12a9 9 0 0 1-9 9m9-9a9 9 0 0 0-9-9m9 9H3m9 9a9 9 0 0 1-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9" />
              </Icon>
            </span>
            <h4 className="text-xs font-bold" style={{ color: 'var(--text-primary)' }}>
              Cubox 同步
            </h4>
            <span className="text-[10px]" style={{ color: 'var(--text-muted)' }}>
              收藏夹全文 + 标注
            </span>
          </div>
          <p className="text-[11px] mb-3" style={{ color: 'var(--text-secondary)' }}>
            拉取 Cubox 中收藏的卡片正文与高亮，触发后台同步任务。
          </p>
          <button
            onClick={handleSync}
            disabled={syncing}
            className="btn-ghost px-3 py-1.5 text-xs"
            style={{
              color: 'var(--area-accent)',
              opacity: syncing ? 0.6 : 1,
              cursor: syncing ? 'wait' : 'pointer',
            }}
          >
            {syncing ? (
              <span className="flex items-center gap-1.5">
                <span className="inline-block w-3 h-3 border-2 border-current border-t-transparent rounded-full animate-spin" />
                同步中…
              </span>
            ) : (
              '同步 Cubox'
            )}
          </button>
        </div>

        {/* 书签导入 */}
        <div
          className="rounded-[var(--radius-md)] p-3.5"
          style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}
        >
          <div className="flex items-center gap-2 mb-2">
            <span
              className="w-6 h-6 rounded-md flex items-center justify-center text-[10px] font-bold"
              style={{
                backgroundColor: 'color-mix(in srgb, var(--area-accent) 12%, transparent)',
                color: 'var(--area-accent)',
              }}
            >
              <Icon size={12}>
                <path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z" />
              </Icon>
            </span>
            <h4 className="text-xs font-bold" style={{ color: 'var(--text-primary)' }}>
              浏览器书签
            </h4>
            <span className="text-[10px]" style={{ color: 'var(--text-muted)' }}>
              Chrome JSON / HTML
            </span>
          </div>
          <p className="text-[11px] mb-3" style={{ color: 'var(--text-secondary)' }}>
            上传 Chrome / Edge 导出的书签文件，自动去重，可选验证 URL 可达性。
          </p>
          <BookmarkImport />
        </div>

        {/* Obsidian 入口 */}
        <div
          className="rounded-[var(--radius-md)] p-3.5"
          style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}
        >
          <div className="flex items-center gap-2 mb-2">
            <span
              className="w-6 h-6 rounded-md flex items-center justify-center text-[10px] font-bold"
              style={{
                backgroundColor: 'color-mix(in srgb, var(--area-accent) 12%, transparent)',
                color: 'var(--area-accent)',
              }}
            >
              <Icon size={12}>
                <circle cx="12" cy="12" r="9" />
                <path d="M12 7v10M7 12h10" />
              </Icon>
            </span>
            <h4 className="text-xs font-bold" style={{ color: 'var(--text-primary)' }}>
              Obsidian vault
            </h4>
            <span className="text-[10px]" style={{ color: 'var(--text-muted)' }}>
              本地 vault 协议
            </span>
          </div>
          <p className="text-[11px] mb-3" style={{ color: 'var(--text-secondary)' }}>
            通过 <code style={{ color: 'var(--area-accent)' }}>obsidian://</code> 协议唤起本地 Obsidian。
          </p>
          <button
            onClick={handleOpenObsidian}
            className="btn-ghost px-3 py-1.5 text-xs"
            style={{ color: 'var(--area-accent)' }}
          >
            打开 Obsidian
          </button>
        </div>

        {/* 冲突快照 */}
        <div
          className="rounded-[var(--radius-md)] p-3.5"
          style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}
        >
          <div className="flex items-center gap-2 mb-2">
            <span
              className="w-6 h-6 rounded-md flex items-center justify-center text-[10px] font-bold"
              style={{
                backgroundColor: 'color-mix(in srgb, var(--area-accent) 12%, transparent)',
                color: 'var(--area-accent)',
              }}
            >
              <Icon size={12}>
                <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
                <line x1="12" y1="9" x2="12" y2="13" />
                <line x1="12" y1="17" x2="12.01" y2="17" />
              </Icon>
            </span>
            <h4 className="text-xs font-bold" style={{ color: 'var(--text-primary)' }}>
              冲突快照
            </h4>
            <span className="text-[10px]" style={{ color: 'var(--text-muted)' }}>
              watchdog 记录
            </span>
          </div>
          <p className="text-[11px] mb-3" style={{ color: 'var(--text-secondary)' }}>
            查看文件监视器记录的同步冲突（外部修改 vs 内部写入）。
          </p>
          <button
            onClick={handleViewConflicts}
            className="btn-ghost px-3 py-1.5 text-xs"
            style={{ color: conflicts !== null ? 'var(--color-error)' : 'var(--area-accent)' }}
          >
            {conflicts !== null ? '隐藏冲突' : '查看冲突'}
          </button>
        </div>
      </section>

      {/* 资讯收藏 — 第 5 个入口卡片 (全宽) */}
      <section className="grid grid-cols-1 gap-3">
        <div
          className="rounded-[var(--radius-md)] p-3.5 cursor-pointer hover:bg-[var(--bg-hover)] transition-colors"
          style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}
          onClick={() => navigate('/knowledge/imported')}
          role="button"
          tabIndex={0}
          onKeyDown={e => { if (e.key === 'Enter') navigate('/knowledge/imported'); }}
        >
          <div className="flex items-center gap-2 mb-2">
            <span
              className="w-6 h-6 rounded-md flex items-center justify-center text-[10px] font-bold"
              style={{
                backgroundColor: 'color-mix(in srgb, var(--area-accent) 12%, transparent)',
                color: 'var(--area-accent)',
              }}
            >
              <Icon size={12}>
                <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
                <polyline points="22 4 12 14.01 9 11.01" />
              </Icon>
            </span>
            <h4 className="text-xs font-bold" style={{ color: 'var(--text-primary)' }}>
              资讯收藏
            </h4>
            <span className="text-[10px]" style={{ color: 'var(--text-muted)' }}>
              5 源聚合
            </span>
          </div>
          <p className="text-[11px]" style={{ color: 'var(--text-secondary)' }}>
            聚合展示 SecNews 收藏 / Cubox / 书签导入 / 归档 / 实时 5 类数据源，支持去重、排序、筛选与分页。
          </p>
          <div className="mt-2 flex items-center gap-1 text-[10px] font-mono" style={{ color: 'var(--area-accent)' }}>
            <span>浏览全部 ›</span>
          </div>
        </div>
      </section>

      {/* 冲突列表展开 */}
      {conflicts !== null && (
        <section
          className="rounded-[var(--radius-md)] p-2.5 text-xs"
          style={{
            backgroundColor: 'var(--bg-elevated)',
            border: '1px solid var(--border-color)',
          }}
        >
          <div className="font-semibold mb-1.5" style={{ color: 'var(--text-primary)' }}>
            冲突快照 ({conflicts.length})
          </div>
          {conflicts.length === 0 ? (
            <p style={{ color: 'var(--text-muted)' }}>无冲突记录</p>
          ) : (
            <ul className="space-y-1">
              {conflicts.map(c => (
                <li key={c.filename} className="flex items-center gap-2">
                  <span style={{ color: 'var(--color-error)' }}>⚠</span>
                  <span className="flex-1 truncate" title={c.filename} style={{ color: 'var(--text-primary)' }}>
                    {c.filename}
                  </span>
                  <span style={{ color: 'var(--text-muted)' }}>{(c.size / 1024).toFixed(1)} KB</span>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}
    </div>
  );
}
