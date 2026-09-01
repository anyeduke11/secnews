/**
 * PipelineSettings — 管线参数配置 (S3-4)
 *
 * KL 管线运行参数 + LLM 模型档位 + 采集源健康 + token 预算
 * + dsh 认知大脑控制面板 (v0.6.3 内置化, 一键启停) + pi 执行 agent 面板。
 * 数据源: GET /api/secnews/pipeline · /api/llm/status · /api/sources/health
 *         dsh/agent 面板自取 /api/dsh/control/* 与 /api/agents/*
 */
import { useState, useEffect, useCallback } from 'react';
import { DshControlCard } from './DshControlCard';
import { AgentRunnerCard } from './AgentRunnerCard';
import { useI18n } from '../../../contexts/I18nContext';

interface PipelineStats {
  queue?: { pending?: number; running?: number; error?: number };
  funnel?: Array<{ stage: string; count: number }>;
}

interface LLMStatus {
  enabled?: boolean;
  providers?: Record<string, { status?: string; model?: string }>;
}

interface SourceHealth {
  category: string;
  source_name: string;
  status: string;
  total_items: number;
}

export function PipelineSettings() {
  const { t } = useI18n();
  const [pipeline, setPipeline] = useState<PipelineStats | null>(null);
  const [llm, setLlm] = useState<LLMStatus | null>(null);
  const [sources, setSources] = useState<SourceHealth[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [pRes, lRes, sRes] = await Promise.all([
        fetch('/api/secnews/pipeline'),
        fetch('/api/llm/status'),
        fetch('/api/sources/health'),
      ]);
      if (pRes.ok) setPipeline(await pRes.json());
      if (lRes.ok) setLlm(await lRes.json());
      if (sRes.ok) {
        const s = await sRes.json();
        setSources(s.sources || []);
      }
      if (!pRes.ok && !lRes.ok) {
        setError(t('settings.load_failed'));
      }
    } catch {
      setError(t('settings.load_failed_network'));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => { refresh(); }, [refresh]);

  return (
    <div className="space-y-3">
      {/* 面板头 + 刷新 */}
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-mono font-semibold" style={{ color: 'var(--text-primary)' }}>{t('settings.title')}</h2>
        <button onClick={refresh} disabled={loading} className="btn-secondary text-[10px] px-2 py-0.5" aria-label={t('settings.refresh')}>
          {loading ? t('settings.refreshing') : t('settings.refresh')}
        </button>
      </div>

      {error && !loading && (
        <div className="p-2 rounded text-[10px] font-mono" style={{ color: 'var(--color-error)', border: '1px solid var(--color-error)' }}>
          {error}
        </div>
      )}

      {/* KL 管线参数 */}
      <div className="p-3 rounded-[var(--radius-sm)]" style={{ border: '1px solid var(--border-color)' }}>
        <h3 className="text-xs font-mono font-medium mb-2" style={{ color: 'var(--text-primary)' }}>{t('settings.kl_pipeline')}</h3>
        {!loading && pipeline?.queue && (
          <div className="grid grid-cols-3 gap-2 mb-2">
            {([
              ['pending', t('settings.queue_pending')], ['running', t('settings.queue_running')], ['error', t('settings.queue_failed')],
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
          <div>{t('settings.kl_stages')}</div>
          <div>{t('settings.kl_meta')}</div>
          <div>{t('settings.kl_heartbeat')}</div>
        </div>
      </div>

      {/* LLM 模型档位 */}
      <div className="p-3 rounded-[var(--radius-sm)]" style={{ border: '1px solid var(--border-color)' }}>
        <h3 className="text-xs font-mono font-medium mb-2" style={{ color: 'var(--text-primary)' }}>{t('settings.model_tier')}</h3>
        <div className="text-[10px] font-mono space-y-1">
          <div className="flex justify-between">
            <span style={{ color: 'var(--text-secondary)' }}>{t('settings.llm_master')}</span>
            <span style={{ color: llm?.enabled ? 'var(--color-success)' : 'var(--color-error)' }}>
              {llm?.enabled ? 'ON' : 'OFF'}
            </span>
          </div>
          <div className="flex justify-between">
            <span style={{ color: 'var(--text-secondary)' }}>{t('settings.refine_flash')}</span>
            <span style={{ color: 'var(--accent)' }}>{t('settings.flash_tier')}</span>
          </div>
          <div className="flex justify-between">
            <span style={{ color: 'var(--text-secondary)' }}>deep_read / assess</span>
            <span style={{ color: 'var(--color-warning)' }}>{t('settings.heavy_tier')}</span>
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

      {/* dsh 认知大脑 (v0.6.3 内置化: 受管子进程 + 前端一键启停 + 配置持久化) */}
      <DshControlCard />

      {/* pi 执行 agent (三层架构执行层) */}
      <AgentRunnerCard />

      {/* 采集源健康 (workbench/SettingsView 并入) */}
      <div className="p-3 rounded-[var(--radius-sm)]" style={{ border: '1px solid var(--border-color)' }}>
        <h3 className="text-xs font-mono font-medium mb-2" style={{ color: 'var(--text-primary)' }}>
          {t('settings.sources_count', { n: sources.length })}
        </h3>
        {sources.length === 0 ? (
          <p className="text-[10px] font-mono" style={{ color: 'var(--text-muted)' }}>{t('settings.no_sources')}</p>
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
        <h3 className="text-xs font-mono font-medium mb-2" style={{ color: 'var(--text-primary)' }}>{t('settings.token_budget')}</h3>
        <p className="text-[10px] font-mono" style={{ color: 'var(--text-muted)' }}>
          {t('settings.no_budget')}
        </p>
      </div>
    </div>
  );
}
