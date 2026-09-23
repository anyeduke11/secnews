/** KLQueueCard — KL 管线队列只读卡 (原 pipeline cat 拆出, 数据 GET /api/secnews/pipeline) */
import { useCallback, useEffect, useState } from 'react';
import { getSecNewsPipeline } from '../../api/secnews';

interface PipelineStats { queue?: { pending?: number; running?: number; error?: number } }

export function KLQueueCard() {
  const [pipeline, setPipeline] = useState<PipelineStats | null>(null);
  const refresh = useCallback(async () => {
    try { setPipeline(await getSecNewsPipeline<PipelineStats>()); } catch { setPipeline(null); }
  }, []);
  useEffect(() => { void refresh(); }, [refresh]);
  const q = pipeline?.queue;
  const cells = [
    ['pending', '待处理', 'mint'], ['running', '进行中', 'mint'], ['error', '失败', 'red'],
  ] as const;
  return (
    <div className="st-card">
      <h3>KL 管线队列</h3>
      <p className="st-section-desc">raw → chunk → score → rank 多阶段管线的运行队列与心跳。</p>
      {q ? (
        <div className="st-cellgrid">
          {cells.map(([key, label, color]) => (
            <div key={key} className="st-cell">
              <span className="st-cellk">{label}</span>
              <span className={`st-cellv sm ${color}`}>{q[key] ?? 0}</span>
            </div>
          ))}
        </div>
      ) : <p className="st-cellnote">队列状态不可用。</p>}
    </div>
  );
}
