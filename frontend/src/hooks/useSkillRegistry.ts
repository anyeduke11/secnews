/**
 * useSkillRegistry / useSkillToggle — v0.8 Phase A 技能注册表 hooks
 *
 * 数据源: /api/skill-registry (A3 交付, 详见 backend/api/skill_registry_api.py)。
 * 统一走 lib/api 的 apiFetch/postJSON (仓库 P0 约定, 禁裸 fetch):
 *   - apiFetch 已把 {detail:{message,...}} 解析为 Error.message, hook 只做兜底文案
 *   - POST enable/disable 成功后由调用方决定是否 refresh (hook 不自动拉列表)
 */
import { useCallback, useEffect, useState } from 'react';
import { apiFetch, postJSON } from '../lib/api';
import { SkillDetail, SkillRun, SkillSummary } from '../types/skill';

export interface UseSkillRegistryReturn {
  skills: SkillSummary[];
  loading: boolean;
  error: string | null;
  /** 触发重新拉取 (category 参数变化也会自动重拉) */
  refresh: () => void;
}

/** GET /api/skill-registry?category=&enabled_only= — 列表 (保持注册顺序) */
export function useSkillRegistry(category?: string): UseSkillRegistryReturn {
  const [skills, setSkills] = useState<SkillSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadSeq, setReloadSeq] = useState(0);

  const refresh = useCallback(() => setReloadSeq(s => s + 1), []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    const path = category
      ? `/api/skill-registry?category=${encodeURIComponent(category)}`
      : '/api/skill-registry';
    apiFetch<SkillSummary[]>(path, { skipLoading: true })
      .then(data => {
        if (cancelled) return;
        setSkills(Array.isArray(data) ? data : []);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        // apiFetch 已提取 detail.message; 仅在 message 为空时兜底
        const msg = err instanceof Error && err.message ? err.message : '技能清单加载失败';
        setError(msg);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [category, reloadSeq]);

  return { skills, loading, error, refresh };
}

export interface UseSkillDetailReturn {
  detail: SkillDetail | null;
  loading: boolean;
  error: string | null;
  refresh: () => void;
}

/** GET /api/skill-registry/{id} — 详情 (B6 SkillDetail 页数据源) */
export function useSkillDetail(skillId: string): UseSkillDetailReturn {
  const [detail, setDetail] = useState<SkillDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadSeq, setReloadSeq] = useState(0);

  const refresh = useCallback(() => setReloadSeq(s => s + 1), []);

  useEffect(() => {
    if (!skillId) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    apiFetch<SkillDetail>(`/api/skill-registry/${encodeURIComponent(skillId)}`, { skipLoading: true })
      .then(data => {
        if (cancelled) return;
        setDetail(data);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const msg = err instanceof Error && err.message ? err.message : '技能详情加载失败';
        setError(msg);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [skillId, reloadSeq]);

  return { detail, loading, error, refresh };
}

export interface UseSkillRunsReturn {
  runs: SkillRun[];
  loading: boolean;
  error: string | null;
  refresh: () => void;
}

/** GET /api/skill-registry/{id}/runs?limit=20 — 运行历史 (B6 RunHistory 数据源) */
export function useSkillRuns(skillId: string): UseSkillRunsReturn {
  const [runs, setRuns] = useState<SkillRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadSeq, setReloadSeq] = useState(0);

  const refresh = useCallback(() => setReloadSeq(s => s + 1), []);

  useEffect(() => {
    if (!skillId) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    apiFetch<SkillRun[]>(`/api/skill-registry/${encodeURIComponent(skillId)}/runs?limit=20`, {
      skipLoading: true,
    })
      .then(data => {
        if (cancelled) return;
        setRuns(Array.isArray(data) ? data : []);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const msg = err instanceof Error && err.message ? err.message : '运行历史加载失败';
        setError(msg);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [skillId, reloadSeq]);

  return { runs, loading, error, refresh };
}

export interface UseSkillToggleReturn {
  /**
   * POST /api/skill-registry/{id}/enable | disable
   * 成功 resolve (调用方 refresh 列表), 失败 reject (Error.message 已含 detail.message)。
   */
  toggle: (skillId: string, next: boolean) => Promise<void>;
  /** 任一启停请求在途时为 true (期间开关禁用, 单用户工作站串行即可) */
  busy: boolean;
}

/** 技能启停 — POST enable/disable, 二次确认由 UI 层 (SkillToggle) 负责 */
export function useSkillToggle(): UseSkillToggleReturn {
  const [busy, setBusy] = useState(false);

  const toggle = useCallback(async (skillId: string, next: boolean) => {
    setBusy(true);
    try {
      await postJSON<{ enabled: boolean }>(
        `/api/skill-registry/${encodeURIComponent(skillId)}/${next ? 'enable' : 'disable'}`,
        {}
      );
    } finally {
      setBusy(false);
    }
  }, []);

  return { toggle, busy };
}
