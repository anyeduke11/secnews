/**
 * SourceMatrixCard — 印厂调度源矩阵 (B2, DEV-0192; 治理 T3 介质分组)
 *
 * 数据: GET /api/sources/health (壳心跳同源接口, 无新端点)。
 * 呈现: .ed-table 编辑部表格 — 源 / 类目 / 介质 / 状态 (ok/warn/err 着色) / 累计产出 / 最近活动;
 * 排序 dead → stale → active (故障源置顶); >100 行截断 + 计数提示。
 * 介质筛选 (治理 T3): 全部/网页(web)/微信(wechat)/多媒体(multimedia) —
 * "全部"视图不展示微信行 (用户裁决 2026-09-18 升级为按介质排除, 微信有专属 tab;
 * 缺 media_kind 的旧数据回落 '(搜狗)' 名匹配排除, 兼容迁移前口径)。
 * 灰显: dead 行 opacity 半显 (有产出的 dead 属复活候选, 保留但降噪)。
 * retired/disabled 标记: 本矩阵数据源是 source_stats 统计层 (无 retired/disabled
 * 状态), 不展示 — 注册层视角见 GET /api/sources/system (治理 T2)。
 * bid (招投标) 类目不参与本矩阵展示 (用户裁决 2026-09-18)。
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
  media_kind?: string;
}

type KindFilter = 'all' | 'web' | 'wechat' | 'multimedia';

const KIND_FILTERS: Array<{ value: KindFilter; label: string }> = [
  { value: 'all', label: '全部' },
  { value: 'web', label: '网页' },
  { value: 'wechat', label: '微信' },
  { value: 'multimedia', label: '多媒体' },
];

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
  const [kind, setKind] = useState<KindFilter>('all');

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

  const filtered = useMemo(() => {
    if (!rows) return [];
    const kindOf = (s: SourceRow) => s.media_kind || 'web';
    return [...rows]
      .filter(s => s.category !== 'bid')
      .filter(s => (kind === 'all'
        ? kindOf(s) !== 'wechat' && !s.source_name.includes('(搜狗)')
        : kindOf(s) === kind))
      .sort((a, b) =>
      (STATUS_ORDER[a.status] ?? 3) - (STATUS_ORDER[b.status] ?? 3)
      || (b.total_items ?? 0) - (a.total_items ?? 0)
      || a.source_name.localeCompare(b.source_name, 'zh-CN'),
    );
  }, [rows, kind]);

  const shown = filtered.slice(0, DISPLAY_LIMIT);

  return (
    <section aria-label="源健康矩阵" data-testid="source-matrix">
      <div className="ed-sechead">
        <span>源健康矩阵</span>
        <span className="ed-note">
          {rows ? `${filtered.length} 源 · 故障置顶` : '…'}
        </span>
      </div>
      <div className="flex items-center gap-1 mb-2" role="group" aria-label="介质筛选">
        {KIND_FILTERS.map(f => (
          <button
            key={f.value}
            onClick={() => setKind(f.value)}
            className="px-2 py-1 text-[11px] font-mono rounded-[var(--radius-sm)] transition-colors"
            style={{
              color: kind === f.value ? 'var(--accent)' : 'var(--text-muted)',
              backgroundColor: kind === f.value ? 'var(--accent-soft)' : 'transparent',
            }}
            aria-pressed={kind === f.value}
          >
            {f.label}
          </button>
        ))}
      </div>
      {rows === null ? (
        <EmptyState compact title="源健康加载中…" />
      ) : error ? (
        <EmptyState compact title="源健康加载失败" description={error} />
      ) : filtered.length === 0 ? (
        <EmptyState compact title="暂无注册源" />
      ) : (
        <>
          <table className="ed-table" aria-label="源健康矩阵">
            <thead>
              <tr>
                <th>源</th>
                <th>类目</th>
                <th>介质</th>
                <th>状态</th>
                <th>累计</th>
                <th>最近活动</th>
              </tr>
            </thead>
            <tbody>
              {shown.map(s => (
                <tr
                  key={`${s.category}-${s.source_name}`}
                  className={s.status === 'dead' ? 'opacity-50 saturate-0' : undefined}
                >
                  <td>{s.source_name}</td>
                  <td className="mono">{s.category}</td>
                  <td className="mono">{s.media_kind || 'web'}</td>
                  <td className="mono" style={{ color: STATUS_COLOR[s.status] ?? 'var(--sn-ink-3)' }}>
                    {STATUS_LABEL[s.status] ?? s.status}
                  </td>
                  <td className="mono">{s.total_items ?? 0}</td>
                  <td className="mono">{(s.last_seen_at || '').slice(0, 16).replace('T', ' ') || '--'}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {filtered.length > DISPLAY_LIMIT && (
            <div style={{ marginTop: 8 }}>
              <Stamp color="info" variant="hollow">
                仅显示前 {DISPLAY_LIMIT} 源 · 共 {filtered.length} 源
              </Stamp>
            </div>
          )}
        </>
      )}
    </section>
  );
}
