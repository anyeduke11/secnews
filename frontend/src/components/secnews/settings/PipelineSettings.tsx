/**
 * PipelineSettings — 管线参数配置 (S3-4) (V2 哨兵化)
 *
 * KL 管线运行参数 + LLM 模型档位 + 采集源健康 + token 预算
 * + dsh 认知大脑控制面板 (v0.6.3 内置化, 一键启停) + pi 执行 agent 面板。
 * 数据源: GET /api/secnews/pipeline · /api/llm/status · /api/sources/health
 *         dsh/agent 面板自取 /api/dsh/control/* 与 /api/agents/*
 *
 * V2: 全部走 settings-shell.css 的 st-cellgrid / st-section / st-rule / st-chip
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

  const q = pipeline?.queue;
  const queueKeys = [
    ['pending', t('settings.queue_pending'), 'mint'] as const,
    ['running', t('settings.queue_running'), 'mint'] as const,
    ['error', t('settings.queue_failed'), 'red'] as const,
  ];

  return (
    <div className="space-y-3" data-testid="pipeline-settings">
      <div className="st-actionbar" style={{ borderTop: 'none', marginTop: 0, paddingTop: 0 }}>
        {error && !loading && <span className="st-ab-msg bad">{error}</span>}
        <button type="button" className="st-btn ghost" onClick={refresh} disabled={loading}
                aria-label={t('settings.refresh')}>
          {loading ? t('settings.refreshing') : t('settings.refresh')}
        </button>
      </div>

      {/* KL 管线参数 */}
      <section className="st-section" aria-label={t('settings.kl_pipeline')}>
        <h3>{t('settings.kl_pipeline')}</h3>
        <p className="st-section-desc">
          KL 多阶段管线 (raw → chunk → score → rank) 的运行队列与心跳。
        </p>
        <div className="st-section-body">
          {!loading && q && (
            <div className="st-cellgrid">
              {queueKeys.map(([key, label, color]) => (
                <div key={key} className="st-cell">
                  <span className="st-cellk">{label}</span>
                  <span className={`st-cellv sm ${color}`}>{q[key] ?? 0}</span>
                </div>
              ))}
            </div>
          )}
          <div className="st-cellnote">
            <div>{t('settings.kl_stages')}</div>
            <div>{t('settings.kl_meta')}</div>
            <div>{t('settings.kl_heartbeat')}</div>
          </div>
        </div>
      </section>

      {/* LLM 模型档位 */}
      <section className="st-section" aria-label={t('settings.model_tier')}>
        <h3>{t('settings.model_tier')}</h3>
        <p className="st-section-desc">4 档模型档位: master / flash / heavy / embed-rerank; 数据来自 /api/llm/status。</p>
        <div className="st-section-body">
          <div className="st-rule">
            <div><p className="st-label">{t('settings.llm_master')}</p></div>
            <div className="st-ctrl">
              <span className={llm?.enabled ? 'st-chip ok' : 'st-chip bad'}>
                <i aria-hidden />{llm?.enabled ? 'ON' : 'OFF'}
              </span>
            </div>
          </div>
          <div className="st-rule">
            <div><p className="st-label">{t('settings.refine_flash')}</p></div>
            <div className="st-ctrl"><span className="st-chip warn"><i aria-hidden />{t('settings.flash_tier')}</span></div>
          </div>
          <div className="st-rule">
            <div><p className="st-label">deep_read / assess</p></div>
            <div className="st-ctrl"><span className="st-chip warn"><i aria-hidden />{t('settings.heavy_tier')}</span></div>
          </div>
          <div className="st-rule">
            <div><p className="st-label">embed / rerank</p></div>
            <div className="st-ctrl"><span className="st-chip mute"><i aria-hidden />local ollama (P3)</span></div>
          </div>
          {llm?.providers && Object.entries(llm.providers).map(([name, p]) => (
            <div key={name} className="st-rule">
              <div><p className="st-label">provider: {name}</p></div>
              <div className="st-ctrl">
                <span className={p.status === 'ok' ? 'st-chip ok' : 'st-chip bad'}>
                  <i aria-hidden />{p.model ?? name} [{p.status ?? '?'}]
                </span>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* dsh 认知大脑 */}
      <DshControlCard />

      {/* pi 执行 agent */}
      <AgentRunnerCard />

      {/* 采集源健康 */}
      <section className="st-section" aria-label={t('settings.sources_count', { n: sources.length })}>
        <h3>{t('settings.sources_count', { n: sources.length })}</h3>
        <p className="st-section-desc">
          实时源健康 (active=绿 / stale=琥珀 / dead=红)。只显示前 18 个, 完整列表见采集区段。
        </p>
        <div className="st-section-body">
          {sources.length === 0 ? (
            <p className="st-cellnote">{t('settings.no_sources')}</p>
          ) : (
            <div className="st-tilegrid">
              {sources.slice(0, 18).map(s => (
                <div key={`${s.category}-${s.source_name}`}
                     className={`st-tile ${s.status === 'stale' ? 'is-warn' : s.status === 'dead' ? 'is-off' : ''}`}>
                  <p className="st-tile-label">{s.source_name}</p>
                  <p className="st-tile-key">{s.category}</p>
                  <span className={`st-chip ${s.status === 'active' ? 'ok' : s.status === 'stale' ? 'warn' : 'bad'}`}>
                    <i aria-hidden />{s.status}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      </section>

      {/* token 预算 */}
      <section className="st-section" aria-label={t('settings.token_budget')}>
        <h3>{t('settings.token_budget')}</h3>
        <p className="st-cellnote">{t('settings.no_budget')}</p>
      </section>
    </div>
  );
}

export default PipelineSettings;