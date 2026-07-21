/**
 * SyncBundleConfig — 类型与共享定义 re-export (向后兼容)。
 *
 * Phase 1B 修复: 避免循环 import, 此文件从 ./types 统一 re-export。
 * 实际渲染拆为 SyncConfigForm + SyncOperations。
 */
export type {
  BundleConfigForm,
  EffectiveRemoteInfo,
  LastSyncResult,
  BundlePreview,
  SyncDirection,
  SyncPhase,
  SyncFrequency,
} from './types';
