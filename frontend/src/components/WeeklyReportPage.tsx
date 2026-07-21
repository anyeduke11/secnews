import React, { useMemo } from 'react';
import { useWeeklyReport } from '../hooks/useWeeklyReport';
import { WeeklyReport, CATEGORIES, getCategoryColor, getCategoryLabel } from '../types';

interface WeeklyReportPageProps {
  onBack: () => void;
}

function Icon({ children, size = 14 }: { children: React.ReactNode; size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {children}
    </svg>
  );
}

function formatDate(iso: string): string {
  try {
    const d = new Date(iso);
    return `${d.getMonth() + 1}/${d.getDate()}`;
  } catch {
    return iso.slice(5, 10);
  }
}

function formatWeekRange(report: WeeklyReport): string {
  return `${formatDate(report.week_start)} - ${formatDate(report.week_end)}`;
}

function CategoryBar({ summary }: { summary: Record<string, number> }) {
  const total = Object.values(summary).filter(v => typeof v === 'number').reduce((a, b) => a + b, 0) || 1;
  const segments = CATEGORIES.filter(c => c.id !== 'all' && (summary[c.id] || 0) > 0).map(c => ({
    id: c.id,
    count: summary[c.id] || 0,
    color: c.color,
    pct: ((summary[c.id] || 0) / total) * 100,
  }));

  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-4 rounded-full overflow-hidden flex" style={{ backgroundColor: 'var(--bg-hover)' }}>
        {segments.map(s => (
          <div key={s.id} style={{ width: `${s.pct}%`, backgroundColor: s.color, minWidth: s.pct > 0 ? 2 : 0 }} title={`${getCategoryLabel(s.id)}: ${s.count}`} />
        ))}
      </div>
      <span className="text-xs font-mono tabular-nums shrink-0" style={{ color: 'var(--text-secondary)' }}>
        {total}
      </span>
    </div>
  );
}

function TopItemsList({ items }: { items: any[] }) {
  if (!items || items.length === 0) return null;
  const top5 = items.slice(0, 5);
  return (
    <div className="space-y-1.5">
      {top5.map((item, i) => (
        <div key={item.id || i} className="flex items-start gap-2 text-xs">
          <span className="font-mono shrink-0" style={{ color: 'var(--text-muted)', width: 16 }}>{i + 1}.</span>
          <a
            href={item.url}
            target="_blank"
            rel="noreferrer"
            className="truncate hover:underline"
            style={{ color: 'var(--text-primary)' }}
            title={item.title}
          >
            {item.title}
          </a>
          <span className="shrink-0 px-1 rounded text-[10px]" style={{ backgroundColor: getCategoryColor(item.category) + '22', color: getCategoryColor(item.category) }}>
            {getCategoryLabel(item.category)}
          </span>
        </div>
      ))}
    </div>
  );
}

function ReportCard({ report, active, onClick }: { report: WeeklyReport; active: boolean; onClick: () => void }) {
  const summary = typeof report.category_summary === 'string' ? {} : (report.category_summary as Record<string, number>);

  return (
    <button
      onClick={onClick}
      className="w-full text-left px-3 py-2.5 rounded-[var(--radius-sm)] transition-colors"
      style={{
        backgroundColor: active ? 'var(--bg-hover)' : 'transparent',
        borderLeft: active ? '3px solid var(--color-ai)' : '3px solid transparent',
      }}
    >
      <div className="text-xs font-medium" style={{ color: active ? 'var(--color-ai)' : 'var(--text-primary)' }}>
        {formatWeekRange(report)}
      </div>
      <div className="text-[10px] mt-0.5" style={{ color: 'var(--text-muted)' }}>
        {summary?.total ?? 0} 条热点
      </div>
    </button>
  );
}

