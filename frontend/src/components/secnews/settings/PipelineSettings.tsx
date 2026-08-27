/**
 * PipelineSettings — 管线参数配置 (S3-4)
 *
 * 展示 KL 管线运行参数 + dsh 连接状态 + LLM 模型档位说明。
 * 数据源: GET /api/kl/pipeline/stats · GET /api/llm/status · GET /api/dsh/health
 */
import { useState, useEffect, useCallback } from 'react';

interface PipelineStats {
  queue?: { pending?: number; running?: number; error?: number };
  funnel?: Array<{ stage: string; count: number }>;
}

interface LLMStatus {
  enabled?: boolean;
  providers?: Record<string, { status?: string; model?: string }>;
}

interface DshHealth {
  status?: string;
  fallback?: string;
  endpoint?: string;
}

export function PipelineSettings() {
  const [pipeline, setPipeline] = useState<PipelineStats | null>(null);
  const [llm, setLlm] = useState<LLMStatus | null>(null);
  const [dsh, setDsh] = useState<DshHealth | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const [pRes, lRes, dRes] = await Promise.all([
        fetch('/api/secnews/pipeline'),
        fetch('/api/llm/status'),
        fetch('/api/dsh/health'),
      ]);
      if (pRes.ok) setPipeline(await pRes.json());
      if (lRes.ok) setLlm(await lRes.json());
      if (dRes.ok) setDsh(await dRes.json());
    } catch { /* silent */ } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  return (
    <div className="space-y-3">
      {/* KL 管线参数 */}
      <div className="p-3 rounded-[var(--radius-sm)]" style={{ border: '1px solid var(--border-color)' }}>
        <h3 className="text-xs font-mono font-medium mb-2" style={{ color: 'var(--text-primary)' }}>KL 管线</h3>
        {!loading && pipeline?.queue && (
          <div className="grid grid-cols-3 gap-2 mb-2">
            {([
              ['pending', '待处理'], ['running', '运行中'], ['error', '失败'],
            ] as const).map(([key, label]) => (
              <div key={key} className="text-center p-1.5 rounded" style={{ backgroundColor: 'var(--bg-hover)' }}>
                <div className="text-base font-mono font-bold"
                  style={{ color: key === 'error' ? 'var(--color-error)' : 'var(--text-primary)' }}>
                  {pipeline.queue?.[key] ?? 0}
                </div>
                <div className="text-[9px]" style={{ color: 'var(--text-muted)' }}>{label}</div>
              </div>
            ))}
          </div>
        )}
        <div className="text-[10px] font-mono space-y-0.5" style={{ color: 'var(--text-muted)' }}>
          <div>阶段: kl:raw → refine → link → structure → publish</div>
          <div>重试上限: 5 次 · Kickoff 延迟: 45s · 批大小: 20</div>
          <div>心跳消费: 每 60s drain_due(50) + 每 10min sweep</div>
        </div>
      </div>

      {/* LLM 模型档位 */}
      <div className="p-3 rounded-[var(--radius-sm)]" style={{ border: '1px solid var(--border-color)' }}>
        <h3 className="text-xs font-mono font-medium mb-2" style={{ color: 'var(--text-primary)' }}>模型档位</h3>
        <div className="text-[10px] font-mono space-y-1">
          <div className="flex justify-between">
            <span style={{ color: 'var(--text-secondary)' }}>LLM 总开关</span>
            <span style={{ color: llm?.enabled ? 'var(--color-success)' : 'var(--color-error)' }}>
              {llm?.enabled ? 'ON' : 'OFF'}
            </span>
          </div>
          <div className="flex justify-between">
            <span style={{ color: 'var(--text-secondary)' }}>refine / 打标</span>
            <span style={{ color: 'var(--accent)' }}>flash 档</span>
          </div>
          <div className="flex justify-between">
            <span style={{ color: 'var(--text-secondary)' }}>deep_read / assess</span>
            <span style={{ color: 'var(--color-warning)' }}>heavy 档（点击触发）</span>
          </div>
          <div className="flex justify-between">
            <span style={{ color: 'var(--text-secondary)' }}>embed / rerank</span>
            <span style={{ color: 'var(--text-muted)' }}>local ollama (P3)</span>
          </div>
          {llm?.providers && Object.entries(llm.providers).map(([name, p]) => (
            <div key={name} className="flex justify-between">
              <span style={{ color: 'var(--text-muted)' }}>provider: {name}</span>
              <span style={{
                color: p.status === 'ok' ? 'var(--color-success)' : 'var(--color-error)',
              }}>
                {p.model ?? name} [{p.status ?? '?'}]
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* dsh 连接 */}
      <div className="p-3 rounded-[var(--radius-sm)]" style={{ border: '1px solid var(--border-color)' }}>
        <h3 className="text-xs font-mono font-medium mb-2" style={{ color: 'var(--text-primary)' }}>dsh 连接</h3>
        {dsh ? (
          <div className="text-[10px] font-mono space-y-1">
            <div className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-full inline-block"
                style={{
                  backgroundColor:
                    dsh.status === 'connected' ? 'var(--color-success)' :
                    dsh.status === 'disconnected' ? 'var(--color-warning)' :
                    'var(--color-error)',
                }} />
              <span style={{ color: 'var(--text-primary)' }}>
                {dsh.status === 'connected' ? 'connected' : dsh.status}
              </span>
              {dsh.fallback && dsh.fallback !== 'none' && (
                <span style={{ color: 'var(--text-muted)' }}>
                  (fallback: {dsh.fallback})
                </span>
              )}
            </div>
            {dsh.endpoint && (
              <div style={{ color: 'var(--text-muted)' }}>
                endpoint: {dsh.endpoint}
              </div>
            )}
          </div>
        ) : (
          <div className="flex items-center gap-2 text-[10px] font-mono">
            <span className="w-2 h-2 rounded-full inline-block"
              style={{ backgroundColor: 'var(--color-warning)' }} />
            <span style={{ color: 'var(--text-muted)' }}>checking...</span>
          </div>
        )}
        <p className="text-[9px] mt-1.5" style={{ color: 'var(--text-muted)', opacity: 0.7 }}>
          DSH 不可达时深度分析自动降级到 LLM 直连兜底
        </p>
      </div>
    </div>
  );
}
