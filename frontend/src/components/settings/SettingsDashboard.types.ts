/**
 * settings/SettingsDashboard — 接口类型 / 快速跳转常量。
 *
 * 拆分自 SettingsDashboard.tsx, 仅承载类型与常量, 无运行时逻辑.
 */
import type { SectionKey } from './sections';

export interface Props {
  onJump: (cat: SectionKey) => void;
}

export interface HealthPayload {
  ok?: boolean;
  version?: string;
  status?: string;
  uptime_s?: number;
  db?: {
    ok: boolean;
    latency_ms: number;
    size_mb?: number;
    hotspots_count?: number;
    error?: string;
  };
  scheduler?: {
    ok: boolean;
    jobs?: string[];
    error?: string;
  };
  collectors?: {
    last_run?: string;
    watchdog_recoveries_24h?: number;
  };
  cache?: { hit_rate?: number };
}

export interface SecretsStatus {
  initialized?: boolean;
  unlocked?: boolean;
  source?: 'os_keyring' | 'session' | 'uninitialized';
}

export interface StatsPayload {
  total_hotspots?: number;
  collect_runs_24h?: number;
  success_rate_24h?: number;
  avg_collect_duration_ms?: number;
  last_fallback_at?: string | null;
}

export interface SourcesHealth {
  total?: number;
  healthy?: number;
  warning?: number;
  dead?: number;
}

export const QUICK_JUMPS: Array<{ cat: SectionKey; label: string; key: string; note: string }> = [
  { cat: 'general', label: '通用', key: 'general', note: '主题/模式/能力开关' },
  { cat: 'models', label: '模型配置', key: 'models', note: 'Provider/密钥/场景模型' },
  { cat: 'collection', label: '采集与管线', key: 'collection', note: '信源/质量/KL 队列/门禁' },
  { cat: 'network', label: '网络', key: 'network', note: '代理/连接' },
  { cat: 'connectivity', label: '集成与凭据', key: 'connectivity', note: '同步/MCP/主密钥' },
  { cat: 'ops', label: '运维', key: 'ops', note: '维护/导出/dsh' },
];