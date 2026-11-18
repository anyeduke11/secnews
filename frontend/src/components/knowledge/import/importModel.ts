/**
 * importModel — 信息导入页 (KnowledgeImport) 的纯类型 / 常量 (B5 从 KnowledgeImport 抽出)
 *
 * 只放无 React 依赖的内容; 展示区块见同目录 Import*.tsx / *Card.tsx。
 */

/** 同步进度阶段 → 文案 */
export const PHASE_LABELS: Record<string, string> = {
  pending: '等待执行 ...',
  connecting: '连接 Cubox ...',
  fetching: '获取卡片列表 ...',
  processing: '处理条目',
  syncing_db: '同步数据库 ...',
  done: '完成',
};

/** /api/knowledge/tasks/{id} 轮询响应中本页面消费的字段 */
export interface CuboxTask {
  status?: string;
  error_message?: string;
  params?: {
    phase?: string;
    current?: number;
    total?: number;
    result?: { new?: number; merged?: number };
  };
}

/** watchdog 冲突快照条目 */
export interface ConflictFile {
  filename: string;
  size: number;
  mtime: number;
}

/** 页内 Toast */
export interface ImportToastMsg {
  kind: 'ok' | 'err';
  msg: string;
}
