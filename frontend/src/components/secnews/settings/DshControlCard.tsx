/**
 * DshControlCard — dsh 认知大脑控制面板 (v0.6.3 内置化)
 *
 * 一键启停 (受管子进程) + 端点/启动命令/自启配置持久化 + 状态自动刷新。
 * 数据源: GET /api/dsh/control/status · POST start|stop|restart · PUT config
 * gate 关闭时 /api/dsh/control/* 404 → 面板如实呈现降级说明。
 */
import { useCallback, useEffect, useRef, useState } from 'react';

interface ProcessSnapshot {
  running: boolean;
  pid: number | null;
  uptime_s: number | null;
  restarts: number;
  last_error: string | null;
  log_tail?: string[];
}

interface DshStatus {
  status: 'connected' | 'starting' | 'stopped' | 'not_configured';
  endpoint: string;
  command_raw: string;
  autostart: boolean;
  configured: boolean;
  endpoint_reachable: boolean;
  process: ProcessSnapshot;
}

const STATUS_LABEL: Record<DshStatus['status'], string> = {
  connected: '已连接',
  starting: '运行中 (endpoint 未响应)',
  stopped: '已停止',
  not_configured: '未配置启动命令',
};

const STATUS_COLOR: Record<DshStatus['status'], string> = {
  connected: 'var(--color-success)',
  starting: 'var(--color-warning)',
  stopped: 'var(--text-disabled)',
  not_configured: 'var(--color-warning)',
};

