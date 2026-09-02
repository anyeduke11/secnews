/**
 * settings/AboutSettings — 系统信息 (Sentinel V2)。
 *
 * 设计原则:
 * - 顶部 st-head 用途说明 (版本对照 / 故障定位 / 上报工单时附)
 * - st-cellgrid 状态卡 (版本 / 运行 / 数据库 / 调度器 / 采集器 / 代理)
 * - 组件状态 st-rule 列表展示
 * - Sentinel 5 disciplines: zero-neon / semantic-3-color / mono-data / mute-text / reduced-motion
 */
import { useState, useEffect } from 'react';
import '../settings/settings-shell.css';

export function AboutSettings() {
  const [health, setHealth] = useState<{
    version?: string;
    uptime_s?: number;
    status?: string;
    components?: { db?: any; scheduler?: any; collectors?: any; proxy?: any };
  } | null>(null);

  useEffect(() => {
    fetch('/api/health')
      .then(r => r.json())
      .then(d => setHealth(d))
      .catch(() => {});
  }, []);

  const fmtUptime = (s?: number) => {
    if (!s) return '-';
    const d = Math.floor(s / 86400);
    const h = Math.floor((s % 86400) / 3600);
    const m = Math.floor((s % 3600) / 60);
    return `${d}d ${h}h ${m}m`;
  };

  const dbOk = health?.components?.db?.ok;
  const dbSizeMB = health?.components?.db?.size_mb;
  const dbTone: 'mint' | 'amber' | 'red' = dbOk ? 'mint' : 'red';

  const schedOk = health?.components?.scheduler?.ok;
  const schedCount = health?.components?.scheduler?.details?.length || 0;
  const schedTone: 'mint' | 'amber' | 'red' = schedOk ? 'mint' : 'amber';

  const collectLast = health?.components?.collectors?.last_run;
  const collectTone: 'mint' | 'amber' | 'red' = collectLast ? 'mint' : 'amber';

  const proxyMode = health?.components?.proxy?.mode;
  const proxyTone: 'mint' | 'amber' | 'red' = proxyMode === 'auto' ? 'mint' : 'amber';

  const statusText = health?.status === 'ok' ? '正常运行'
    : health?.status === 'degraded' ? '部分降级'
    : health?.status === 'down' ? '已停机'
    : '检测中…';

  const statusTone: 'mint' | 'amber' | 'red' = health?.status === 'ok' ? 'mint'
    : health?.status === 'degraded' ? 'amber'
    : health?.status === 'down' ? 'red'
    : 'amber';

  return (
    <div className="settings-shell" style={{ display: 'flex', flexDirection: 'column', gap: 'var(--sn-row)' }}>
      <div className="st-head">
        <h2 className="st-title">系统信息</h2>
        <p className="st-sub2">
          汇报版本 + 组件健康, 故障排查时第一手证据.
          截图提交工单前请确认: 状态徽章不是红色 / 数据库体积未越阈值 / 调度器任务数不为 0.
          重启后运行时间会归零, 期间不能判断 uptime 异常。
        </p>
        <div className="st-headops">
          <span className={`st-chip ${statusTone === 'mint' ? 'ok' : statusTone === 'amber' ? 'warn' : 'bad'}`}>
            <i /> {statusText}
          </span>
        </div>
      </div>

      <div className="st-cellgrid">
        <div className="st-cell">
          <span className="st-cellk">版本</span>
          <span className="st-cellv sm">{health?.version || '—'}</span>
          <span className="st-cellnote">git tag · commit short</span>
        </div>
        <div className="st-cell">
          <span className="st-cellk">运行</span>
          <span className="st-cellv sm">{fmtUptime(health?.uptime_s)}</span>
          <span className="st-cellnote">UPTIME</span>
        </div>
        <div className="st-cell">
          <span className="st-cellk">数据库</span>
          <span className={`st-cellv ${dbTone === 'mint' ? '' : dbTone}`}>
            {dbOk ? '正常' : '异常'}
          </span>
          <span className="st-cellnote">
            {dbSizeMB ? `${dbSizeMB.toFixed(1)} MB` : '尚未采集'}
          </span>
        </div>
        <div className="st-cell">
          <span className="st-cellk">调度器</span>
          <span className={`st-cellv ${schedTone === 'mint' ? '' : schedTone}`}>
            {schedOk ? `${schedCount}` : '—'}
          </span>
          <span className="st-cellnote">{schedOk ? '任务数' : '未启动'}</span>
        </div>
        <div className="st-cell">
          <span className="st-cellk">采集器</span>
          <span className={`st-cellv ${collectTone === 'mint' ? '' : collectTone}`}>
            {collectLast ? collectLast.slice(0, 10) : '未运行'}
          </span>
          <span className="st-cellnote">LAST_RUN</span>
        </div>
        <div className="st-cell">
          <span className="st-cellk">代理</span>
          <span className={`st-cellv ${proxyTone === 'mint' ? '' : proxyTone}`}>
            {proxyMode || '—'}
          </span>
          <span className="st-cellnote">{proxyMode === 'auto' ? '系统接管' : '直连'}</span>
        </div>
      </div>

      {/* 组件详情 — 折叠为单个 st-rule 列表, 紧凑 */}
      <div className="st-section">
        <h3 style={{ margin: '0 0 var(--sn-row) 0', fontSize: 'var(--sn-fs-h3)', color: 'var(--sn-ink)' }}>
          组件清单
        </h3>
        <div className="st-section-body" style={{ padding: 0 }}>
          <table className="st-table">
            <thead>
              <tr>
                <th>组件</th>
                <th style={{ width: 80 }}>状态</th>
                <th style={{ width: 200 }}>详情</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>数据库</td>
                <td>
                  <span className={`st-chip ${dbTone === 'mint' ? 'ok' : 'bad'}`}>
                    <i /> {dbOk ? 'OK' : 'FAIL'}
                  </span>
                </td>
                <td style={{ fontFamily: 'var(--sn-mono)', fontSize: 11, color: 'var(--sn-ink-2)' }}>
                  {dbSizeMB ? `${dbSizeMB.toFixed(1)} MB` : '—'}
                </td>
              </tr>
              <tr>
                <td>调度器</td>
                <td>
                  <span className={`st-chip ${schedTone === 'mint' ? 'ok' : 'warn'}`}>
                    <i /> {schedOk ? 'OK' : 'IDLE'}
                  </span>
                </td>
                <td style={{ fontFamily: 'var(--sn-mono)', fontSize: 11, color: 'var(--sn-ink-2)' }}>
                  {schedOk ? `${schedCount} 个任务` : '未启动'}
                </td>
              </tr>
              <tr>
                <td>采集器</td>
                <td>
                  <span className={`st-chip ${collectTone === 'mint' ? 'ok' : 'warn'}`}>
                    <i /> {collectLast ? 'OK' : 'IDLE'}
                  </span>
                </td>
                <td style={{ fontFamily: 'var(--sn-mono)', fontSize: 11, color: 'var(--sn-ink-2)' }}>
                  {collectLast ? collectLast.slice(0, 16).replace('T', ' ') : '—'}
                </td>
              </tr>
              <tr>
                <td>代理</td>
                <td>
                  <span className={`st-chip ${proxyTone === 'mint' ? 'ok' : 'mute'}`}>
                    <i /> {proxyMode === 'auto' ? 'ON' : 'OFF'}
                  </span>
                </td>
                <td style={{ fontFamily: 'var(--sn-mono)', fontSize: 11, color: 'var(--sn-ink-2)' }}>
                  {proxyMode === 'auto' ? '系统接管' : '直连'}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}