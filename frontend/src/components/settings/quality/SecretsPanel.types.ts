/**
 * quality/SecretsPanel.types — SecretsPanel 内部状态类型 (拆分自 SecretsPanel.tsx)
 *
 * 仅承载跨文件共用的纯类型, 无运行时导出。
 */

/** 操作结果消息条 (ok / error) */
export type SecretsPanelMsg = { type: 'ok' | 'error'; text: string };

/** 主密钥 prompt modal 目标 (unlock / reveal 共用) */
export type SecretsPanelKeyPrompt = { target: 'unlock' | 'reveal'; secretId?: number };

/** 新增/编辑密钥表单状态 */
export type SecretsPanelUpsertState = {
  id?: number; provider: string; name: string; model: string; base_url: string; api_key: string; master_key: string;
};