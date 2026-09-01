/**
 * DshControlCard — dsh 认知大脑控制面板 (v0.6.3 内置化)
 *
 * 一键启停 (受管子进程) + 端点/启动命令/自启配置持久化 + 状态自动刷新。
 * 数据源: GET /api/dsh/control/status · POST start|stop|restart · PUT config
 * v0.7 Batch ⑨ B9-1: 接入 i18n (dsh.* namespace)
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { useI18n } from '../../../contexts/I18nContext';

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

const STATUS_I18N: Record<DshStatus['status'], string> = {
  connected: 'dsh.connected',
  starting: 'dsh.running_no_endpoint',
  stopped: 'dsh.stopped',
  not_configured: 'dsh.not_configured',
};

const STATUS_COLOR: Record<DshStatus['status'], string> = {
  connected: 'var(--color-success)',
  starting: 'var(--color-warning)',
  stopped: 'var(--text-disabled)',
  not_configured: 'var(--color-warning)',
};

export function DshControlCard() {
  const { t } = useI18n();
  const [status, setStatus] = useState<DshStatus | null>(null);
  const [gateOff, setGateOff] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [opBusy, setOpBusy] = useState<'start' | 'stop' | 'restart' | 'save' | null>(null);
  const [opMsg, setOpMsg] = useState<{ kind: 'ok' | 'err'; text: string } | null>(null);

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
        setError(`${t('dsh.status_load_failed')} (${r.status})`);
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
      setError(t('dsh.status_load_failed_network'));
    }
  }, [t]);

  useEffect(() => { refresh(); }, [refresh]);
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
        setOpMsg({ kind: 'err', text: d.error ?? t('dsh.op_rejected') });
      } else if (!r.ok) {
        setOpMsg({ kind: 'err', text: `${t('dsh.op_failed')} (${r.status})` });
      } else {
        const okI18n: Record<typeof op, string> = {
          start: 'dsh.started',
          stop: 'dsh.stopped_action',
          restart: 'dsh.restarted',
        };
        setOpMsg({ kind: 'ok', text: t(okI18n[op]) });
      }
    } catch {
      setOpMsg({ kind: 'err', text: t('dsh.op_failed_network') });
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
        setOpMsg({ kind: 'err', text: `${t('dsh.save_failed')} (${r.status})` });
        return;
      }
      setOpMsg({ kind: 'ok', text: t('dsh.saved') });
      dirtyRef.current = false;
    } catch {
      setOpMsg({ kind: 'err', text: t('dsh.save_failed_network') });
    } finally {
      setOpBusy(null);
      await refresh();
    }
  };

  if (gateOff) {
    return (
      <div className="p-3 rounded-[var(--radius-sm)]" style={{ border: '1px solid var(--border-color)' }}>
        <h3 className="text-xs font-mono font-medium mb-1.5" style={{ color: 'var(--text-primary)' }}>{t('dsh.cognitive_brain')}</h3>
        <p className="text-[10px] font-mono" style={{ color: 'var(--text-muted)' }}>
          {t('dsh.disabled_hint')}
          {t('dsh.fallback_llm')}
        </p>
      </div>
    );
  }

  const proc = status?.process;

  return (
    <div className="p-3 rounded-[var(--radius-sm)]" style={{ border: '1px solid var(--border-color)' }}>
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-xs font-mono font-medium" style={{ color: 'var(--text-primary)' }}>
          {t('dsh.cognitive_brain')}
          {status && (
            <span className="ml-2 inline-flex items-center gap-1 text-[10px]">
              <span className="w-2 h-2 rounded-full inline-block" style={{ backgroundColor: STATUS_COLOR[status.status] }} />
              <span style={{ color: 'var(--text-secondary)' }}>{t(STATUS_I18N[status.status])}</span>
              {status.endpoint_reachable && status.status === 'connected' && (
                <span style={{ color: 'var(--color-success)' }}> · endpoint OK</span>
              )}
            </span>
          )}
        </h3>
        <div className="flex items-center gap-1">
          <button onClick={() => doOp('start')} disabled={opBusy !== null}
            className="btn-secondary text-[10px] px-2 py-0.5"
            aria-label={t('dsh.start')}>
            {opBusy === 'start' ? t('dsh.starting') : t('dsh.start')}
          </button>
          <button onClick={() => doOp('stop')} disabled={opBusy !== null || !proc?.running}
            className="btn-secondary text-[10px] px-2 py-0.5"
            aria-label={t('dsh.stop')}>
            {opBusy === 'stop' ? t('dsh.stopping') : t('dsh.stop')}
          </button>
          <button onClick={() => doOp('restart')} disabled={opBusy !== null}
            className="btn-secondary text-[10px] px-2 py-0.5"
            aria-label={t('dsh.restart')}>
            {opBusy === 'restart' ? t('dsh.restarting') : t('dsh.restart')}
          </button>
        </div>
      </div>

      {error && <p className="text-[10px] font-mono mb-1.5" style={{ color: 'var(--color-error)' }}>{error}</p>}
      {opMsg && (
        <p className="text-[10px] font-mono mb-1.5"
          style={{ color: opMsg.kind === 'ok' ? 'var(--color-success)' : 'var(--color-error)' }}
          role="status" aria-live="polite">
          {opMsg.text}
        </p>
      )}

      {proc?.running && (
        <div className="text-[10px] font-mono mb-2" style={{ color: 'var(--text-muted)' }}>
          {t('dsh.pid_info', {
            pid: proc.pid ?? '–',
            uptime: proc.uptime_s != null ? `${Math.round(proc.uptime_s)}${t('common.seconds')}` : t('dsh.uptime_unknown'),
          })}
          {proc.restarts > 0 && (
            <span style={{ color: 'var(--color-warning)' }}>
              {t('dsh.restart_count', { n: proc.restarts })}
            </span>
          )}
        </div>
      )}
      {proc?.last_error && (
        <p className="text-[10px] font-mono mb-2" style={{ color: 'var(--color-error)' }}>{proc.last_error}</p>
      )}

      <div className="space-y-1.5">
        <input
          value={endpoint}
          onChange={e => { dirtyRef.current = true; setEndpoint(e.target.value); }}
          placeholder={t('dsh.endpoint_placeholder')}
          className="w-full px-2 py-1 text-[11px] font-mono rounded"
          style={{ backgroundColor: 'var(--bg-hover)', border: '1px solid var(--border-color)', color: 'var(--text-primary)' }}
        />
        <input
          value={command}
          onChange={e => { dirtyRef.current = true; setCommand(e.target.value); }}
          placeholder={t('dsh.cmd_placeholder')}
          className="w-full px-2 py-1 text-[11px] font-mono rounded"
          style={{ backgroundColor: 'var(--bg-hover)', border: '1px solid var(--border-color)', color: 'var(--text-primary)' }}
        />
        <div className="flex items-center justify-between">
          <label className="flex items-center gap-1.5 text-[10px] font-mono" style={{ color: 'var(--text-secondary)' }}>
            <input type="checkbox" checked={autostart}
              onChange={e => { dirtyRef.current = true; setAutostart(e.target.checked); }} />
            {t('dsh.autostart')}
          </label>
          <button onClick={saveConfig} disabled={opBusy !== null} className="btn-secondary text-[10px] px-2 py-0.5">
            {opBusy === 'save' ? t('dsh.saving') : t('dsh.save_config')}
          </button>
        </div>
      </div>
      <p className="text-[9px] mt-1.5" style={{ color: 'var(--text-muted)', opacity: 0.7 }}>
        {t('dsh.fallback_hint')}
      </p>
    </div>
  );
}
