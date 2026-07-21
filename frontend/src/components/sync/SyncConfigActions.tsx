/**
 * SyncConfigActions — 配置表单底部 actions (测试/保存/删除按钮 + 提示消息)。
 *
 * Phase 6 拆分: 从 SyncConfigForm 抽出, 减少后者体积, 保持单文件 ≤ 10KB。
 */
import React from 'react';
import { Icon } from '../Icon';

interface SyncConfigActionsProps {
  testing: boolean;
  saving: boolean;
  configured: boolean;
  canTest: boolean;
  onTest: () => void;
  onSave: () => void;
  onDelete: () => void;
  saveOk: string | null;
  actionError: string | null;
  testMsg: { ok: boolean; message: string } | null;
}

export function SyncConfigActions({
  testing,
  saving,
  configured,
  canTest,
  onTest,
  onSave,
  onDelete,
  saveOk,
  actionError,
  testMsg,
}: SyncConfigActionsProps) {
  return (
    <>
      {saveOk && (
        <div
          className="mt-3 px-3 py-2 rounded text-[11px]"
          style={{
            background: 'color-mix(in srgb, var(--color-success) 10%, transparent)',
            color: 'var(--color-success)',
            border: '1px solid color-mix(in srgb, var(--color-success) 30%, transparent)',
          }}
        >
          {saveOk}
        </div>
      )}

      {actionError && (
        <div
          className="mt-3 px-3 py-2 rounded text-[11px]"
          style={{
            background: 'color-mix(in srgb, var(--color-error) 10%, transparent)',
            color: 'var(--color-error)',
            border: '1px solid color-mix(in srgb, var(--color-error) 30%, transparent)',
          }}
        >
          ✗ {actionError}
        </div>
      )}

      <div className="flex gap-2 mt-3 flex-wrap">
        <button
          onClick={onTest}
          disabled={testing || !canTest}
          className="btn-ghost px-3 py-1.5 text-xs"
          style={{ opacity: testing ? 0.6 : 1 }}
        >
          <Icon size={12}>
            <polyline points="9 11 12 14 22 4" />
            <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11" />
          </Icon>
          {testing ? '测试中…' : '测试连接'}
        </button>
        <button
          onClick={onSave}
          disabled={saving}
          className="btn-ghost px-3 py-1.5 text-xs"
          style={{ opacity: saving ? 0.6 : 1 }}
        >
          <Icon size={12}>
            <path d="M19 21H5a2 2 0 0 0-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z" />
            <polyline points="17 21 17 13 7 13 7 21" />
            <polyline points="7 3 7 8 15 8" />
          </Icon>
          {saving ? '保存中…' : '保存配置'}
        </button>
        {configured && (
          <button
            onClick={onDelete}
            className="btn-ghost px-3 py-1.5 text-xs"
            style={{ color: 'var(--color-error)' }}
          >
            <Icon size={12}>
              <polyline points="3 6 5 6 21 6" />
              <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
            </Icon>
            删除配置
          </button>
        )}
      </div>

      {testMsg && (
        <div
          className="mt-3 px-3 py-2 rounded text-[11px]"
          style={{
            background: testMsg.ok
              ? 'color-mix(in srgb, var(--color-success) 10%, transparent)'
              : 'color-mix(in srgb, var(--color-error) 10%, transparent)',
            color: testMsg.ok ? 'var(--color-success)' : 'var(--color-error)',
            border: `1px solid ${
              testMsg.ok
                ? 'color-mix(in srgb, var(--color-success) 30%, transparent)'
                : 'color-mix(in srgb, var(--color-error) 30%, transparent)'
            }`,
          }}
        >
          {testMsg.ok ? '✓' : '✗'} {testMsg.message}
        </div>
      )}
    </>
  );
}