export function DshControlCard() {
  const [status, setStatus] = useState<DshStatus | null>(null);
  const [gateOff, setGateOff] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [opBusy, setOpBusy] = useState<'start' | 'stop' | 'restart' | 'save' | null>(null);
  const [opMsg, setOpMsg] = useState<{ kind: 'ok' | 'err'; text: string } | null>(null);

  // 表单 (加载后初始化)
  const [endpoint, setEndpoint] = useState('');
  const [command, setCommand] = useState('');
  const [autostart, setAutostart] = useState(false);
  const dirtyRef = useRef(false);

  const refresh = useCallback(async () => {
    try {
      const r = await fetch('/api/dsh/control/status');
      if (r.status === 404) {
        setGateOff(true);
        return;
      }
      if (!r.ok) {
        setError(`状态加载失败 (${r.status})`);
        return;
      }
      const d: DshStatus = await r.json();
      setGateOff(false);
      setError(null);
      setStatus(d);
      if (!dirtyRef.current) {
        setEndpoint(d.endpoint ?? '');
        setCommand(d.command_raw ?? '');
        setAutostart(d.autostart ?? false);
      }
    } catch {
      setError('状态加载失败: 网络或后端不可达');
    }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);
  // 10s 自动刷新 (轮询同时驱动后端 poll → 意外退出自动复活)
  useEffect(() => {
    const timer = window.setInterval(refresh, 10_000);
    return () => window.clearInterval(timer);
  }, [refresh]);

  const doOp = async (op: 'start' | 'stop' | 'restart') => {
    setOpBusy(op);
    setOpMsg(null);
    try {
      const r = await fetch(`/api/dsh/control/${op}`, { method: 'POST' });
      const d = await r.json().catch(() => ({}));
      if (r.status === 409) {
        setOpMsg({ kind: 'err', text: d.error ?? '操作被拒绝' });
      } else if (!r.ok) {
        setOpMsg({ kind: 'err', text: `操作失败 (${r.status})` });
      } else {
        setOpMsg({ kind: 'ok', text: { start: '已启动', stop: '已停止', restart: '已重启' }[op] });
      }
    } catch {
      setOpMsg({ kind: 'err', text: '操作失败: 网络或后端不可达' });
    } finally {
      setOpBusy(null);
      await refresh();
    }
  };

  const saveConfig = async () => {
    setOpBusy('save');
    setOpMsg(null);
    try {
      const r = await fetch('/api/dsh/control/config', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ endpoint, command, autostart }),
      });
      if (!r.ok) {
        setOpMsg({ kind: 'err', text: `保存失败 (${r.status})` });
        return;
      }
      setOpMsg({ kind: 'ok', text: '配置已保存' });
      dirtyRef.current = false;
    } catch {
      setOpMsg({ kind: 'err', text: '保存失败: 网络或后端不可达' });
    } finally {
      setOpBusy(null);
      await refresh();
    }
  };

  if (gateOff) {
    return (
      <div className="p-3 rounded-[var(--radius-sm)]" style={{ border: '1px solid var(--border-color)' }}>
        <h3 className="text-xs font-mono font-medium mb-1.5" style={{ color: 'var(--text-primary)' }}>dsh 认知大脑</h3>
        <p className="text-[10px] font-mono" style={{ color: 'var(--text-muted)' }}>
          dsh 扩展未启用 (feature_gates.toml dsh=false, /api/dsh/* 返回 404)。
          业务自动降级 LLM 直连。
        </p>
      </div>
    );
  }

  const proc = status?.process;

  return (
    <div className="p-3 rounded-[var(--radius-sm)]" style={{ border: '1px solid var(--border-color)' }}>
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-xs font-mono font-medium" style={{ color: 'var(--text-primary)' }}>
          dsh 认知大脑
          {status && (
            <span className="ml-2 inline-flex items-center gap-1 text-[10px]">
              <span className="w-2 h-2 rounded-full inline-block" style={{ backgroundColor: STATUS_COLOR[status.status] }} />
              <span style={{ color: 'var(--text-secondary)' }}>{STATUS_LABEL[status.status]}</span>
              {status.endpoint_reachable && status.status === 'connected' && (
                <span style={{ color: 'var(--color-success)' }}> · endpoint OK</span>
              )}
            </span>
          )}
        </h3>
        <div className="flex items-center gap-1">
          <button onClick={() => doOp('start')} disabled={opBusy !== null}
            className="btn-secondary text-[10px] px-2 py-0.5">
            {opBusy === 'start' ? '启动中...' : '启动'}
          </button>
          <button onClick={() => doOp('stop')} disabled={opBusy !== null || !proc?.running}
            className="btn-secondary text-[10px] px-2 py-0.5">
            {opBusy === 'stop' ? '停止中...' : '停止'}
          </button>
          <button onClick={() => doOp('restart')} disabled={opBusy !== null}
            className="btn-secondary text-[10px] px-2 py-0.5">
            {opBusy === 'restart' ? '重启中...' : '重启'}
          </button>
        </div>
      </div>

      {error && <p className="text-[10px] font-mono mb-1.5" style={{ color: 'var(--color-error)' }}>{error}</p>}
      {opMsg && (
        <p className="text-[10px] font-mono mb-1.5"
          style={{ color: opMsg.kind === 'ok' ? 'var(--color-success)' : 'var(--color-error)' }}>
          {opMsg.text}
        </p>
      )}

      {/* 进程详情 */}
      {proc?.running && (
        <div className="text-[10px] font-mono mb-2" style={{ color: 'var(--text-muted)' }}>
          pid {proc.pid} · 运行 {proc.uptime_s != null ? `${Math.round(proc.uptime_s)}s` : '–'}
          {proc.restarts > 0 && <span style={{ color: 'var(--color-warning)' }}> · 自动重启 {proc.restarts} 次</span>}
        </div>
      )}
      {proc?.last_error && (
        <p className="text-[10px] font-mono mb-2" style={{ color: 'var(--color-error)' }}>{proc.last_error}</p>
      )}

      {/* 配置表单 */}
      <div className="space-y-1.5">
        <input
          value={endpoint}
          onChange={e => { dirtyRef.current = true; setEndpoint(e.target.value); }}
          placeholder="endpoint (如 http://localhost:3210)"
          className="w-full px-2 py-1 text-[11px] font-mono rounded"
          style={{ backgroundColor: 'var(--bg-hover)', border: '1px solid var(--border-color)', color: 'var(--text-primary)' }}
        />
        <input
          value={command}
          onChange={e => { dirtyRef.current = true; setCommand(e.target.value); }}
          placeholder="启动命令 (如 node /path/to/dsh/dev.mjs)"
          className="w-full px-2 py-1 text-[11px] font-mono rounded"
          style={{ backgroundColor: 'var(--bg-hover)', border: '1px solid var(--border-color)', color: 'var(--text-primary)' }}
        />
        <div className="flex items-center justify-between">
          <label className="flex items-center gap-1.5 text-[10px] font-mono" style={{ color: 'var(--text-secondary)' }}>
            <input type="checkbox" checked={autostart}
              onChange={e => { dirtyRef.current = true; setAutostart(e.target.checked); }} />
            app 启动时自动拉起
          </label>
          <button onClick={saveConfig} disabled={opBusy !== null} className="btn-secondary text-[10px] px-2 py-0.5">
            {opBusy === 'save' ? '保存中...' : '保存配置'}
          </button>
        </div>
      </div>
      <p className="text-[9px] mt-1.5" style={{ color: 'var(--text-muted)', opacity: 0.7 }}>
        dsh 不可达时深度分析自动降级 LLM 直连; 意外退出自动复活 (上限 3 次)
      </p>
    </div>
  );
}
