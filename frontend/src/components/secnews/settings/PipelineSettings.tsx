/**
 * PipelineSettings — 管线参数配置 (S3-4)
 *
 * KL 管线运行参数 + dsh 连接状态 + LLM 模型档位 + 采集源健康 + token 预算。
 * v0.6.3: workbench/SettingsView 采集源/预算两节并入; 刷新按钮接线 + 失败态显式呈现。
 * 数据源: GET /api/secnews/pipeline · GET /api/llm/status · GET /api/dsh/health · GET /api/sources/health
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
  note?: string;        // P1-2: 降级为实验性时携带说明
}

interface SourceHealth {
  category: string;
  source_name: string;
  status: string;
  total_items: number;
}

export function PipelineSettings() {
  const [pipeline, setPipeline] = useState<PipelineStats | null>(null);
  const [llm, setLlm] = useState<LLMStatus | null>(null);
  const [dsh, setDsh] = useState<DshHealth | null>(null);
  const [sources, setSources] = useState<SourceHealth[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [dshGateOff, setDshGateOff] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [pRes, lRes, dRes, sRes] = await Promise.all([
        fetch('/api/secnews/pipeline'),
        fetch('/api/llm/status'),
        fetch('/api/dsh/health'),
        fetch('/api/sources/health'),
      ]);
      if (pRes.ok) setPipeline(await pRes.json());
      if (lRes.ok) setLlm(await lRes.json());
      // dsh gate 关闭 → 404, 如实呈现而非永远 checking
      if (dRes.status === 404) {
        setDsh(null);
        setDshGateOff(true);
      } else if (dRes.ok) {
        setDsh(await dRes.json());
        setDshGateOff(false);
      }
      if (sRes.ok) {
        const s = await sRes.json();
        setSources(s.sources || []);
      }
      if (!pRes.ok && !lRes.ok) {
        setError('设置面板加载失败: 后端不可达');
      }
    } catch {
      setError('设置面板加载失败: 网络或后端不可达');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  return (
    <div className="space-y-3">
      {/* 面板头 + 刷新 */}
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-mono font-semibold" style={{ color: 'var(--text-primary)' }}>设置</h2>
        <button onClick={refresh} disabled={loading} className="btn-secondary text-[10px] px-2 py-0.5">
          {loading ? '刷新中...' : '刷新'}
        </button>
      </div>

      {error && !loading && (
        <div className="p-2 rounded text-[10px] font-mono" style={{ color: 'var(--color-error)', border: '1px solid var(--color-error)' }}>
          {error}
        </div>
      )}

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
        {dshGateOff ? (
          <div className="flex items-center gap-2 text-[10px] font-mono">
            <span className="w-2 h-2 rounded-full inline-block"
              style={{ backgroundColor: 'var(--text-disabled)' }} />
            <span style={{ color: 'var(--text-muted)' }}>
              dsh 桥接未启用 (feature_gates.toml dsh=false, /api/dsh/* 返回 404)
            </span>
          </div>
        ) : dsh ? (
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
            {dsh.note && (
              <div style={{ color: 'var(--text-muted)', marginTop: '4px', fontSize: '9px' }}>
                {dsh.note}
              </div>
            )}
          </div>
        ) : (
          <div className="flex items-center gap-2 text-[10px] font-mono">
            <span className="w-2 h-2 rounded-full inline-block"
              style={{ backgroundColor: 'var(--color-warning)' }} />
            <span style={{ color: 'var(--text-muted)' }}>
              {loading ? 'checking...' : 'dsh 状态加载失败, 点击刷新重试'}
            </span>
          </div>
        )}
        <p className="text-[9px] mt-1.5" style={{ color: 'var(--text-muted)', opacity: 0.7 }}>
          DSH 不可达时深度分析自动降级到 LLM 直连兜底
        </p>
      </div>

      {/* 采集源健康 (workbench/SettingsView 并入) */}
      <div className="p-3 rounded-[var(--radius-sm)]" style={{ border: '1px solid var(--border-color)' }}>
        <h3 className="text-xs font-mono font-medium mb-2" style={{ color: 'var(--text-primary)' }}>
          采集源 · {sources.length}
        </h3>
        {sources.length === 0 ? (
          <p className="text-[10px] font-mono" style={{ color: 'var(--text-muted)' }}>暂无源数据</p>
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-1">
            {sources.slice(0, 18).map(s => (
              <div key={`${s.category}-${s.source_name}`} className="text-[10px] font-mono flex items-center gap-1">
                <span className="w-1.5 h-1.5 rounded-full inline-block shrink-0" style={{
                  backgroundColor: s.status === 'active' ? 'var(--color-success)' :
                    s.status === 'stale' ? 'var(--color-warning)' : 'var(--color-error)',
                }} />
                <span style={{ color: 'var(--text-secondary)' }} className="truncate">{s.source_name}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* token 预算 (workbench/SettingsView 并入, 后端预算配置 Phase 5 实装) */}
      <div className="p-3 rounded-[var(--radius-sm)]" style={{ border: '1px solid var(--border-color)' }}>
        <h3 className="text-xs font-mono font-medium mb-2" style={{ color: 'var(--text-primary)' }}>token 预算</h3>
        <p className="text-[10px] font-mono" style={{ color: 'var(--text-muted)' }}>
          暂无预算配置（Phase 5 实装; 当前用量见底部状态栏 token 日用量）
        </p>
      </div>
    </div>
  );
}
