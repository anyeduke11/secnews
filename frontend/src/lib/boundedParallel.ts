/**
 * C11 R19: boundedParallel - 限制并发上限的 Promise.all 替代.
 *
 * 旧实现 (V1Prototype refetchChain):
 *   for (const a of actions) {
 *     const r = await listRuns({ action_id: a.id });
 *     for (const run of r.items) {
 *       const arts = await listArtifacts({ run_id: run.id });
 *       ...
 *     }
 *   }
 *   → 串行等待, 50 个 action × 5 runs = 250 次串行, P95 latency = 250 × 80ms = 20s
 *
 * 修复:
 *   await boundedParallel(items, async (item) => op(item), 8)
 *   → 最多 8 并发, 同一时点始终 ≤ 8 in-flight, 浏览器连接池不被吃光
 *   50 个 action × 5 runs 用 8 并发, P95 latency ≈ ceil(50×5/8) × 80ms = 5s
 *
 * 错误隔离: 任意一个 reject 立即 reject 整个 pool, 调用方需 try/catch
 * (Mimosa 禁 silent, R19 走的是服务端聚合端点, 本函数为前端兜底, 实际不再用)
 */
export async function boundedParallel<T, R>(
  items: readonly T[],
  fn: (item: T, index: number) => Promise<R>,
  concurrency: number = 8,
): Promise<R[]> {
  if (items.length === 0) return [];
  const limit = Math.max(1, Math.min(concurrency, items.length));
  const results: R[] = new Array(items.length);
  let nextIndex = 0;

  const worker = async (): Promise<void> => {
    while (true) {
      const i = nextIndex;
      nextIndex += 1;
      if (i >= items.length) return;
      results[i] = await fn(items[i], i);
    }
  };

  const workers = Array.from({ length: limit }, () => worker());
  await Promise.all(workers);
  return results;
}
