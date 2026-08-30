/**
 * AgentRunnerCard — pi 轻量级执行 agent 面板 (v0.6.3 三层架构执行层)
 *
 * runner 可用性 + 任务执行 (路由: preferred_agent > task_types > default)。
 * 数据源: GET /api/agents/available · POST /api/agents/run
 */
import { useCallback, useEffect, useState } from 'react';

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
        setLoadError(`runner 面板加载失败 (${r.status})`);
        return;
      }
      const d = await r.json();
      setAgents(d.agents ?? []);
      setDefaultAgent(d.default_agent ?? 'builtin');
      setAgent(prev => prev || d.default_agent || 'builtin');
    } catch {
      setLoadError('runner 面板加载失败: 网络或后端不可达');
    }
  }, []);

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
        setResult({ ok: false, agent: null, error: `执行失败 (${r.status})` });
        return;
      }
      setResult(await r.json());
    } catch {
      setResult({ ok: false, agent: null, error: '执行失败: 网络或后端不可达' });
    } finally {
      setRunning(false);
    }
  };

  // 任务类型候选 = 全部 runner 的 task_types 并集
  const taskTypeOptions = Array.from(new Set(agents.flatMap(a => a.task_types)));
  const selected = agents.find(a => a.name === agent);

  return (
    <div className="p-3 rounded-[var(--radius-sm)]" style={{ border: '1px solid var(--border-color)' }}>
      <h3 className="text-xs font-mono font-medium mb-2" style={{ color: 'var(--text-primary)' }}>
        执行 Agent
        <span className="ml-2 text-[9px] font-normal" style={{ color: 'var(--text-muted)' }}>
          dsh 决策 → CLI agent 执行 (三层架构执行层)
        </span>
      </h3>

      {loadError && (
        <p className="text-[10px] font-mono mb-2" style={{ color: 'var(--color-error)' }}>{loadError}</p>
      )}

      {/* runner 可用性 */}
      {agents.length > 0 && (
        <div className="flex flex-wrap gap-1.5 mb-2">
          {agents.map(a => (
            <button key={a.name} onClick={() => setAgent(a.name)}
              className="text-[10px] font-mono px-2 py-0.5 rounded"
              style={{
                color: agent === a.name ? 'var(--accent)' : a.available ? 'var(--text-secondary)' : 'var(--text-disabled)',
                backgroundColor: agent === a.name ? 'var(--accent-soft)' : 'var(--bg-hover)',
                border: '1px solid var(--border-color)',
              }}
              title={a.available ? `${a.protocol} · timeout ${a.timeout_seconds}s` : 'CLI 未安装'}>
              {a.name}{a.external ? '' : ' (内置)'}{a.available ? '' : ' ✗'}
            </button>
          ))}
        </div>
      )}

      {/* 执行表单 */}
      <div className="space-y-1.5">
        <div className="flex items-center gap-1.5">
          <select value={agent} onChange={e => setAgent(e.target.value)}
            className="px-2 py-1 text-[11px] font-mono rounded w-36"
            style={{ backgroundColor: 'var(--bg-hover)', border: '1px solid var(--border-color)', color: 'var(--text-primary)' }}>
            <option value="">自动路由 (默认 {defaultAgent})</option>
            {agents.map(a => <option key={a.name} value={a.name}>{a.name}</option>)}
          </select>
          <input value={taskType} onChange={e => setTaskType(e.target.value)} list="agent-task-types"
            placeholder="task_type"
            className="flex-1 px-2 py-1 text-[11px] font-mono rounded"
            style={{ backgroundColor: 'var(--bg-hover)', border: '1px solid var(--border-color)', color: 'var(--text-primary)' }} />
          <datalist id="agent-task-types">
            {taskTypeOptions.map(t => <option key={t} value={t} />)}
          </datalist>
        </div>
        <textarea value={input} onChange={e => setInput(e.target.value)} rows={3}
          placeholder={selected?.external ? `任务书 (由 ${selected.name} 执行, timeout ${selected.timeout_seconds}s)...` : '任务输入 (builtin → ai_hub LLM)...'}
          className="w-full px-2 py-1.5 text-[11px] font-mono rounded resize-y"
          style={{ backgroundColor: 'var(--bg-hover)', border: '1px solid var(--border-color)', color: 'var(--text-primary)' }} />
        <div className="flex items-center gap-1.5">
          <input value={workspace} onChange={e => setWorkspace(e.target.value)}
            placeholder="workspace (可选, 仅 codegarden/<project>/)"
            className="flex-1 px-2 py-1 text-[11px] font-mono rounded"
            style={{ backgroundColor: 'var(--bg-hover)', border: '1px solid var(--border-color)', color: 'var(--text-primary)' }} />
          <button onClick={run} disabled={running || !input.trim()}
            className="btn-secondary text-[10px] px-3 py-1 shrink-0">
            {running ? '执行中...' : '执行'}
          </button>
        </div>
      </div>

      {/* 结果 */}
      {result && (
        <div className="mt-2 p-2 rounded text-[10px] font-mono"
          style={{
            backgroundColor: 'var(--bg-hover)',
            border: `1px solid ${result.ok ? 'var(--color-success)' : 'var(--color-error)'}`,
          }}>
          <div style={{ color: 'var(--text-muted)' }}>
            agent={result.agent ?? '–'}{result.duration_ms != null ? ` · ${result.duration_ms}ms` : ''}
          </div>
          <div className="mt-1 whitespace-pre-wrap" style={{
            color: result.ok ? 'var(--text-primary)' : 'var(--color-error)',
          }}>
            {result.ok ? result.result : result.error}
          </div>
        </div>
      )}
    </div>
  );
}
