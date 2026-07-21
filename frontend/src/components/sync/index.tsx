/**
 * SyncPage — 跨端配置同步页 (主入口 / 薄壳)。
 *
 * Phase 1B: 拆自原 SyncPage.tsx (33KB/862行 → 7 文件, 每文件 ≤ 10KB)。
 * 本文件仅做组合, 状态与业务逻辑委托 useSyncPage hook, 渲染委托 4 个子组件。
 *
 * 子组件树:
 *   SyncHeader
 *   SyncStatusPanel
 *   SyncConfigForm
 *   SyncOperations
 *   SyncHistory
 *
 * API 保持向后兼容: export function SyncPage({ onBack })
 */
import React from 'react';
import { useGoHome } from '../../hooks/useGoHome';
import { SyncHeader } from './SyncHeader';
import { SyncStatusPanel } from './SyncStatusPanel';
import { SyncConfigForm } from './SyncConfigForm';
import { SyncOperations } from './SyncOperations';
import { SyncHistory } from './SyncHistory';
import { useSyncPage } from './useSyncPage';

interface SyncPageProps {
  /** 兼容旧 onBack 模式, 新代码优先 useGoHome hook */
  onBack?: () => void;
}

export function SyncPage({ onBack }: SyncPageProps) {
  const goHomeHook = useGoHome();
  const goHome = onBack ?? goHomeHook;

  const c = useSyncPage();

  return (
    <div className="sync-page">
      <SyncHeader configured={c.configured} onBack={goHome} />

      <SyncStatusPanel status={c.statusForPanel} />

      <SyncConfigForm
        form={c.form}
        setForm={c.setForm}
        configured={c.configured}
        effective={c.effective}
        testing={c.testing}
        saving={c.saving}
        testMsg={c.testMsg}
        saveOk={c.saveOk}
        actionError={c.actionError}
        showMasterKey={c.showMasterKey}
        setShowMasterKey={c.setShowMasterKey}
        masterKeyFromCache={c.masterKeyFromCache}
        setMasterKeyFromCache={c.setMasterKeyFromCache}
        onTest={c.handleTest}
        onSave={c.handleSave}
        onDelete={c.handleDelete}
      />

      <SyncOperations
        form={c.form}
        configured={c.configured}
        syncing={c.syncing}
        masterKeyForSync={c.masterKeyForSync}
        setMasterKeyForSync={c.setMasterKeyForSync}
        lastResult={c.lastResult}
        preview={c.preview}
        loading={c.loading}
        onSync={c.handleSync}
        onToggleAuto={c.handleToggleAuto}
        onFetchPreview={c.fetchPreview}
      />

      <SyncHistory
        configured={c.configured}
        history={c.history}
        conflicts={c.conflicts}
        onResolveConflict={c.handleResolveConflict}
      />

      {c.error && (
        <div
          className="mt-3 px-3 py-2 rounded text-[11px]"
          style={{
            background: 'color-mix(in srgb, var(--color-error) 10%, transparent)',
            color: 'var(--color-error)',
          }}
        >
          {c.error}
        </div>
      )}
    </div>
  );
}
