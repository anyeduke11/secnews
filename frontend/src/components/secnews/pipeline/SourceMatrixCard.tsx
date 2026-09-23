/**
 * SourceMatrixCard — 印厂调度源矩阵 (B2, DEV-0192)
 *
 * 数据: GET /api/sources/health (壳心跳同源接口, 无新端点)。
 * 呈现: .ed-table 编辑部表格 — 源 / 类目 / 状态 (ok/warn/err 着色) / 累计产出 / 最近活动;
 * 排序 dead → stale → active (故障源置顶); >100 行截断 + 计数提示。
 * bid (招投标) 类目与 *(搜狗) 镜像源不参与本矩阵展示 (用户裁决 2026-09-18: 与本看板无关)。
 */
import { useEffect, useMemo, useState } from 'react';
import { getJSON } from '../../../lib/api';
import { Stamp } from '../../shared/editorial/Stamp';
import { EmptyState } from '../../EmptyState';
import '../../../components/shared/editorial/pages.css';

interface SourceRow {
  category: string;
  source_name: string;
  status: string;
  total_items?: number;
  last_seen_at?: string | null;
}

const STATUS_ORDER: Record<string, number> = { dead: 0, stale: 1, active: 2 };
const STATUS_LABEL: Record<string, string> = { dead: '离线', stale: '重试', active: '正常' };
const STATUS_COLOR: Record<string, string> = {
  dead: 'var(--err, var(--red))',
  stale: 'var(--warn, var(--amber))',
  active: 'var(--ok, var(--mint))',
};

const DISPLAY_LIMIT = 100;

export function SourceMatrixCard() {
  const [rows, setRows] = useState<SourceRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    getJSON<{ sources?: SourceRow[] }>('/api/sources/health')
      .then(d => { if (alive) setRows(d.sources ?? []); })
      .catch(e => {
        if (!alive) return;
        setRows([]);
        setError(e instanceof Error ? e.message : String(e));
      });
    return () => { alive = false; };
  }, []);

  const sorted = useMemo(() => {
    if (!rows) return [];
    return [...rows]
      .filter(s => s.category !== 'bid' && !s.source_name.includes('(搜狗)'))
      .sort((a, b) =>
      (STATUS_ORDER[a.status] ?? 3) - (STATUS_ORDER[b.status] ?? 3)
      || (b.total_items ?? 0) - (a.total_items ?? 0)
      || a.source_name.localeCompare(b.source_name, 'zh-CN'),
    );
  }, [rows]);

  const shown = sorted.slice(0, DISPLAY_LIMIT);

  return (
    <section aria-label="源健康矩阵" data-testid="source-matrix">
      <div className="ed-sechead">
        <span>源健康矩阵</span>
        <span className="ed-note">
          {rows ? `${sorted.length} 源 · 故障置顶` : '…'}
        </span>
      </div>
      {rows === null ? (
        <EmptyState compact title="源健康加载中…" />
      ) : error ? (
        <EmptyState compact title="源健康加载失败" description={error} />
      ) : sorted.length === 0 ? (
        <EmptyState compact title="暂无注册源" />
      ) : (
        <>
          <table className="ed-table" aria-label="源健康矩阵">
            <thead>
              <tr>
                <th>源</th>
                <th>类目</th>
                <th>状态</th>
                <th>累计</th>
                <th>最近活动</th>
              </tr>
            </thead>
            <tbody>
              {shown.map(s => (
                <tr key={`${s.category}-${s.source_name}`}>
                  <td>{s.source_name}</td>
                  <td className="mono">{s.category}</td>
                  <td className="mono" style={{ color: STATUS_COLOR[s.status] ?? 'var(--sn-ink-3)' }}>
                    {STATUS_LABEL[s.status] ?? s.status}
                  </td>
                  <td className="mono">{s.total_items ?? 0}</td>
                  <td className="mono">{(s.last_seen_at || '').slice(0, 16).replace('T', ' ') || '--'}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {sorted.length > DISPLAY_LIMIT && (
            <div style={{ marginTop: 8 }}>
              <Stamp color="info" variant="hollow">
                仅显示前 {DISPLAY_LIMIT} 源 · 共 {sorted.length} 源
              </Stamp>
            </div>
          )}
        </>
      )}
    </section>
  );
}
