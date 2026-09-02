/**
 * AgentRunnerCard — pi 轻量级执行 agent 面板 (v0.6.3 三层架构执行层, Sentinel V2 token)。
 *
 * runner 可用性 + 任务执行 (路由: preferred_agent > task_types > default)。
 * 数据源: GET /api/agents/available · POST /api/agents/run
 */
import { useCallback, useEffect, useState } from 'react';
import { useI18n } from '../../../contexts/I18nContext';

interface AgentInfo {
  name: string;
  protocol: string;
  task_types: string[];
  timeout_seconds: number;
  external: boolean;
  available: boolean;
}

interface RunResult {
  ok: boolean;
  agent: string | null;
  protocol?: string;
  result?: string | null;
  error?: string | null;
  duration_ms?: number;
}

export function AgentRunnerCard() {
  const { t } = useI18n();
  const [agents, setAgents] = useState<AgentInfo[]>([]);
  const [defaultAgent, setDefaultAgent] = useState('builtin');
  const [loadError, setLoadError] = useState<string | null>(null);

  const [agent, setAgent] = useState('');
  const [taskType, setTaskType] = useState('execute');
  const [input, setInput] = useState('');
  const [workspace, setWorkspace] = useState('');
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<RunResult | null>(null);

  const load = useCallback(async () => {
    try {
      const r = await fetch('/api/agents/available');
      if (!r.ok) {
        setLoadError(`${t('runner.load_failed')} (${r.status})`);
        return;
      }
      const d = await r.json();
      setAgents(d.agents ?? []);
      setDefaultAgent(d.default_agent ?? 'builtin');
      setAgent(prev => prev || d.default_agent || 'builtin');
    } catch {
      setLoadError(t('runner.load_failed_network'));
    }
  }, [t]);

  useEffect(() => { load(); }, [load]);

  const run = async () => {
    if (!input.trim()) return;
    setRunning(true);
    setResult(null);
    try {
      const r = await fetch('/api/agents/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          task_type: taskType.trim(),
          input: input,
          preferred_agent: agent || null,
          workspace: workspace.trim() || null,
        }),
      });
      if (!r.ok) {
        setResult({ ok: false, agent: null, error: `${t('runner.execute_failed')} (${r.status})` });
        return;
      }
      setResult(await r.json());
    } catch {
      setResult({ ok: false, agent: null, error: t('runner.execute_failed_network') });
    } finally {
      setRunning(false);
    }
  };

  // 任务类型候选 = 全部 runner 的 task_types 并集
  const taskTypeOptions = Array.from(new Set(agents.flatMap(a => a.task_types)));
  const selected = agents.find(a => a.name === agent);

  return (
    <div
      style={{
        padding: 'var(--sn-cell-pad)',
        borderRadius: 'var(--sn-radius-md)',
        border: '1px solid var(--sn-line)',
        backgroundColor: 'var(--sn-bg-1)',
        display: 'flex',
        flexDirection: 'column',
        gap: 'var(--sn-row)',
      }}
    >
      <h3 style={{
        fontFamily: 'var(--sn-mono)',
        fontSize: 'var(--sn-fs-h3)',
        fontWeight: 'var(--sn-fw-medium)',
        color: 'var(--sn-ink)',
        margin: 0,
      }}>
        {t('runner.card_title')}
        <span style={{
          marginLeft: 12,
          fontSize: 'var(--sn-fs-mute)',
          fontWeight: 'var(--sn-fw-regular)',
          color: 'var(--sn-ink-3)',
        }}>
          {t('runner.card_subtitle')}
        </span>
      </h3>

      {loadError && (
        <p style={{
          fontFamily: 'var(--sn-mono)',
          fontSize: 'var(--sn-fs-mute)',
          color: 'var(--sn-red)',
          margin: 0,
        }}>
          {loadError}
        </p>
      )}

      {/* runner 可用性 */}
      {agents.length > 0 && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
          {agents.map(a => {
            const selected = agent === a.name;
            const tone = selected ? 'mint' : a.available ? 'mute' : 'bad';
            const toneColor = tone === 'mint' ? 'var(--sn-mint)' : tone === 'bad' ? 'var(--sn-red)' : 'var(--sn-ink-2)';
            const toneBg = selected
              ? 'color-mix(in srgb, var(--sn-mint) 14%, transparent)'
              : 'var(--sn-bg-hover)';
            return (
              <button
                key={a.name}
                onClick={() => setAgent(a.name)}
                title={a.available ? `${a.protocol} · timeout ${a.timeout_seconds}s` : t('runner.cli_not_installed')}
                style={{
                  padding: '3px 10px',
                  borderRadius: 'var(--sn-radius-sm)',
                  fontSize: 11,
                  fontFamily: 'var(--sn-mono)',
                  color: toneColor,
                  backgroundColor: toneBg,
                  border: `1px solid ${selected ? 'var(--sn-mint)' : 'var(--sn-line)'}`,
                  cursor: 'pointer',
                }}
              >
                {a.name}{a.external ? '' : t('runner.builtin_tag')}{a.available ? '' : t('runner.unavailable_tag')}
              </button>
            );
          })}
        </div>
      )}

      {/* 执行表单 */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <select
            value={agent} onChange={e => setAgent(e.target.value)}
            className="st-select"
            style={{ width: 144, fontFamily: 'var(--sn-mono)' }}
          >
            <option value="">{t('runner.auto_route', { default: defaultAgent })}</option>
            {agents.map(a => <option key={a.name} value={a.name}>{a.name}</option>)}
          </select>
          <input
            value={taskType} onChange={e => setTaskType(e.target.value)} list="agent-task-types"
            placeholder="task_type"
            className="st-input"
            style={{ flex: 1, fontFamily: 'var(--sn-mono)' }}
          />
          <datalist id="agent-task-types">
            {taskTypeOptions.map(t => <option key={t} value={t} />)}
          </datalist>
        </div>
        <textarea
          value={input} onChange={e => setInput(e.target.value)} rows={3}
          placeholder={
            selected?.external
              ? t('runner.task_input_external', { name: selected.name, timeout: selected.timeout_seconds })
              : t('runner.task_input_builtin')
          }
          className="st-textarea"
          style={{ fontFamily: 'var(--sn-mono)' }}
        />
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <input
            value={workspace} onChange={e => setWorkspace(e.target.value)}
            placeholder={t('runner.workspace_placeholder')}
            className="st-input"
            style={{ flex: 1, fontFamily: 'var(--sn-mono)' }}
          />
          <button
            className="st-btn primary"
            onClick={run}
            disabled={running || !input.trim()}
          >
            {running ? t('runner.executing') : t('runner.execute')}
          </button>
        </div>
      </div>

      {/* 结果 */}
      {result && (
        <div style={{
          padding: 'var(--sn-cell-pad)',
          borderRadius: 'var(--sn-radius-md)',
          fontFamily: 'var(--sn-mono)',
          fontSize: 'var(--sn-fs-mute)',
          backgroundColor: 'var(--sn-bg-hover)',
          border: `1px solid ${result.ok ? 'color-mix(in srgb, var(--sn-mint) 32%, transparent)' : 'color-mix(in srgb, var(--sn-red) 32%, transparent)'}`,
        }}>
          <div style={{ color: 'var(--sn-ink-3)' }}>
            agent={result.agent ?? '–'}{result.duration_ms != null ? ` · ${result.duration_ms}ms` : ''}
          </div>
          <div
            className="mt-1 whitespace-pre-wrap"
            style={{
              color: result.ok ? 'var(--sn-ink)' : 'var(--sn-red)',
              marginTop: 4,
              whiteSpace: 'pre-wrap',
            }}
          >
            {result.ok ? result.result : result.error}
          </div>
        </div>
      )}
    </div>
  );
}