/**
 * ReviewDataView — 复习栈弹层「数据」视图 (B5 从 ReviewOverlay 抽出)
 *
 * 7 日到期预报柱状 / 复习历史流 / 保留率 30d / 评分分布 / 在册+暂停计数。
 * 取数 (getReviewForecast · listReviewHistory · getReviewStats) 原样搬运,
 * Promise.all 并发与次数不变; DOM / class / aria 与拆分前逐字一致。
 */
import { useEffect, useMemo, useState } from 'react';
import { getReviewForecast, getReviewStats, listReviewHistory } from '../../../api/action';
import { fmtDay, type ForecastItem, type HistoryItem, type RvStats } from './reviewModel';

export function ReviewDataView() {
  const [forecast, setForecast] = useState<ForecastItem[] | null>(null);
  const [history, setHistory] = useState<HistoryItem[] | null>(null);
  const [stats, setStats] = useState<RvStats | null>(null);

  useEffect(() => {
    let dead = false;
    Promise.all([
      getReviewForecast<{ items?: ForecastItem[] }>(7).catch(() => null),
      listReviewHistory<{ items?: HistoryItem[] }>(50).catch(() => null),
      getReviewStats<RvStats>().catch(() => null),
    ]).then(([fc, hs, st]) => {
      if (dead) return;
      setForecast(fc?.items ?? null);
      setHistory(hs?.items ?? null);
      setStats(st?.stats ?? null);
    });
    return () => { dead = true; };
  }, []);

  const maxCount = useMemo(
    () => Math.max(1, ...(forecast ?? []).map(f => f.count)),
    [forecast],
  );
  const distEntries = Object.entries(stats?.grade_distribution ?? {});

  return (
    <div className="ac-rv-data">
      <section className="ac-rv-block">
        <h4 className="ac-rv-bh">7 日到期预报</h4>
        {forecast ? (
          <div className="ac-rv-bars" role="img"
            aria-label={`未来 7 天到期数：${forecast.map(f => `${f.date} ${f.count} 张`).join('，')}`}>
            {forecast.map(f => (
              <div key={f.date} className="ac-rv-barcol" title={`${f.date}：${f.count} 张`}>
                <b className="num">{f.count}</b>
                <i style={{ height: `${Math.round((f.count / maxCount) * 64) + 2}px` }} />
                <span className="num">{f.date.slice(5)}</span>
              </div>
            ))}
          </div>
        ) : <p className="ac-rv-hint">载入中…</p>}
      </section>

      <section className="ac-rv-block">
        <h4 className="ac-rv-bh">保留率与分布</h4>
        <div className="ac-rv-kpis">
          <span>保留率 30d <b className="num">
            {stats ? (stats.retention_30d == null ? '--' : `${Math.round(stats.retention_30d * 100)}%`) : '…'}
          </b></span>
          <span>在册 <b className="num">{stats?.total ?? '--'}</b></span>
          <span>暂停 <b className="num">{stats?.suspended_count ?? '--'}</b></span>
          {distEntries.map(([g, n]) => (
            <span key={g}>g{g} <b className="num">{n}</b></span>
          ))}
        </div>
      </section>

      <section className="ac-rv-block">
        <h4 className="ac-rv-bh">复习历史</h4>
        {history === null ? <p className="ac-rv-hint">载入中…</p> : history.length === 0 ? (
          <p className="ac-rv-hint">还没有评分记录。评分后会在这里留下流水。</p>
        ) : (
          <ul className="ac-rv-hist">
            {history.map(h => (
              <li key={h.id} className={h.reverted ? 'is-reverted' : undefined}>
                <span className="ac-rv-ht num">{fmtDay(h.created_at)}</span>
                <span className="ac-rv-htitle">{h.entity_id}</span>
                <span className="ac-rv-hm num">
                  g{h.grade} · 下次 {h.new_interval}d{h.reverted ? ' · 已撤销' : ''}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
