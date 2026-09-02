/**
 * DshControlCard — dsh 认知大脑控制面板 (v0.6.3 内置化, Sentinel V2 token)
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

const STATUS_TONE: Record<DshStatus['status'], 'ok' | 'warn' | 'mute' | 'bad'> = {
  connected: 'ok',
  starting: 'warn',
  stopped: 'mute',
  not_configured: 'warn',
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
      <div
        style={{
          padding: 'var(--sn-cell-pad)',
          borderRadius: 'var(--sn-radius-md)',
          border: '1px solid var(--sn-line)',
          backgroundColor: 'var(--sn-bg-1)',
        }}
      >
        <h3 style={{
          fontFamily: 'var(--sn-mono)',
          fontSize: 'var(--sn-fs-h3)',
          fontWeight: 'var(--sn-fw-medium)',
          color: 'var(--sn-ink)',
          margin: '0 0 6px 0',
        }}>
          {t('dsh.cognitive_brain')}
        </h3>
        <p style={{
          fontFamily: 'var(--sn-mono)',
          fontSize: 'var(--sn-fs-mute)',
          color: 'var(--sn-ink-3)',
          margin: 0,
        }}>
          {t('dsh.disabled_hint')}
          {t('dsh.fallback_llm')}
        </p>
      </div>
    );
  }

  const proc = status?.process;
  const tone = status ? STATUS_TONE[status.status] : 'mute';

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
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <h3 style={{
          fontFamily: 'var(--sn-mono)',
          fontSize: 'var(--sn-fs-h3)',
          fontWeight: 'var(--sn-fw-medium)',
          color: 'var(--sn-ink)',
          margin: 0,
          display: 'flex',
          alignItems: 'center',
          gap: 12,
        }}>
          {t('dsh.cognitive_brain')}
          {status && (
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 'var(--sn-fs-mute)' }}>
              <span className={`st-chip ${tone}`}>
                <i /> {t(STATUS_I18N[status.status])}
              </span>
              {status.endpoint_reachable && status.status === 'connected' && (
                <span style={{ color: 'var(--sn-mint)', fontFamily: 'var(--sn-mono)' }}>· endpoint OK</span>
              )}
            </span>
          )}
        </h3>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <button
            className="st-btn"
            onClick={() => doOp('start')}
            disabled={opBusy !== null}
            aria-label={t('dsh.start')}
          >
            {opBusy === 'start' ? t('dsh.starting') : t('dsh.start')}
          </button>
          <button
            className="st-btn"
            onClick={() => doOp('stop')}
            disabled={opBusy !== null || !proc?.running}
            aria-label={t('dsh.stop')}
          >
            {opBusy === 'stop' ? t('dsh.stopping') : t('dsh.stop')}
          </button>
          <button
            className="st-btn"
            onClick={() => doOp('restart')}
            disabled={opBusy !== null}
            aria-label={t('dsh.restart')}
          >
            {opBusy === 'restart' ? t('dsh.restarting') : t('dsh.restart')}
          </button>
        </div>
      </div>

      {error && (
        <p style={{ fontFamily: 'var(--sn-mono)', fontSize: 'var(--sn-fs-mute)', color: 'var(--sn-red)', margin: 0 }}>
          {error}
        </p>
      )}
      {opMsg && (
        <p
          role="status" aria-live="polite"
          style={{
            fontFamily: 'var(--sn-mono)',
            fontSize: 'var(--sn-fs-mute)',
            color: opMsg.kind === 'ok' ? 'var(--sn-mint)' : 'var(--sn-red)',
            margin: 0,
          }}
        >
          {opMsg.text}
        </p>
      )}

      {proc?.running && (
        <div style={{ fontFamily: 'var(--sn-mono)', fontSize: 'var(--sn-fs-mute)', color: 'var(--sn-ink-3)' }}>
          {t('dsh.pid_info', {
            pid: proc.pid ?? '–',
            uptime: proc.uptime_s != null ? `${Math.round(proc.uptime_s)}${t('common.seconds')}` : t('dsh.uptime_unknown'),
          })}
          {proc.restarts > 0 && (
            <span style={{ color: 'var(--sn-amber)', marginLeft: 8 }}>
              {t('dsh.restart_count', { n: proc.restarts })}
            </span>
          )}
        </div>
      )}
      {proc?.last_error && (
        <p style={{ fontFamily: 'var(--sn-mono)', fontSize: 'var(--sn-fs-mute)', color: 'var(--sn-red)', margin: 0 }}>
          {proc.last_error}
        </p>
      )}

      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        <input
          className="st-input"
          value={endpoint}
          onChange={e => { dirtyRef.current = true; setEndpoint(e.target.value); }}
          placeholder={t('dsh.endpoint_placeholder')}
          style={{ fontFamily: 'var(--sn-mono)' }}
        />
        <input
          className="st-input"
          value={command}
          onChange={e => { dirtyRef.current = true; setCommand(e.target.value); }}
          placeholder={t('dsh.cmd_placeholder')}
          style={{ fontFamily: 'var(--sn-mono)' }}
        />
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <label style={{
            display: 'flex', alignItems: 'center', gap: 6,
            fontSize: 'var(--sn-fs-mute)', fontFamily: 'var(--sn-mono)',
            color: 'var(--sn-ink-2)',
          }}>
            <input
              type="checkbox"
              checked={autostart}
              onChange={e => { dirtyRef.current = true; setAutostart(e.target.checked); }}
              style={{ accentColor: 'var(--sn-mint)' }}
            />
            {t('dsh.autostart')}
          </label>
          <button
            className="st-btn primary"
            onClick={saveConfig}
            disabled={opBusy !== null}
          >
            {opBusy === 'save' ? t('dsh.saving') : t('dsh.save_config')}
          </button>
        </div>
      </div>
      <p style={{
        fontFamily: 'var(--sn-mono)',
        fontSize: 'var(--sn-fs-mute)',
        color: 'var(--sn-ink-3)',
        margin: 0,
      }}>
        {t('dsh.fallback_hint')}
      </p>
    </div>
  );
}