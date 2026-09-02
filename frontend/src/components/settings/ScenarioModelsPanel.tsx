/**
 * ScenarioModelsPanel — 三场景模型配置面板 (v0.7.4-image 提取)
 *
 * 单一来源 UI 组件,被两个入口复用:
 *   1. /secnews/settings → QualitySettings 折叠面板 (默认折叠)
 *   2. /secnews/image   → ImageStudio 主页内容 (复用同一份配置)
 *
 * 数据契约: POST /api/settings/scenario-model {scenario, model, actor}
 *   → 响应 {status, scenario, old_model, new_model}
 * 优先级: env HOTSPOT_SCENARIO_*_MODEL > settings.kv > yaml task_overrides > 兜底
 *
 * 状态独立于父组件 (useState) — 适合作为可独立打开/折叠的子面板。
 * 如需父组件感知保存状态,可在 props.onSaved 回调里抛事件。
 */
import { useState, useCallback } from 'react';

export type Scenario = 'deep' | 'light' | 'image';

export interface ScenarioModels {
  deep: string;
  light: string;
  image: string;
}

export interface ScenarioModelsPanelProps {
  /** 初始值 (由父组件传入; 通常从 /api/settings/... 拉出) */
  initial?: Partial<ScenarioModels>;
  /** 父组件 id, 仅用于 vitest data-testid 区分 */
  scope?: string;
  /** 保存成功回调 (用于跨页同步提示) */
  onSaved?: (scenario: Scenario, oldModel: string | null, newModel: string) => void;
  /** 紧凑模式: 不显示标题/描述, 仅输入行 (供 ImageStudio 嵌入复用) */
  compact?: boolean;
}

type ScenarioMessage = { type: 'ok' | 'error'; text: string } | null;

const SCENARIO_ORDER: readonly Scenario[] = ['deep', 'light', 'image'] as const;

export function ScenarioModelsPanel({ initial, scope = 'scenario', onSaved, compact = false }: ScenarioModelsPanelProps) {
  const [scenarioModels, setScenarioModels] = useState<ScenarioModels>({
    deep: initial?.deep ?? '',
    light: initial?.light ?? '',
    image: initial?.image ?? '',
  });
  const [savingScenario, setSavingScenario] = useState<Scenario | null>(null);
  const [scenarioMessage, setScenarioMessage] = useState<ScenarioMessage>(null);

  const saveScenarioModel = useCallback(async (scenario: Scenario, model: string) => {
    setSavingScenario(scenario);
    setScenarioMessage(null);
    try {
      const r = await fetch('/api/settings/scenario-model', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ scenario, model, actor: 'web' }),
      });
      const d = await r.json();
      if (r.ok && d.status === 'ok') {
        setScenarioMessage({ type: 'ok', text: `${scenario}: ${d.old_model ?? '(无)'} → ${d.new_model}` });
        onSaved?.(scenario, d.old_model ?? null, d.new_model);
      } else {
        setScenarioMessage({ type: 'error', text: d.message || '保存失败' });
      }
    } catch {
      setScenarioMessage({ type: 'error', text: '保存失败 (网络错误)' });
    } finally {
      setSavingScenario(null);
    }
  }, [onSaved]);

  return (
    <div
      className="px-3 py-2 space-y-2"
      style={compact ? {} : { borderTop: '1px solid var(--border-color)' }}
      data-testid={`${scope}-panel`}
    >
      {!compact && (
        <p className="text-[10px]" style={{ color: 'var(--text-muted)' }}>
          优先级: env HOTSPOT_SCENARIO_*_MODEL &gt; 本设置 (settings.kv) &gt; yaml task_overrides &gt; 兜底。
          模型选择 = 路由选择; 密钥仍走加密保险箱 (Batch ⑥)。
        </p>
      )}
      {SCENARIO_ORDER.map((scenario) => {
        const current = scenarioModels[scenario] || '';
        const isSaving = savingScenario === scenario;
        const isDirty = current !== (initial?.[scenario] ?? '');
        return (
          <div key={scenario} className="flex items-center gap-2" data-testid={`${scope}-row-${scenario}`}>
            <span
              className="text-[11px] font-mono w-12"
              style={{ color: 'var(--text-secondary)' }}
            >
              {scenario}
            </span>
            <input
              value={current}
              onChange={(e) => setScenarioModels((m) => ({ ...m, [scenario]: e.target.value }))}
              placeholder="留空走 yaml router 默认"
              data-testid={`${scope}-input-${scenario}`}
              className="flex-1 px-2 py-1 text-xs font-mono rounded-[var(--radius-sm)] focus-ring"
              style={{
                backgroundColor: 'var(--bg-hover)',
                border: '1px solid var(--border-color)',
                color: 'var(--text-primary)',
              }}
            />
            <button
              onClick={() => saveScenarioModel(scenario, current.trim())}
              disabled={isSaving || !isDirty}
              data-testid={`${scope}-save-${scenario}`}
              className="px-2 py-1 text-[10px] rounded-[var(--radius-sm)]"
              style={{
                backgroundColor: isDirty ? 'var(--color-general)' : 'var(--bg-hover)',
                color: isDirty ? 'var(--text-on-color)' : 'var(--text-muted)',
                opacity: isSaving ? 0.6 : 1,
              }}
            >
              {isSaving ? '保存中...' : '保存'}
            </button>
          </div>
        );
      })}
      {scenarioMessage && (
        <p
          className="text-[10px]"
          data-testid={`${scope}-message`}
          style={{
            color: scenarioMessage.type === 'ok' ? 'var(--color-general)' : 'var(--color-error)',
          }}
        >
          {scenarioMessage.text}
        </p>
      )}
    </div>
  );
}

export default ScenarioModelsPanel;