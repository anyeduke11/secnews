/**
 * DshControlCard — dsh 认知大脑控制面板 (v0.6.3 内置化, Sentinel V2 token)
 *
 * 一键启停 (受管子进程) + 端点/启动命令/自启配置持久化 + 状态自动刷新。
 * 数据源: GET /api/dsh/control/status · POST start|stop|restart · PUT config
 * v0.7 Batch ⑨ B9-1: 接入 i18n (dsh.* namespace)
 *
 * 拆分 (前端重构 V1 B6-b, 单文件 ≤300 行): 两个展示区块移至同目录
 * DshControlCardHeader (标题/状态 chip/启停按钮) 与 DshControlCardGateOff (gate 关闭提示卡)。
 * 状态与请求逻辑全部保留在本组件, 区块仅为受控视图 (零行为/DOM 变更)。
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { ApiError } from '../../../lib/api';
import {
  getDshControlStatus,
  postDshControlOp,
  updateDshControlConfig,
} from '../../../api/secnews';
import type { DshStatus } from '../../../api/secnews';
import { useI18n } from '../../../contexts/I18nContext';
import { DshControlCardGateOff } from './DshControlCardGateOff';
import { DshControlCardHeader } from './DshControlCardHeader';

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
      const d = await getDshControlStatus();
      setGateOff(false);
      setError(null);
      setStatus(d);
      if (!dirtyRef.current) {
        setEndpoint(d.endpoint ?? '');
        setCommand(d.command_raw ?? '');
        setAutostart(d.autostart ?? false);
      }
    } catch (e) {
      // 404 = feature gate 关闭 (原 r.status === 404 分支); 其余按网络/后端失败呈现
      if (e instanceof ApiError && e.status === 404) {
        setGateOff(true);
        return;
      }
      setError(e instanceof ApiError
        ? `${t('dsh.status_load_failed')} (${e.status})`
        : t('dsh.status_load_failed_network'));
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
      await postDshControlOp(op);
      const okI18n: Record<typeof op, string> = {
        start: 'dsh.started',
        stop: 'dsh.stopped_action',
        restart: 'dsh.restarted',
      };
      setOpMsg({ kind: 'ok', text: t(okI18n[op]) });
    } catch (e) {
      // 409 冲突: 后端 {error} 信封经 getApiErrorMessage 兜底进 e.message
      if (e instanceof ApiError && e.status === 409) {
        setOpMsg({ kind: 'err', text: e.message || t('dsh.op_rejected') });
      } else if (e instanceof ApiError) {
        setOpMsg({ kind: 'err', text: `${t('dsh.op_failed')} (${e.status})` });
      } else {
        setOpMsg({ kind: 'err', text: t('dsh.op_failed_network') });
      }
    } finally {
      setOpBusy(null);
      await refresh();
    }
  };

  const saveConfig = async () => {
    setOpBusy('save');
    setOpMsg(null);
    try {
      await updateDshControlConfig({ endpoint, command, autostart });
      setOpMsg({ kind: 'ok', text: t('dsh.saved') });
      dirtyRef.current = false;
    } catch (e) {
      setOpMsg({
        kind: 'err',
        text: e instanceof ApiError
          ? `${t('dsh.save_failed')} (${e.status})`
          : t('dsh.save_failed_network'),
      });
    } finally {
      setOpBusy(null);
      await refresh();
    }
  };

  if (gateOff) {
    return <DshControlCardGateOff t={t} />;
  }

  const proc = status?.process;

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
      <DshControlCardHeader
        t={t}
        status={status}
        proc={proc}
        opBusy={opBusy}
        onOp={doOp}
      />

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