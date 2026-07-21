/**
 * resource-hub/types — ResourceHub 共享类型 & 常量。
 *
 * Phase 1B: 拆自原 ResourceHub.tsx, 集中放置端口/资源相关常量与 props。
 * 避免子组件之间循环 import, 状态/回调通过 props 注入。
 */
import type { CgResource, ResourceStatus } from '../../../types/codegarden';

export const PROTECTED_PORTS = new Set<number>([8898]);
export const PORT_RANGE_START = 8000;
export const PORT_RANGE_END = 9999;

export const PORT_STATUS_COLORS: Record<ResourceStatus, string> = {
  allocated: 'var(--color-error)',
  free: 'var(--color-success)',
  reserved: 'var(--color-warning)',
};

export const PROTECTED_COLOR = 'var(--color-info)';

export type FlashKind = 'ok' | 'err';

export type PortStatus = 'free' | 'allocated' | 'reserved' | 'protected';

export interface PortPoolProps {
  items: CgResource[];
  onAllocate: (req: { preferred_port?: number }) => Promise<CgResource>;
  onRelease: (port: number) => Promise<void>;
}

export interface ResourceCardProps {
  resource: CgResource;
  onRemove?: () => void | Promise<void>;
}

export interface ResourceListProps {
  items: CgResource[];
  loading: boolean;
  error: string | null;
  typeLabel: string;
  onRemove: (id: string) => void | Promise<void>;
}