export function WeeklyReportPage({ onBack }: WeeklyReportPageProps) {
  const { reports, latest, loading, error, generate } = useWeeklyReport();
  const [selectedWeek, setSelectedWeek] = React.useState<string | null>(null);

  const selected = useMemo(() => {
    if (!selectedWeek && latest) return latest;
    if (selectedWeek) return reports.find(r => r.week_start === selectedWeek) || latest;
    return latest;
  }, [selectedWeek, reports, latest]);

  const parsedSummary = useMemo(() => {
    if (!selected) return null;
    const s = selected.category_summary;
    return typeof s === 'string' ? null : (s as Record<string, number>);
  }, [selected]);

  const parsedTopItems = useMemo(() => {
    if (!selected) return [];
    const t = selected.top_items;
    return Array.isArray(t) ? t : [];
  }, [selected]);

  const parsedSourceHealth = useMemo(() => {
    if (!selected) return [];
    const s = selected.source_health;
    return Array.isArray(s) ? s : [];
  }, [selected]);

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <button onClick={onBack} className="btn-ghost px-2 py-1.5 text-xs" aria-label="返回首页">
            <Icon><polyline points="15 18 9 12 15 6" /></Icon>
          </button>
          <div>
            <h2 className="text-base font-bold" style={{ color: 'var(--text-primary)' }}>周报</h2>
            <p className="text-[11px]" style={{ color: 'var(--text-muted)' }}>每周热点回顾与趋势分析</p>
          </div>
        </div>
        <button
          onClick={generate}
          disabled={loading}
          className="btn-ghost px-3 py-1.5 text-xs"
          style={{ opacity: loading ? 0.6 : 1 }}
        >
          <Icon><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><polyline points="14 2 14 8 20 8" /><line x1="12" y1="18" x2="12" y2="12" /><line x1="9" y1="15" x2="15" y2="15" /></Icon>
          <span className="ml-1">生成本周周报</span>
        </button>
      </div>

      {error && (
        <div className="px-3 py-2 rounded text-xs" style={{ backgroundColor: 'color-mix(in srgb, var(--color-error) 13%, transparent)', color: 'var(--color-error)' }}>
          {error}
        </div>
      )}

      <div className="flex gap-4">
        <div className="w-48 shrink-0 space-y-1 max-h-[70vh] overflow-y-auto" style={{ borderRight: '1px solid var(--border-color)', paddingRight: 12 }}>
          {reports.length === 0 && !loading && (
            <p className="text-xs" style={{ color: 'var(--text-muted)' }}>暂无周报数据</p>
          )}
          {reports.map(r => (
            <ReportCard
              key={r.week_start}
              report={r}
              active={(selected?.week_start || '') === r.week_start}
              onClick={() => setSelectedWeek(r.week_start)}
            />
          ))}
        </div>

        <div className="flex-1 space-y-5">
          {loading && !selected && (
            <div className="text-center py-10 text-xs" style={{ color: 'var(--text-muted)' }}>加载中…</div>
          )}

          {!loading && !selected && (
            <div className="text-center py-10 text-xs" style={{ color: 'var(--text-muted)' }}>
              点击「生成本周周报」开始
            </div>
          )}

          {selected && (
            <>
              <div>
                <h3 className="text-sm font-semibold mb-2" style={{ color: 'var(--text-primary)' }}>
                  {formatWeekRange(selected)} 热点分布
                </h3>
                {parsedSummary && <CategoryBar summary={parsedSummary} />}
                <div className="flex flex-wrap gap-3 mt-2">
                  {CATEGORIES.filter(c => c.id !== 'all' && (parsedSummary?.[c.id] || 0) > 0).map(c => (
                    <span key={c.id} className="text-[11px] flex items-center gap-1">
                      <span className="w-2 h-2 rounded-full inline-block" style={{ backgroundColor: c.color }} />
                      <span style={{ color: 'var(--text-secondary)' }}>{c.label}</span>
                      <span className="font-mono" style={{ color: c.color }}>{parsedSummary?.[c.id] || 0}</span>
                    </span>
                  ))}
                </div>
              </div>

              {parsedTopItems.length > 0 && (
                <div>
                  <h3 className="text-sm font-semibold mb-2" style={{ color: 'var(--text-primary)' }}>Top 热点</h3>
                  <TopItemsList items={parsedTopItems} />
                </div>
              )}

              {parsedSourceHealth.length > 0 && (
                <div>
                  <h3 className="text-sm font-semibold mb-2" style={{ color: 'var(--text-primary)' }}>来源健康度</h3>
                  <div className="space-y-1">
                    {parsedSourceHealth.slice(0, 10).map((s: any, i: number) => (
                      <div key={i} className="flex items-center gap-2 text-xs">
                        <span className="truncate flex-1" style={{ color: 'var(--text-secondary)' }}>{s.source}</span>
                        <span className="font-mono shrink-0" style={{ color: 'var(--text-muted)' }}>{s.total} 条</span>
                        <span className="font-mono shrink-0" style={{ color: s.pass / Math.max(s.total, 1) >= 0.8 ? 'var(--color-success)' : 'var(--color-warning)' }}>
                          {Math.round((s.pass / Math.max(s.total, 1)) * 100)}%
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <div className="text-[10px]" style={{ color: 'var(--text-muted)' }}>
                生成于 {selected.generated_at ? new Date(selected.generated_at).toLocaleString('zh-CN') : '—'}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}