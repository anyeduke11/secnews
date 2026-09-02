/**
 * SourceItem — 单条自定义信源渲染 (Sentinel V2)。
 *
 * V2 token: --sn-ink / --sn-ink-3 / --sn-mint / --sn-red / --sn-bg-hover
 * 嵌入 SourceSettings (PipelineSettings 信源管理) 中使用.
 */
export interface SourceItemData {
  id: number;
  name: string;
  url: string;
  category: string;
  enabled: boolean;
  last_check_status?: string;
  last_check_latency_ms?: number;
}

interface SourceItemProps {
  source: SourceItemData;
  onToggle: (id: number, enabled: boolean) => void;
  onProbe: (id: number) => void;
  onDelete: (id: number) => void;
}

export function SourceItem({ source: s, onToggle, onProbe, onDelete }: SourceItemProps) {
  return (
    <div
      style={{
        padding: 'var(--sn-cell-pad)',
        borderRadius: 'var(--sn-radius-md)',
        backgroundColor: 'var(--sn-bg-hover)',
        border: '1px solid var(--sn-line)',
        fontSize: 'var(--sn-fs-mute)',
        display: 'flex',
        flexDirection: 'column',
        gap: 6,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span
          style={{
            fontFamily: 'var(--sn-mono)',
            color: 'var(--sn-ink)',
            flex: 1,
            minWidth: 0,
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}
          title={s.url}
        >
          {s.name || s.url}
        </span>
        <span
          style={{
            padding: '2px 8px',
            borderRadius: 'var(--sn-radius-sm)',
            fontSize: 10,
            backgroundColor: 'color-mix(in srgb, var(--sn-mint) 14%, transparent)',
            color: 'var(--sn-mint)',
            fontFamily: 'var(--sn-mono)',
            letterSpacing: '0.03em',
          }}
        >
          {s.category}
        </span>
      </div>
      <div style={{ fontSize: 'var(--sn-fs-mute)', color: 'var(--sn-ink-3)' }}>
        {s.last_check_status || '未探测'} · {Math.round(s.last_check_latency_ms || 0)}ms
      </div>
      <div style={{ display: 'flex', gap: 6 }}>
        <button
          className="st-btn"
          onClick={() => onToggle(s.id, !s.enabled)}
          style={{
            padding: '4px 10px',
            fontSize: 11,
            backgroundColor: s.enabled ? 'var(--sn-mint)' : 'var(--sn-bg-1)',
            color: s.enabled ? 'var(--bg-primary)' : 'var(--sn-ink-3)',
            borderColor: s.enabled ? 'var(--sn-mint)' : 'var(--sn-line)',
          }}
        >
          {s.enabled ? '启用' : '禁用'}
        </button>
        <button
          className="st-btn"
          onClick={() => onProbe(s.id)}
          style={{ padding: '4px 10px', fontSize: 11 }}
        >
          探测
        </button>
        <button
          className="st-btn danger"
          onClick={() => onDelete(s.id)}
          style={{ padding: '4px 10px', fontSize: 11 }}
        >
          删除
        </button>
      </div>
    </div>
  );
}