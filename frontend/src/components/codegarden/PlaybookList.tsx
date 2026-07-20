// frontend/src/components/codegarden/PlaybookList.tsx
// M4 Playbook 列表 — 浏览 codegarden/playbooks/*.yml + 查看 YAML + 执行
import { useState } from 'react';
import { Playbook } from '../../types/codegarden';
import { useCodegardenOrchestration } from '../../hooks/useCodegardenOrchestration';
import { Icon } from '../Icon';

export function PlaybookList() {
  const { playbooks, loadingPlaybooks, error, runPlaybook, refreshPlaybooks } = useCodegardenOrchestration();
  const [selected, setSelected] = useState<Playbook | null>(null);
  const [paramsJson, setParamsJson] = useState('{}');
  const [running, setRunning] = useState(false);
  const [toast, setToast] = useState<{ kind: 'ok' | 'err'; msg: string } | null>(null);

  const flash = (kind: 'ok' | 'err', msg: string) => {
    setToast({ kind, msg });
    setTimeout(() => setToast(null), 3000);
  };

  const handleRun = async () => {
    if (!selected) return;
    let params = {};
    try { params = JSON.parse(paramsJson || '{}'); }
    catch { flash('err', 'params 不是有效的 JSON'); return; }

    setRunning(true);
    try {
      const r = await runPlaybook(selected.name, params);
      flash('ok', `已触发 (task #${r.task_id}, ${r.steps_count} 步)`);
    } catch (e: any) {
      flash('err', e?.message || String(e));
    } finally {
      setRunning(false);
    }
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
        <h3 className="text-sm font-bold" style={{ color: 'var(--text-primary)' }}>
          Playbook <span className="text-[10px] font-normal" style={{ color: 'var(--text-muted)' }}>({playbooks.length})</span>
        </h3>
        <button onClick={refreshPlaybooks} className="btn-ghost px-2 py-1.5 text-xs" title="刷新">
          <Icon><polyline points="23 4 23 10 17 10" /><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" /></Icon>
        </button>
      </div>

      {loadingPlaybooks ? (
        <div className="text-xs text-center py-6" style={{ color: 'var(--text-muted)' }}>加载中…</div>
      ) : error ? (
        <div className="text-xs text-center py-6" style={{ color: '#e85d5d' }}>{error}</div>
      ) : playbooks.length === 0 ? (
        <div className="text-xs text-center py-6" style={{ color: 'var(--text-muted)' }}>
          暂无 Playbook，请在 codegarden/playbooks/ 目录创建 .yml 文件
        </div>
      ) : (
        <div className="grid gap-2" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))' }}>
          {playbooks.map(pb => (
            <div
              key={pb.name}
              onClick={() => { setSelected(pb); setParamsJson('{}'); }}
              className="rounded-[var(--radius-sm)] p-2.5 cursor-pointer transition-colors"
              style={{
                backgroundColor: 'var(--bg-elevated)',
                border: '1px solid var(--border-color)',
                borderLeft: selected?.name === pb.name ? '3px solid var(--color-ai)' : '3px solid transparent',
              }}
            >
              <div className="text-xs font-semibold truncate" style={{ color: 'var(--text-primary)' }} title={pb.name}>
                {pb.name}
              </div>
              <div className="text-[10px] mt-0.5 font-mono" style={{ color: 'var(--text-muted)' }}>
                {pb.size} bytes · {pb.path.split('/').pop()}
              </div>
            </div>
          ))}
        </div>
      )}

      {selected && (
        <div className="mt-3">
          <div className="text-[11px] mb-1.5" style={{ color: 'var(--text-muted)' }}>
            YAML 内容 — {selected.name}
          </div>
          <pre
            className="text-[10px] font-mono p-2 rounded max-h-80 overflow-auto"
            style={{ backgroundColor: 'var(--bg-hover)', color: 'var(--text-secondary)', whiteSpace: 'pre-wrap' }}
          >
            {selected.content}
          </pre>
          <div className="mt-2">
            <label className="text-[10px]" style={{ color: 'var(--text-muted)' }}>执行参数 (JSON)</label>
            <textarea
              value={paramsJson}
              onChange={(e) => setParamsJson(e.target.value)}
              rows={3}
              className="w-full text-[10px] px-2 py-1 rounded font-mono mt-1"
              style={{ backgroundColor: 'var(--bg-hover)', color: 'var(--text-primary)', border: '1px solid var(--border-color)' }}
            />
          </div>
          <button
            onClick={handleRun}
            disabled={running}
            className="btn-ghost mt-2 px-3 py-1.5 text-[11px]"
            style={{ color: 'var(--color-ai)', opacity: running ? 0.6 : 1 }}
          >
            {running ? '执行中…' : '▶ 执行 Playbook'}
          </button>
        </div>
      )}

      {toast && (
        <div
          className="fixed bottom-4 left-1/2 -translate-x-1/2 px-3 py-1.5 rounded text-xs z-50"
          style={{ backgroundColor: toast.kind === 'ok' ? '#00c96a' : '#e85d5d', color: '#fff' }}
        >
          {toast.msg}
        </div>
      )}
    </div>
  );
}
