/**
 * SentinelHomeAux — 资讯页容器的两处辅助片段 (D7 收口时抽出, 用于守住容器 ≤300 行约束)
 *
 * - `RailWithPipe`: 必须是独立组件 —— 在 SentinelHomePage 函数体内调用 usePipe
 *   会落在 Provider 之外, 永远读到 null。
 * - `SignalPanelLazy`: 受管信号完整面板按需加载 (位于主列之后 = 首屏之下),
 *   不占首屏 JS 包体; 右栏只读摘要走同步加载的 SignalPanelCompact。
 */
import { lazy } from 'react';
import { SentinelRail } from './SentinelRail';
import { usePipe } from './SentinelShell';
import type { QualitySummaryRaw } from './feed/feedModel';

export function RailWithPipe({ quality }: { quality: QualitySummaryRaw | null }) {
  const { pipe } = usePipe();
  return <SentinelRail sources={pipe?.sources ?? []} quality={quality} />;
}

export const SignalPanelLazy = lazy(() =>
  import('../v1/panels/SignalPanel').then(m => ({ default: m.SignalPanel }))
);
