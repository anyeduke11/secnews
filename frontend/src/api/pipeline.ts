/**
 * 管道心跳域 API — 壳 PipeBar 与资讯域 TokenLedger 共用。
 *
 * 单独成文件 (只有 1 个函数) 是为了避免壳入口为取一个端点而把整个
 * api/secnews.ts 拉进首屏 chunk (B3 实测: 直连 secnews 使首屏 +732 B gzip)。
 */

import { getJSON } from '../lib/api';

/** GET /api/kl/pipeline/stats — 管线统计 (漏斗/队列/token ledger) */
export function getKlPipelineStats<T = Record<string, unknown>>(): Promise<T> {
  return getJSON<T>('/api/kl/pipeline/stats');
}