/**
 * shell/PipeBar — 印务条 pressbar (采集管道心跳)
 *
 * 2026-11-17 结构性拆分自 components/sentinel/SentinelShell.tsx, DOM/类名/文案逐字搬出。
 * 语义不变, 全站常驻; 心跳数据经 PipeContext 读取。
 */
import { usePipe } from './pipe';

export function PipeBar({ ingested }: { ingested: number | null }) {
  const { pipe } = usePipe();
  return (
    <section className="pressbar" aria-label="采集管道状态">
      <div className="pipe-block">
        <span className="pipe-k">管道状态</span>
        <span className="pipe-v" style={{ color: pipe?.health === '良好' ? 'var(--sn-mint)' : pipe?.health === '--' ? undefined : pipe?.health === '一般' ? 'var(--sn-amber)' : 'var(--sn-red)' }}>
          {pipe?.health ?? '…'}
        </span>
      </div>
      <div className="pipe-block">
        <span className="pipe-k" title="分母 = 采集器注册表中 enabled=1 的源数（不含已停止抓取的 source_stats 历史行）">源在线</span>
        <span className="pipe-v">
          {pipe ? `${pipe.active} / ${pipe.total}` : '…'}
          {pipe && pipe.stale > 0 && <span className="delta" style={{ color: 'var(--sn-amber)' }}>{pipe.stale} 重试</span>}
          {pipe && pipe.dead > 0 && <span className="delta" style={{ color: 'var(--sn-red)' }}>{pipe.dead} 离线</span>}
        </span>
      </div>
      <div className="pipe-block">
        <span className="pipe-k">今日收录</span>
        <span className="pipe-v">{ingested != null ? `${ingested} 篇` : '…'}</span>
      </div>
      <div className="pipe-block">
        <span className="pipe-k" title="统计对象 = wiki md frontmatter（llm-wiki-2.0 归档）；管线推进实际读写 DB knowledge_items.lifecycle，两者数字本就不同">管线漏斗</span>
        <span className="pipe-v pipe-funnel">
          {pipe?.funnel
            ? pipe.funnel.map(f => (
              <span className="fs" key={f.stage}>
                <i>{f.stage.replace(/^kl:/, '')}</i>
                <b className="num">{f.count}</b>
              </span>
            ))
            : '…'}
        </span>
      </div>
      <div className="pipe-block">
        <span className="pipe-k">队列</span>
        <span className="pipe-v">
          {pipe?.queue
            ? <>
              {pipe.queue.pending} 待 · {pipe.queue.running} 运
              {pipe.queue.error > 0 && (
                <span className="delta" style={{ color: 'var(--sn-amber)' }}>{pipe.queue.error} 异常</span>
              )}
            </>
            : '…'}
        </span>
      </div>
      <div className="pipe-live">
        <div className="beat-row">
          <span className="pulse" aria-hidden="true" />
          <span className="beat-label">PIPELINE LIVE</span>
        </div>
        {/* B 批收尾 (DEV-0194): 灯数 40→16 缩减宽度, 让「队列 + PIPELINE LIVE」保持同行
            (超出部分省略; 完整分布见 aria-label 与 /secnews/pipeline 源矩阵) */}
        <div
          className="beat-lights"
          role="img"
          aria-label={pipe ? `${pipe.total} 个采集源: ${pipe.active} 正常, ${pipe.stale} 重试中, ${pipe.dead} 离线 (图示前 ${Math.min(16, pipe.sources.length)} 个)` : '加载中'}
        >
          {pipe?.sources.slice(0, 16).map((s, idx) => (
            <i key={`${s.category}-${s.source_name}-${idx}`} className={s.status === 'stale' ? 'warm' : s.status === 'dead' ? 'dead' : undefined} />
          ))}
        </div>
      </div>
    </section>
  );
}