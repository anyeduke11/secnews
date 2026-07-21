/**
 * service-mesh/types — ServiceMesh 共享类型 & 常量。
 *
 * Phase 1B: 拆自原 ServiceMesh.tsx, 集中放置跨子组件共享的 props/常量。
 * 避免子组件之间循环 import, 状态/回调通过 props 注入。
 */
import type {
  CgService,
  ServiceRuntime,
  ServiceStatus,
  ServiceType,
} from '../../../types/codegarden';

export const RUNTIME_OPTIONS: Array<ServiceRuntime | 'all'> = [
  'all', 'docker', 'pm2', 'system', 'bare',
];

export const STATUS_OPTIONS: Array<ServiceStatus | 'all'> = [
  'all', 'running', 'stopped', 'error', 'unknown',
];

export const TYPE_OPTIONS: Array<ServiceType | 'all'> = [
  'all', 'http', 'websocket', 'grpc', 'static', 'database',
];

export const STATUS_LABELS: Record<ServiceStatus, string> = {
  running: '运行中',
  stopped: '已停止',
  error: '异常',
  unknown: '未知',
};

export type FlashKind = 'ok' | 'err';
export type FlashFn = (kind: FlashKind, msg: string) => void;

export interface ServiceMeshProps {
  onShowTopology?: () => void;
}

export interface ServiceCardProps {
  service: CgService;
  onClick?: () => void;
}

export interface ServiceDetailDialogProps {
  service: CgService;
  onClose: () => void;
  onRestart: (id: string) => Promise<{ task_id: number }>;
  getLogs: (id: string, tail?: number) => Promise<string>;
  getMetrics: (id: string) => Promise<Record<string, unknown>>;
  onFlash: FlashFn;
}

export interface MetaRowProps {
  label: string;
  value: string;
  mono?: boolean;
}
