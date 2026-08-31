import { useState, useEffect, useCallback, useRef } from 'react';
import { apiFetch } from '../lib/api';
import { DeepReadResponse, DeepReadSection, DeepReadTone } from '../types';

const VALID_TONES: readonly DeepReadTone[] = ['mint', 'amber', 'red'];

/** 防御归一: 后端加了新 tone 或漏了标题时, 前端不该整节消失 */
function normalizeSection(raw: Partial<DeepReadSection> | null | undefined): DeepReadSection | null {
  const key = typeof raw?.key === 'string' ? raw.key : '';
  if (!key) return null;
  return {
    key,
    title: raw?.title || key,
    tone: VALID_TONES.includes(raw?.tone as DeepReadTone) ? (raw!.tone as DeepReadTone) : 'mint',
    body: typeof raw?.body === 'string' ? raw.body : '',
  };
}

export interface UseDeepReadReturn {
  /** 当前深读内容 (无则 null) */
  data: DeepReadResponse | null;
  /** 分节数组 (顺序与标题由后端按文章类型决定; 无内容时为空数组) */
  sections: DeepReadSection[];
  /** 加载中 */
  loading: boolean;
  /** 错误信息 */
  error: string | null;
  /** 读取或生成深度解读: force=false 命中缓存则瞬时返回, 否则调 LLM 生成 */
  regenerate: (entityType: string, entityId: string, force?: boolean) => Promise<void>;
  /** 清空当前状态 */
  clear: () => void;
}

const NO_SECTIONS: DeepReadSection[] = [];

export function useDeepRead(): UseDeepReadReturn {
  const [data, setData] = useState<DeepReadResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchAbortRef = useRef<AbortController | null>(null);

  // 分节由服务端下发 (按文章类型不同), 不再按固定键名枚举取值
  const sections: DeepReadSection[] = Array.isArray(data?.sections)
    ? (data.sections.map(normalizeSection).filter(Boolean) as DeepReadSection[])
    : NO_SECTIONS;

  const clear = useCallback(() => {
    setData(null);
    setError(null);
    setLoading(false);
  }, []);

  const regenerate = useCallback(
    async (entityType: string, entityId: string, force = true) => {
      if (fetchAbortRef.current) fetchAbortRef.current.abort();
      const controller = new AbortController();
      fetchAbortRef.current = controller;

      setLoading(true);
      setError(null);
      try {
        const item = await apiFetch<DeepReadResponse>(
          `/api/deep-read/${encodeURIComponent(entityType)}/${encodeURIComponent(entityId)}?force=${force ? '1' : '0'}`,
          {
            method: 'POST',
            signal: controller.signal,
          },
        );
        setData(item);
      } catch (e: any) {
        if (e?.name === 'AbortError') return;
        setError(e?.message || '深读生成失败');
      } finally {
        if (fetchAbortRef.current === controller) {
          setLoading(false);
        }
      }
    },
    [],
  );

  // 清理
  useEffect(() => {
    return () => {
      fetchAbortRef.current?.abort();
    };
  }, []);

  return { data, sections, loading, error, regenerate, clear };
}
