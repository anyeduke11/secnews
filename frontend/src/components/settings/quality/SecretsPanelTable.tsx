/**
 * quality/SecretsPanelTable — 密钥列表表格 (拆分自 SecretsPanel.tsx)
 *
 * 纯渲染: 数据与操作回调由 SecretsPanel 注入, 本组件不持有状态。
 */
interface SecretsPanelTableProps {
  list: Array<Record<string, any>>;
  onReveal: (id: number) => void;
  onTest: (id: number) => void;
  onEdit: (s: Record<string, any>) => void;
  onRemove: (s: Record<string, any>) => void;
}

export function SecretsPanelTable({ list, onReveal, onTest, onEdit, onRemove }: SecretsPanelTableProps) {
  return (
    <table className="st-table" aria-label="密钥列表">
      <thead>
        <tr>
          <th>名称</th>
          <th>Provider</th>
          <th>Model · Base URL</th>
          <th style={{ width: 200 }}>操作</th>
        </tr>
      </thead>
      <tbody>
        {list.map(s => (
          <tr key={s.id} data-testid={`secrets-row-${s.id}`}>
            <td><span className="st-nm">{s.name || '(无名)'}</span></td>
            <td>{s.provider || '(无)'}</td>
            <td>
              <span className="st-sub">{s.model}</span>
              <span className="st-sub">{s.base_url}</span>
            </td>
            <td>
              <div className="st-ctrlrow">
                <button type="button" className="st-btn ghost" onClick={() => onReveal(s.id)} title="显明文 10s 自动隐藏">显明文</button>
                <button type="button" className="st-btn ghost" onClick={() => onTest(s.id)}>测连</button>
                <button type="button" className="st-btn ghost" onClick={() => onEdit(s)}>编辑</button>
                <button type="button" className="st-btn danger" onClick={() => onRemove(s)}>删</button>
              </div>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}