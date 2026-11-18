/**
 * Badge — CaseDetail 状态徽章原子 (B5 续拆: 自 CaseDetail.tsx 原样搬运)
 *
 * v1.0.1 一致性重构: Badge 改用 CSS 变量 token (light/dark 双值), 背景用 color-mix 表达 dim 透明层.
 * 兼容: CaseDetail.tsx 仍 `export { Badge }`, V1Prototype.tsx 旧 import 路径不变。
 */

export function Badge({ children, color }: { children: React.ReactNode; color: 'green' | 'red' | 'yellow' | 'gray' | 'blue' }) {
  const styles: Record<string, { bg: string; fg: string }> = {
    green:  { bg: 'color-mix(in srgb, var(--color-success) 14%, transparent)', fg: 'var(--color-success)' },
    red:    { bg: 'color-mix(in srgb, var(--color-error)   14%, transparent)', fg: 'var(--color-error)' },
    yellow: { bg: 'color-mix(in srgb, var(--color-warning) 14%, transparent)', fg: 'var(--color-warning)' },
    gray:   { bg: 'color-mix(in srgb, var(--text-muted)   14%, transparent)', fg: 'var(--text-secondary)' },
    blue:   { bg: 'color-mix(in srgb, var(--color-info)    14%, transparent)', fg: 'var(--color-info)' },
  };
  const s = styles[color] || styles.gray;
  return (
    <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium" style={{ background: s.bg, color: s.fg }}>
      {children}
    </span>
  );
}
