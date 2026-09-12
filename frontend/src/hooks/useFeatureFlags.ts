/**
 * useFeatureFlags — 前端 feature flag hook
 *
 * 从后端 /api/settings/features 拉取扩展状态（feature_gates.toml 派生的
 * 运行时视图），缓存 5 分钟到 localStorage；拉取失败回退 DEFAULT_FLAGS。
 * 模块级共享：多个消费者（App/Header/LayerHeader/SettingsPage）只发一次请求。
 *
 * 端点为单一 hook 专用 → 常量化于此, 走 lib/api 统一封装。
 */
import { useEffect, useState } from 'react';
import { getJSON } from '../lib/api';

export interface FeatureFlags {
  codegarden: boolean;
  /** P1.6: M2/M3/M4 (服务网格/资源中枢/联动引擎) 独立 gate */
  codegardenPhase2b: boolean;
  mcp: boolean;
  sync: boolean;
  techStack: boolean;
  securityGraph: boolean;
  /** v0.6: SecNews 安全看板 */
  secnews: boolean;
  /** v0.6: CRM 业绩座舱 (security-cockpit 方案 C) */
  crm: boolean;
  /** v0.6: dsh 桥接层 (关闭时 /api/dsh/* 404, 界面需如实呈现) */
  dsh: boolean;
}

export const DEFAULT_FLAGS: FeatureFlags = {
  codegarden: false,
  codegardenPhase2b: false,
  mcp: false,
  sync: true,
  techStack: false,
  securityGraph: false,
  secnews: true,
  crm: false,
  dsh: false,
};

const CACHE_KEY = 'hotspot-feature-flags';
const CACHE_TTL_MS = 5 * 60 * 1000;
const FEATURES_URL = '/api/settings/features';

interface CachedFlags {
  fetchedAt: number;
  flags: FeatureFlags;
}

let sharedFlags: FeatureFlags | null = null;
let inflight: Promise<FeatureFlags> | null = null;

function readCache(): FeatureFlags | null {
  try {
    const raw = localStorage.getItem(CACHE_KEY);
    if (!raw) return null;
    const cached = JSON.parse(raw) as CachedFlags;
    if (Date.now() - cached.fetchedAt > CACHE_TTL_MS) return null;
    return { ...DEFAULT_FLAGS, ...cached.flags };
  } catch {
    return null;
  }
}

function writeCache(flags: FeatureFlags): void {
  try {
    localStorage.setItem(CACHE_KEY, JSON.stringify({ fetchedAt: Date.now(), flags }));
  } catch {}
}

async function fetchFlags(): Promise<FeatureFlags> {
  try {
    const data = await getJSON<Record<string, unknown>>(FEATURES_URL);
    const flags: FeatureFlags = {
      codegarden: !!data.codegarden,
      codegardenPhase2b: !!((data.codegarden_phase2b as boolean | undefined) ?? data.codegardenPhase2b),
      mcp: !!data.mcp,
      sync: !!data.sync,
      techStack: !!((data.techStack as boolean | undefined) ?? data.tech_stack),
      securityGraph: !!((data.securityGraph as boolean | undefined) ?? data.security_graph),
      secnews: !!((data.secnews as boolean | undefined) ?? true),
      crm: !!data.crm,
      dsh: !!data.dsh,
    };
    writeCache(flags);
    return flags;
  } catch {
    // 非 2xx (apiFetch 抛错) 或网络失败 → 回退默认 flags
    return DEFAULT_FLAGS;
  }
}

export function useFeatureFlags(): FeatureFlags {
  const [flags, setFlags] = useState<FeatureFlags>(() => sharedFlags ?? readCache() ?? DEFAULT_FLAGS);

  useEffect(() => {
    let cancelled = false;
    if (!inflight) {
      inflight = fetchFlags().finally(() => { inflight = null; });
    }
    inflight.then(f => {
      if (!cancelled) {
        sharedFlags = f;
        setFlags(f);
      }
    });
    return () => { cancelled = true; };
  }, []);

  return flags;
}
