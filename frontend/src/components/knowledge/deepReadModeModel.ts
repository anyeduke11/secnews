/**
 * deepReadModeModel — 深度阅读页纯类型 (B5 续拆自 DeepReadMode)
 *
 * 只放无 React 依赖的内容, 供容器与展示区块共享。
 */
import type { KnowledgeItem } from '../../types';

export interface RecommendResult {
  item: KnowledgeItem;
  score: number;
  shared_tags: string[];
}

export interface RecommendResponse {
  version: string;
  entity_type: string;
  entity_id: string;
  items: RecommendResult[];
}

export interface ChunkInfo {
  id: number;
  item_id: string;
  chunk_index: number;
  content: string;
  char_start: number;
  char_end: number;
  summary: string;
  created_at: string;
}

/** 主条目 (接口返回 = KnowledgeItem + content/lifecycle 扩展字段) */
export type DeepReadItem = KnowledgeItem & { content?: string; lifecycle?: string };
