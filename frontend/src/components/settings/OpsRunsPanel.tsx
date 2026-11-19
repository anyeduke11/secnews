/**
 * OpsRunsPanel — 失败面板最小版 (v0.8.6 P0-5 / M5, 设置→运维首卡)。
 *
 * 数据: GET /api/ops/runs (job_runs 统一 run record — 注册口 instrument_job
 * 全量写入 + EVENT_MISSED 的 status=missed 行)。失败优先视图: failed →
 * missed → running → ok, 同级按时间倒序; 后端排序, 前端只呈现。
 * 验收: 任一 job 失败 24h 内可在 UI 查到原因 (PRD §2 G2)。
 */
import { useCallback, useEffect, useState } from 'react';
import { LayerTable, type LayerTableColumn } from '../layout/LayerTable';
import { getOpsRuns } from '../../api/settings';
import { useAbortGuard } from '../../hooks/useAbortGuard';
import { StatusBadge, type StatusTone } from '../../primitives/StatusBadge';

interface RunRow {
  id: number;
  job_id: string;
  job_type: string;
  status: 'running' | 'ok' | 'failed' | 'missed';
  started_at: string;
  finished_at: string | null;
  duration_ms: number | null;
  error: string | null;
  trace_id: string | null;
}

interface OpsRunsResponse {
  runs: RunRow[];
  summary: {
    ok: number; failed: number; missed: number;
    running: number; stale_running: number;
  };
  window_hours: number;
}

type FilterKey = 'failed,missed' | 'all';

const FILTERS: Array<{ key: FilterKey; label: string }> = [
  { key: 'failed,missed', label: '失败优先' },
  { key: 'all', label: '全部' },
];

const STATUS_LABEL: Record<RunRow['status'], string> = {
  failed: '失败', missed: '错过', ok: '成功', running: '进行中',
};
/** 状态四态: failed / missed / ok / running
 *  B10: 收敛到 StatusBadge 的 StatusTone —— failed→risk / missed→warn / ok→ok / running→neutral */
const STATUS_CHIP: Record<RunRow['status'], StatusTone> = {
  failed: 'risk', missed: 'warn', ok: 'ok', running: 'neutral',
};

function fmtDuration(ms: number | null): string {
  if (ms == null) return '—';
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`;
  return `${Math.round(ms / 60_000)}m`;
}

export function OpsRunsPanel() {
  const [data, setData] = useState<OpsRunsResponse | null>(null);
  const [filter, setFilter] = useState<FilterKey>('failed,missed');
  const dead = useAbortGuard(); // P1-7 竞态守卫: 卸载后不写状态

  const reload = useCallback(async (f: FilterKey) => {
    try {
      const d = await getOpsRuns<OpsRunsResponse>(f);
      if (dead.current) return;
      setData(d);
    } catch {
      if (dead.current) return;
      setData(null);
    }
  }, [dead]);

  useEffect(() => { void reload(filter); }, [filter, reload]);

  const s = data?.summary;

  const columns: LayerTableColumn<RunRow>[] = [
    { key: 'started_at', header: '时间', render: row => (
      <span className="text-xs whitespace-nowrap" style={{ color: 'var(--text-muted)' }}>
        {row.started_at?.slice(5, 16).replace('T', ' ')}
      </span>
    ) },
    { key: 'job_type', header: '任务', render: row => (
      <span className="font-mono text-xs" title={row.job_id}>{row.job_type}</span>
    ) },
    { key: 'status', header: '状态', render: row => (
      <StatusBadge tone={STATUS_CHIP[row.status]} dot>{STATUS_LABEL[row.status]}</StatusBadge>
    ) },
    { key: 'duration_ms', header: '耗时', render: row => (
      <span className="text-xs tabular-nums" style={{ color: 'var(--text-muted)' }}>
        {fmtDuration(row.duration_ms)}
      </span>
    ) },
    { key: 'error', header: '原因', render: row => (
      <span className="max-w-[320px] truncate inline-block text-xs" title={row.error ?? ''}>
        {row.error ?? '—'}
      </span>
    ) },
  ];

  return (
    <div className="st-card">
      <h3>任务失败面板</h3>
      <p className="st-raildesc">
        24h 内全部定时任务的执行账本 (job_runs) · 失败与错过优先呈现, 原因可查
      </p>

      {/* summary 计数行 + 过滤切换 + 手动刷新 */}
      <div className="flex flex-wrap items-center gap-2 mb-2">
        {s && (
          <>
            <StatusBadge tone="risk" dot>失败 {s.failed}</StatusBadge>
            <StatusBadge tone="warn" dot blink>错过 {s.missed}</StatusBadge>
            <StatusBadge tone="ok" dot>成功 {s.ok}</StatusBadge>
            <StatusBadge tone="neutral" dot>进行 {s.running}</StatusBadge>
            {s.stale_running > 0 && (
              <StatusBadge tone="warn" dot blink title="running 超 2h 未收尾 — 疑似进程崩溃残留">僵尸 {s.stale_running}
              </StatusBadge>
            )}
          </>
        )}
        <span className="flex-1" />
        {FILTERS.map(f => (
          <button
            key={f.key}
            type="button"
            className={`st-btn ghost ${filter === f.key ? '' : 'opacity-50'}`}
            onClick={() => setFilter(f.key)}
          >
            {f.label}
          </button>
        ))}
        <button
          type="button"
          className="st-btn ghost"
          onClick={() => void reload(filter)}
        >
          刷新
        </button>
      </div>

      {data === null ? (
        <p className="st-raildesc">载入中…</p>
      ) : (
        <LayerTable
          columns={columns}
          data={data.runs}
          rowKey={row => row.id}
          emptyMessage="24h 内无失败/错过的任务运行"
          compact
        />
      )}
    </div>
  );
}
