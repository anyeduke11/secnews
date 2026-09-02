/**
 * ScenarioModelsPanel — 三场景模型配置面板 (V2 哨兵化)
 *
 * 单一来源 UI 组件,被三个入口复用:
 *   1. /settings?cat=image_models → SettingsPage 主区 (新)
 *   2. /settings?cat=collection   → QualitySettings 子面板
 *   3. ImageStudio 主页内容 (DEPRECATED thin wrapper)
 *
 * 数据契约: POST /api/settings/scenario-model {scenario, model, actor}
 *   → 响应 {status, scenario, old_model, new_model}
 * 优先级: env HOTSPOT_SCENARIO_*_MODEL > settings.kv > yaml task_overrides > 兜底
 *
 * 设计: st-rule 行式布局, 每行 st-label(scenario) + st-input + st-btn;
 *       compact 模式仅渲染 input+save 行, 不显示标题/描述 (兼容嵌入场景)
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
const SCENARIO_LABEL: Record<Scenario, string> = {
  deep: '深度 (DEEP READ)',
  light: '轻度 (FLASH)',
  image: '图片 (IMAGE)',
};

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
    <div data-testid={`${scope}-panel`}>
      {!compact && (
        <p className="st-section-desc">
          优先级: env HOTSPOT_SCENARIO_*_MODEL &gt; 本设置 (settings.kv) &gt; yaml task_overrides &gt; 兜底。
          模型选择 = 路由选择; 密钥仍走加密保险箱 (Batch ⑥)。
        </p>
      )}
      <div className="st-section-body">
        {SCENARIO_ORDER.map((scenario) => {
          const current = scenarioModels[scenario] || '';
          const isSaving = savingScenario === scenario;
          const isDirty = current !== (initial?.[scenario] ?? '');
          return (
            <div key={scenario} className="st-rule" data-testid={`${scope}-row-${scenario}`}>
              <div>
                <p className="st-label">{SCENARIO_LABEL[scenario]}</p>
                <p className="st-key">scenario.{scenario}</p>
              </div>
              <div className="st-ctrl">
                <div className="st-ctrlrow">
                  <input
                    value={current}
                    onChange={(e) => setScenarioModels((m) => ({ ...m, [scenario]: e.target.value }))}
                    placeholder="留空走 yaml router 默认"
                    data-testid={`${scope}-input-${scenario}`}
                    className="st-input"
                    style={{ maxWidth: 280 }}
                    aria-label={`${scenario} model`}
                  />
                  <button
                    type="button"
                    onClick={() => saveScenarioModel(scenario, current.trim())}
                    disabled={isSaving || !isDirty}
                    data-testid={`${scope}-save-${scenario}`}
                    className="st-btn primary"
                    style={{ minWidth: 70 }}
                  >
                    {isSaving ? '保存中...' : '保存'}
                  </button>
                </div>
              </div>
            </div>
          );
        })}
        {scenarioMessage && (
          <p
            className={`st-cellnote ${scenarioMessage.type === 'ok' ? '' : 'is-bad'}`}
            data-testid={`${scope}-message`}
            style={{ color: scenarioMessage.type === 'ok' ? 'var(--sn-mint)' : 'var(--sn-red)' }}
          >
            {scenarioMessage.text}
          </p>
        )}
      </div>
    </div>
  );
}

export default ScenarioModelsPanel;