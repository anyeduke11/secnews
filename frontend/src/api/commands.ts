/**
 * 命令栏客户端 (v0.8.6 P1-4, M4) — POST 执行 + GET 历史。
 * 后端恒 HTTP 200, intent/outcome 字段区分 (unknown/unsupported 不猜)。
 */
import { getJSON, postJSON } from '../lib/api';

export type CommandIntent = 'query' | 'create_case' | 'report' | 'execute' | 'unknown';
export type CommandOutcome = 'done' | 'unsupported' | 'unrecognized' | 'error';

export interface CommandSignalHit {
  signal_id: string;
  summary: string;
  url: string;
  title: string;
  occurred_at: string;
  confidence: string;
}

export interface CommandResult {
  command_id: string;
  intent: CommandIntent;
  outcome: CommandOutcome;
  message: string;
  results?: CommandSignalHit[];
  result_count?: number;
  window_days?: number;
  proposal_id?: string;
  options?: string[];
}

export interface CommandLogItem {
  id: string;
  input_text: string;
  intent: CommandIntent | null;
  action_ref: string | null;
  run_id: string | null;
  outcome: CommandOutcome | null;
  created_at: string;
}

/** POST /api/commands — 执行一条命令 (本地规则意图路由)。 */
export function runCommand(text: string): Promise<CommandResult> {
  return postJSON<CommandResult>('/api/commands', { text });
}

/** GET /api/commands — 命令 run record 列表。 */
export function listCommands(limit = 20): Promise<{ items: CommandLogItem[]; total: number }> {
  return getJSON(`/api/commands?limit=${limit}`);
}
