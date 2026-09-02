/**
 * settings/SettingsDashboard — 设置首屏 · 哨兵式体检面板 (V2)
 *
 * 用途:
 *  - 默认 cat=dashboard, 不点进各分类也能看到"系统还好吗"
 *  - 4 张系统子状态卡 (DB / 采集 / 凭据 / 调度) + 8 张区段跳转 tile + 最近 24h 统计
 *  - 借 settings-shell.css 的 st-card / st-cellgrid / st-tilegrid / st-chip
 *
 * 数据源 (与哨兵面板一致, 直接 fetch 而非 usePipe):
 *  - GET /api/health        → db.ok / scheduler.jobs / collectors
 *  - GET /api/secrets/status → master_key 初始化 + unlock 状态
 *  - GET /api/sources/health → 源健康概览
 *  - GET /api/stats         → 24h collect_runs / hotspots 总数 / 平均耗时
 *
 * 不在 V2 范围:
 *  - 实时 SSE 推送 (复用现有 /api/observability/stream, 后续按需接入)
 *  - 历史趋势图 (留 v0.8 — 当前只渲染 4 个核心数字)
 */
import { useEffect, useState } from 'react';
import type { SectionKey } from './sections';

interface Props {
  onJump: (cat: SectionKey) => void;
}

interface HealthPayload {
  ok?: boolean;
  uptime_s?: number;
  db?: {
    ok: boolean;
    latency_ms: number;
    size_mb?: number;
    hotspots_count?: number;
    error?: string;
  };
  scheduler?: {
    ok: boolean;
    jobs?: string[];
    error?: string;
  };
  collectors?: {
    last_run?: string;
    watchdog_recoveries_24h?: number;
  };
  cache?: { hit_rate?: number };
}

interface SecretsStatus {
  initialized?: boolean;
  unlocked?: boolean;
  source?: 'os_keyring' | 'session' | 'uninitialized';
}

interface StatsPayload {
  total_hotspots?: number;
  collect_runs_24h?: number;
  success_rate_24h?: number;
  avg_collect_duration_ms?: number;
  last_fallback_at?: string | null;
}

interface SourcesHealth {
  total?: number;
  healthy?: number;
  warning?: number;
  dead?: number;
}

const QUICK_JUMPS: Array<{ cat: SectionKey; label: string; key: string; note: string }> = [
  { cat: 'collection', label: '采集', key: 'collection', note: '质量/信源/调度' },
  { cat: 'secrets', label: '密钥', key: 'secrets', note: 'LLM 凭据状态' },
  { cat: 'alerts', label: '告警', key: 'alerts', note: '规则与通道' },
  { cat: 'sync', label: '同步', key: 'sync', note: 'WebDAV/跨设备' },
  { cat: 'pipeline', label: '管线', key: 'pipeline', note: 'KL/dsh/Agent' },
  { cat: 'sentinel', label: '哨兵', key: 'sentinel', note: '只读控制台' },
  { cat: 'maintenance', label: '维护', key: 'maintenance', note: 'VACUUM/去重' },
  { cat: 'feedback', label: '反馈画像', key: 'feedback', note: '角色倾向总结' },
];

function fmtUptime(s?: number): string {
  if (typeof s !== 'number' || s < 0) return '—';
  const days = Math.floor(s / 86400);
  const hrs = Math.floor((s % 86400) / 3600);
  if (days > 0) return `${days}d ${hrs}h`;
  const mins = Math.floor((s % 3600) / 60);
  return `${hrs}h ${mins}m`;
}

function fmtPct(v?: number): string {
  if (typeof v !== 'number') return '—';
  return `${(v * 100).toFixed(1)}%`;
}

function fmtInt(v?: number): string {
  if (typeof v !== 'number') return '—';
  return v.toLocaleString('en-US');
}

function fmtMs(v?: number): string {
  if (typeof v !== 'number') return '—';
  return `${Math.round(v)} ms`;
}

