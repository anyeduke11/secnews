/**
 * FunnelBar — 管线漏斗 (治理 T3: 吞吐为主视图, 存量降为次要)
 *
 * 主视图 = 近 7 天各阶段 kl_transition 到达量条形 (流量口径, 按最大值归一),
 * 存量快照 (lifecycle 投影) 降为行尾小字 — 存量被 T4 发布直灌污染时
 * (publish 存量 4179 vs 近 7 天流动 0) 只有流量能暴露管线停摆。
 * last_transition_at 距今 >7 天 → 顶部黄条提示"管线停摆 N 天" (治理 T4 防再犯展示面)。
 * throughput 字段缺失 (旧后端) 时降级回存量条形, 保持兼容。
 */
/** /api/kl/pipeline/stats.throughput — 近 7 天事件流 (治理 T3 吞吐口径) */
export interface StageThroughput {
  throughput_7d: Record<string, number>;
  conversion: Record<string, number | null>;
  last_transition_at: string | null;
}

interface FunnelBarProps {
  funnel: Array<{ stage: string; count: number }>;
  throughput?: StageThroughput | null;
}

const STAGE_COLORS: Record<string, string> = {
  'kl:raw': 'var(--color-info)',
  'kl:refine': 'var(--color-warning)',
  'kl:link': 'var(--color-ai)',
  'kl:structure': 'var(--layer-judge)',
  'kl:publish': 'var(--color-success)',
};

/** 停摆判定阈值 (天) — 与治理 T4 "入口断供 >7d 提示" 口径一致 */
const STALL_THRESHOLD_DAYS = 7;

/** last_transition_at 距今天数; 无心跳/解析失败 → null (不误报) */
function stalledDays(lastTransitionAt: string | null): number | null {
  if (!lastTransitionAt) return null;
  const t = new Date(lastTransitionAt).getTime();
  if (Number.isNaN(t)) return null;
  return Math.floor((Date.now() - t) / 86_400_000);
}

export function FunnelBar({ funnel, throughput }: FunnelBarProps) {
  const stalled = throughput ? stalledDays(throughput.last_transition_at) : null;
  const th = throughput?.throughput_7d ?? null;
  const conv = throughput?.conversion ?? null;
  const max = th
    ? Math.max(...funnel.map(f => th[f.stage] ?? 0), 1)
    : Math.max(...funnel.map(f => f.count), 1);

  return (
    <div className="p-3 rounded-[var(--radius-sm)]" style={{ border: '1px solid var(--border-color)' }}>
      <h3 className="text-xs font-mono font-medium mb-3" style={{ color: 'var(--text-primary)' }}>
        管线漏斗
      </h3>
      {stalled != null && stalled > STALL_THRESHOLD_DAYS && (
        <div
          className="flex items-center gap-2 mb-3 px-2 py-1.5 rounded-[2px] text-[11px] font-mono"
          style={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--color-warning)', color: 'var(--color-warning)' }}
          role="alert"
        >
          ⚠ 管线停摆 {stalled} 天 — 近 7 天无阶段转化, 请检查知识入管链路
        </div>
      )}
      <div className="flex flex-col gap-1.5">
        {funnel.map(f => {
          const flow = th ? th[f.stage] ?? 0 : f.count;
          const rateKey = conv ? Object.keys(conv).find(k => k.endsWith(`_to_${f.stage.replace('kl:', '')}`)) : undefined;
          const rate = rateKey ? conv?.[rateKey] : undefined;
          return (
            <div key={f.stage} className="flex items-center gap-2">
              <span className="text-[10px] font-mono w-24 shrink-0" style={{ color: 'var(--text-muted)' }}>
                {f.stage.replace('kl:', '')}
              </span>
              <div className="flex-1 h-4 rounded-[2px] overflow-hidden" style={{ backgroundColor: 'var(--bg-secondary)' }}>
                <div
                  className="h-full rounded-[2px] transition-all"
                  style={{
                    width: `${(flow / max) * 100}%`,
                    backgroundColor: STAGE_COLORS[f.stage] ?? 'var(--accent)',
                    minWidth: flow > 0 ? '4px' : '0',
                  }}
                />
              </div>
              <span
                className="text-[10px] font-mono w-24 text-right tabular-nums"
                style={{ color: th ? 'var(--text-primary)' : 'var(--text-secondary)' }}
                title={th ? '近 7 天转化量 / 存量' : '存量'}
              >
                {th ? <>近7天 {flow.toLocaleString()} <span style={{ color: 'var(--text-muted)' }}>· 存量 {f.count.toLocaleString()}</span></> : f.count.toLocaleString()}
              </span>
              {th && rate != null && (
                <span className="text-[10px] font-mono w-12 text-right tabular-nums" style={{ color: 'var(--text-muted)' }} title="上一阶段 → 本阶段转化率">
                  {Math.round(rate * 100)}%
                </span>
              )}
              {th && rateKey && rate == null && (
                <span className="text-[10px] font-mono w-12 text-right" style={{ color: 'var(--text-muted)' }}>—</span>
              )}
            </div>
          );
        })}
      </div>
      {th && (
        <p className="mt-2 text-[10px] font-mono" style={{ color: 'var(--text-muted)' }}>
          主视图 = 近 7 天 kl_transition 流量; 存量为 lifecycle 快照, 二者口径不同
        </p>
      )}
    </div>
  );
}
