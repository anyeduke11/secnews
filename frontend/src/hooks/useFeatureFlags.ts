/**
 * useFeatureFlags — 前端 feature flag hook
 *
 * 从后端 /api/settings/features 拉取扩展状态（feature_gates.toml 派生的
 * 运行时视图），缓存 5 分钟到 localStorage；拉取失败回退 DEFAULT_FLAGS。
 * 模块级共享：多个消费者（App/Header/LayerHeader/SettingsPage）只发一次请求。
 *
 * 端点为跨域共享 → 收敛到 api/shared.ts (getFeatureFlagsRaw)。
 */
import { useEffect, useState } from 'react';
import { getFeatureFlagsRaw } from '../api/shared';

export interface FeatureFlags {
  mcp: boolean;
  techStack: boolean;
  securityGraph: boolean;
  /** v0.6: SecNews 安全看板 */
  secnews: boolean;
  /** v0.6: dsh 桥接层 (关闭时 /api/dsh/* 404, 界面需如实呈现) */
  dsh: boolean;
}

export const DEFAULT_FLAGS: FeatureFlags = {
  mcp: false,
  techStack: false,
  securityGraph: false,
  secnews: true,
  dsh: false,
};

const CACHE_KEY = 'hotspot-feature-flags';
const CACHE_TTL_MS = 5 * 60 * 1000;

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
    const data = await getFeatureFlagsRaw();
    const flags: FeatureFlags = {
      mcp: !!data.mcp,
      techStack: !!((data.techStack as boolean | undefined) ?? data.tech_stack),
      securityGraph: !!((data.securityGraph as boolean | undefined) ?? data.security_graph),
      secnews: !!((data.secnews as boolean | undefined) ?? true),
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
