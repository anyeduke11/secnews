/**
 * 三层能力区块共享壳 (v0.8.5 layout-retrofit D01-D03).
 *
 * 排版债务修复: 三个面板原先各自内联 marginTop 22/26 + padding 14px 16px +
 * borderRadius 10 — 裸数值且互不一致 (同一视觉组件三份漂移拷贝)。
 * 统一映射到项目令牌 (index.css): 间距 --space-3/--space-4/--space-6 (4px 基数),
 * 圆角 --radius-lg (=10px, 值不变)。视觉指纹不变, 只正骨不动脸。
 */
import type { CSSProperties } from 'react';

export const PANEL_SHELL: CSSProperties = {
  marginTop: 'var(--space-6)',
  padding: 'var(--space-3) var(--space-4)',
  borderRadius: 'var(--radius-lg)',
  border: '1px solid var(--sn-line, var(--line))',
  background: 'var(--sn-bg-panel, var(--bg-card))',
};