export function SettingsDashboard({ onJump }: Props) {
  const [health, setHealth] = useState<HealthPayload | null>(null);
  const [secrets, setSecrets] = useState<SecretsStatus | null>(null);
  const [stats, setStats] = useState<StatsPayload | null>(null);
  const [sources, setSources] = useState<SourcesHealth | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    const fetches: Array<Promise<unknown>> = [
      fetch('/api/health').then(r => r.json()).catch(() => null),
      fetch('/api/secrets/status').then(r => r.json()).catch(() => null),
      fetch('/api/stats').then(r => r.json()).catch(() => null),
      fetch('/api/sources/health').then(r => r.json()).catch(() => null),
    ];
    Promise.all(fetches).then(([h, s, st, src]) => {
      if (cancelled) return;
      setHealth(h as HealthPayload);
      setSecrets(s as SecretsStatus);
      setStats(st as StatsPayload);
      // /api/sources/health 是数组 — 聚合
      if (Array.isArray(src)) {
        const arr = src as Array<{ status?: string }>;
        setSources({
          total: arr.length,
          healthy: arr.filter(x => x.status === 'healthy').length,
          warning: arr.filter(x => x.status === 'warning').length,
          dead: arr.filter(x => x.status === 'dead').length,
        });
      } else {
        setSources(null);
      }
      setLoading(false);
    });
    return () => { cancelled = true; };
  }, []);

  const db = health?.db;
  const sched = health?.scheduler;

  return (
    <div className="space-y-3" data-testid="settings-dashboard">
      {/* 4 系统子状态 — st-cellgrid */}
      <section className="st-cellgrid" aria-label="系统状态">
        <article className="st-cell" data-testid="dash-db">
          <span className="st-cellk">DATABASE</span>
          <span className={`st-cellv ${db?.ok === false ? 'red' : db?.ok ? 'mint' : 'amber'}`}>
            {loading ? '…' : db?.ok === false ? 'OFFLINE' : db?.ok ? 'ONLINE' : 'N/A'}
          </span>
          <span className="st-cellnote">
            {db ? `${fmtMs(db.latency_ms)} · ${db.size_mb?.toFixed?.(1) ?? '?'} MB` : '加载中'}
          </span>
          {db?.hotspots_count != null && (
            <span className="st-cellnote">{fmtInt(db.hotspots_count)} 行 · hotspot</span>
          )}
        </article>

        <article className="st-cell" data-testid="dash-collect">
          <span className="st-cellk">COLLECT 24h</span>
          <span className="st-cellv">{fmtInt(stats?.collect_runs_24h)}</span>
          <span className="st-cellnote">
            成功率 {fmtPct(stats?.success_rate_24h)} · 平均 {fmtMs(stats?.avg_collect_duration_ms)}
          </span>
        </article>

        <article className="st-cell" data-testid="dash-secrets">
          <span className="st-cellk">KEYS</span>
          <span className={`st-cellv ${secrets?.unlocked ? 'mint' : secrets?.initialized ? 'amber' : 'red'}`}>
            {!secrets ? '…' : secrets.unlocked ? 'UNLOCKED' : secrets.initialized ? 'LOCKED' : 'NO KEY'}
          </span>
          <span className="st-cellnote">
            {secrets?.source === 'os_keyring' ? 'OS keyring 后端'
              : secrets?.source === 'session' ? '会话内 unlock'
              : '未初始化主密钥'}
          </span>
        </article>

        <article className="st-cell" data-testid="dash-scheduler">
          <span className="st-cellk">SCHEDULER</span>
          <span className={`st-cellv ${sched?.ok === false ? 'red' : sched?.ok ? 'mint' : 'amber'}`}>
            {!sched ? '…' : sched.ok ? `${sched.jobs?.length ?? 0} JOBS` : 'STOPPED'}
          </span>
          <span className="st-cellnote">
            {health?.uptime_s != null ? `uptime ${fmtUptime(health.uptime_s)}` : sched?.error ?? '加载中'}
          </span>
        </article>
      </section>

      {/* 8 区段快速跳转 — st-tilegrid */}
      <section aria-label="区段跳转">
        <h3 style={{ fontFamily: 'var(--sn-mono)', fontSize: 'var(--sn-fs-h3)', fontWeight: 500, margin: '4px 0 8px', color: 'var(--sn-ink)' }}>
          快速跳转
        </h3>
        <div className="st-tilegrid">
          {QUICK_JUMPS.map(t => (
            <button
              key={t.key}
              type="button"
              className="st-tile"
              onClick={() => onJump(t.cat)}
              aria-label={`跳转 ${t.label}`}
              data-testid={`dash-tile-${t.key}`}
            >
              <p className="st-tile-label">{t.label}</p>
              <p className="st-tile-key">cat={t.cat}</p>
              <span className="st-tile-note">{t.note}</span>
            </button>
          ))}
        </div>
      </section>

      {/* 源健康概览 — st-section */}
      <section className="st-section" aria-label="源健康">
        <h3>源健康概览</h3>
        <p className="st-section-desc">
          当前所有信源的存活/降级/死亡计数, 点击下方卡片可跳到采集区段查看详情。
        </p>
        <div className="st-section-body">
          {!sources ? (
            <p className="st-cellnote">无可用源健康数据</p>
          ) : (
            <div className="st-cellgrid">
              <div className="st-cell">
                <span className="st-cellk">TOTAL</span>
                <span className="st-cellv sm">{fmtInt(sources.total)}</span>
              </div>
              <div className="st-cell">
                <span className="st-cellk">HEALTHY</span>
                <span className="st-cellv sm mint">{fmtInt(sources.healthy)}</span>
              </div>
              <div className="st-cell">
                <span className="st-cellk">WARNING</span>
                <span className="st-cellv sm amber">{fmtInt(sources.warning)}</span>
              </div>
              <div className="st-cell">
                <span className="st-cellk">DEAD</span>
                <span className="st-cellv sm red">{fmtInt(sources.dead)}</span>
              </div>
            </div>
          )}
          <div>
            <button
              type="button"
              className="st-btn ghost"
              onClick={() => onJump('collection')}
            >
              → 查看采集区段
            </button>
          </div>
        </div>
      </section>
    </div>
  );
}

export default SettingsDashboard;