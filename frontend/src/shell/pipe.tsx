/**
 * shell/pipe — 管道心跳数据层 (fetch / Context / hooks)
 *
 * 2026-11-17 结构性拆分自 components/sentinel/SentinelShell.tsx, 逐字搬出:
 *  - fetchPipe: /api/sources/health + /api/kl/pipeline/stats 合并口径
 *  - PipeContext + PipeProvider + usePipe: 子页消费心跳数据 (避免重复拉取)
 *  - mountedReload 登记 + usePipeReloadOnSse: SSE 事件 10s 节流重拉
 *  - fetchIngested24h: 壳未收到 ingested 时的 24h 收录自取口径
 */
import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import { listHotspots } from '../api/hotspots';
import { getSourceHealth, type SourceHealthPayload } from '../api/sources';
import { getKlPipelineStats } from '../api/pipeline';
import type { PipeSnapshot, SourceHealthRow } from './types';

interface PipelineStats {
  funnel?: { stage: string; count: number }[];
  queue?: { pending?: number; running?: number; error?: number };
}

async function fetchPipelineStats(): Promise<Pick<PipeSnapshot, 'funnel' | 'queue'>> {
  try {
    // apiFetch 非 ok / 网络失败抛错 → 降级为 null, 不影响源健康展示
    const data = await getKlPipelineStats<PipelineStats>();
    return {
      funnel: Array.isArray(data.funnel) ? data.funnel : null,
      queue: data.queue
        ? { pending: data.queue.pending ?? 0, running: data.queue.running ?? 0, error: data.queue.error ?? 0 }
        : null,
    };
  } catch {
    // 端点未注册或后端不可达时降级为 null, 不影响源健康展示
    return { funnel: null, queue: null };
  }
}

/** 今日收录兜底口径 (与 SentinelGraphPage 同源): 只取 24h total */
export async function fetchIngested24h(): Promise<number | null> {
  try {
    const data = await listHotspots({ category: 'all', time_range: '24h', limit: 1 });
    return typeof data.total === 'number' ? data.total : null;
  } catch {
    return null;
  }
}

export async function fetchPipe(): Promise<PipeSnapshot> {
  const [res, stats] = await Promise.all([
    // apiFetch 非 ok / 网络失败抛错 → null (对应原 r.ok 分支检查 + .catch(() => null))
    getSourceHealth()
      .then(row => row as SourceHealthPayload & {
        sources?: SourceHealthRow[];
        registered_total: number;
        registered_active: number;
        registered_stale: number;
        registered_dead: number;
      })
      .catch(() => null),
    fetchPipelineStats(),
  ]);
  const rows: SourceHealthRow[] = res?.sources || [];
  // 优先用后端"注册且启用"口径: source_stats 历史行含已无 collector 抓取的孤儿源
  // (旧分母 152 含 22 个孤儿行, 若干还显示 active), 拿它当分母会让"源在线 x/y"
  // 与管道状态一起失真。后端未升级缺字段时回落逐行统计, 保持兼容。
  const registered = typeof res?.registered_total === 'number' ? res : null;
  const active = registered ? registered.registered_active : rows.filter(s => s.status === 'active').length;
  const stale = registered ? registered.registered_stale : rows.filter(s => s.status === 'stale').length;
  const dead = registered ? registered.registered_dead : rows.filter(s => s.status === 'dead').length;
  const total = registered ? registered.registered_total : rows.length;
  const ratio = total > 0 ? active / total : 0;
  return {
    active, stale, dead, total, sources: rows, ...stats,
    health: total === 0 ? '--' : ratio >= 0.9 ? '良好' : ratio >= 0.7 ? '一般' : '告警',
  };
}

export const PipeContext = createContext<{ pipe: PipeSnapshot | null; reload: () => void }>({
  pipe: null,
  reload: () => {},
});

/** 已挂载壳的 reload 登记 — 三层页是「页面渲染壳」结构, 页面组件体内的 hook 永远在 Provider 之外,
 *  经 context 只能拿到默认 no-op (2026-09-10 前 SSE 事件从未真正刷新过心跳条); usePipeReloadOnSse 优先走这里 */
let mountedReload: (() => void) | null = null;

/** 子页消费心跳数据 (避免重复拉取 /api/sources/health); 注意 pipe 只在壳的子树内可读 */
export function usePipe() {
  return useContext(PipeContext);
}

/** 壳层 Provider: 持有心跳快照 + reload, 首挂载拉一次并登记 mountedReload */
export function PipeProvider({ children }: { children: React.ReactNode }) {
  const [pipe, setPipe] = useState<PipeSnapshot | null>(null);

  const reload = useCallback(() => { fetchPipe().then(setPipe); }, []);

  useEffect(() => { reload(); }, [reload]);
  useEffect(() => {
    mountedReload = reload;
    return () => { if (mountedReload === reload) mountedReload = null; };
  }, [reload]);

  return <PipeContext.Provider value={{ pipe, reload }}>{children}</PipeContext.Provider>;
}

/** 心跳条节流刷新 hook — 由各页的 useRealtimeInvalidation (src/hooks/realtime.ts) handler
 *  在 SSE 事件到达时调用。本 hook 本身不订阅 SSE (迁移后也不是 useSSE 消费方), 只提供
 *  10s 节流 + mountedReload 优先于 context reload 的 DEV-0167 语义, 迁移时逐字保留 */
export function usePipeReloadOnSse() {
  const { reload } = usePipe();
  const lastRef = useRef(0);
  return useCallback(() => {
    const now = Date.now();
    if (now - lastRef.current < 10000) return;
    lastRef.current = now;
    (mountedReload ?? reload)();
  }, [reload]);
}