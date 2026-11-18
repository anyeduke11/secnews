// V1PrototypeParts — 从 V1Prototype.tsx 拆出的共享小件 (纯搬迁, 行为不变).
// 职责: SectionTitle (区块标题 + 路径徽标), 供知识目录视图复用.

// ---------------------------------------------------------------------------
// 共享组件
// ---------------------------------------------------------------------------

export function SectionTitle({ children, path }: { children: React.ReactNode; path: string }) {
  return (
    <div className="flex items-center gap-2 mb-3">
      <h2 className="text-lg font-semibold" style={{ color: 'var(--text-primary)' }}>{children}</h2>
      <span className="text-xs font-mono px-1.5 py-0.5 rounded" style={{ background: 'var(--bg-muted)', color: 'var(--text-muted)' }}>路径: {path}</span>
    </div>
  );
}