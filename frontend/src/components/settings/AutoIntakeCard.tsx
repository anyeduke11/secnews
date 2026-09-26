/**
 * settings/AutoIntakeCard — 自动入管规则引擎配置卡 (2026-09-26, 设计稿 §3.1)
 *
 * 高质量 + 命中关注域 (可选) 的资讯自动进入 KL 管线, 每日限量防风暴;
 * 收藏通道不受上限约束 (source='secnews' vs 'secnews_auto')。
 * GET /api/settings/auto-intake 读配置 + 今日已入管; 控件改本地态,
 * 保存按钮统一走 PATCH (service 逐键写 settings.kv + audit_log)。
 */
import { useCallback, useEffect, useState } from 'react';
import { apiFetch } from '../../lib/api';

interface AutoIntakeConfig {
  enabled: boolean;
  min_quality_score: number;
  daily_limit: number;
  require_domain_hit: boolean;
  today_intaken: number;
}

export function AutoIntakeCard() {
  const [cfg, setCfg] = useState<AutoIntakeConfig | null>(null);
  const [loadError, setLoadError] = useState(false);
  const [saving, setSaving] = useState(false);
  const [savedFlash, setSavedFlash] = useState(false);
  const [saveError, setSaveError] = useState(false);
  const [saveMsg, setSaveMsg] = useState<string | null>(null);

  const load = useCallback(() => {
    apiFetch<AutoIntakeConfig>('/api/settings/auto-intake')
      .then((d) => {
        setCfg(d);
        setLoadError(false);
      })
      .catch(() => setLoadError(true));
  }, []);
  useEffect(() => { load(); }, [load]);

  const save = useCallback((next: AutoIntakeConfig) => {
    if (saving) return;
    setSaving(true);
    setSaveError(false);
    apiFetch<AutoIntakeConfig>('/api/settings/auto-intake', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        enabled: next.enabled,
        min_quality_score: next.min_quality_score,
        daily_limit: next.daily_limit,
        require_domain_hit: next.require_domain_hit,
      }),
    })
      .then((d) => {
        setCfg(d);
        setSavedFlash(true);
        setSaveMsg(null);
        window.setTimeout(() => setSavedFlash(false), 1500);
      })
      .catch(async (e) => {
        // 422 = 校验拒绝 (如 daily_limit 越界) — 展示服务端原因而非笼统失败
        let reason: string | null = null;
        try { reason = (await e?.response?.text?.()) || null; } catch { /* ignore */ }
        setSaveMsg(reason ? `保存被拒绝: ${reason}` : null);
        setSaveError(true);
        load(); // 失败回滚到服务端真值
      })
      .finally(() => setSaving(false));
  }, [saving, load]);

  return (
    <div className="st-card" data-testid="auto-intake-card">
      <h3>自动入管</h3>
      <p className="st-section-desc">
        高质量资讯自动进入 KL 管线 (每日限量防风暴); 收藏通道不受上限约束。
        {saving && <span className="st-chip"><i aria-hidden />保存中…</span>}
        {savedFlash && !saving && <span className="st-chip ok"><i aria-hidden />已保存</span>}
        {saveError && (
          <span className="st-chip warn">
            <i aria-hidden />
            {saveMsg || '保存失败'}
          </span>
        )}
      </p>
      {loadError ? (
        <p className="st-cellnote">配置不可用。</p>
      ) : !cfg ? (
        <p className="st-key">加载中…</p>
      ) : (
        <div className="st-section-body">
          <div className="st-cellgrid">
            <div className="st-cell">
              <span className="st-cellk">今日已入管</span>
              <span className="st-cellv sm mint" data-testid="auto-intake-today">{cfg.today_intaken}</span>
            </div>
            <div className="st-cell">
              <span className="st-cellk">每日上限</span>
              <span className="st-cellv sm">{cfg.daily_limit}</span>
            </div>
          </div>
          <div className="st-ctrlrow flex-wrap" style={{ marginTop: 10 }}>
            <button
              type="button"
              className={cfg.enabled ? 'st-btn primary' : 'st-btn'}
              aria-pressed={cfg.enabled}
              data-testid="auto-intake-toggle"
              disabled={saving}
              onClick={() => setCfg({ ...cfg, enabled: !cfg.enabled })}
            >
              {cfg.enabled ? '已开启' : '已关闭'}
            </button>
            <button
              type="button"
              className={cfg.require_domain_hit ? 'st-btn primary' : 'st-btn'}
              aria-pressed={cfg.require_domain_hit}
              data-testid="auto-intake-domain"
              disabled={saving}
              onClick={() => setCfg({ ...cfg, require_domain_hit: !cfg.require_domain_hit })}
            >
              {cfg.require_domain_hit ? '须命中关注域' : '不限关注域'}
            </button>
            <label className="st-key" style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
              质量阈值
              <input
                type="number"
                min={0}
                max={100}
                className="st-input"
                style={{ width: 72 }}
                value={cfg.min_quality_score}
                data-testid="auto-intake-score"
                disabled={saving}
                onChange={(e) => setCfg({ ...cfg, min_quality_score: Number(e.target.value) })}
              />
            </label>
            <label className="st-key" style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
              每日上限
              <input
                type="number"
                min={1}
                max={100}
                className="st-input"
                style={{ width: 72 }}
                value={cfg.daily_limit}
                data-testid="auto-intake-limit"
                disabled={saving}
                onChange={(e) => setCfg({ ...cfg, daily_limit: Number(e.target.value) })}
              />
            </label>
            <button
              type="button"
              className="st-btn primary"
              data-testid="auto-intake-save"
              disabled={saving}
              onClick={() => save(cfg)}
            >
              保存
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
