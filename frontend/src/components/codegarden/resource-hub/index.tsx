/**
 * ResourceHub — M3 资源中枢主面板（Phase 1B 拆分后）。
 *
 * Phase 1B: 拆自原 ResourceHub.tsx (15KB / 393 行 → 4 文件, 每文件 ≤ 10KB)。
 * 4 个 tab：端口 / 域名 / 环境模板 / 存储卷
 * 端口 tab → PortPool 网格（带 8898 保护）；其余 tab → ResourceCard 列表。
 *
 * 公开 API 完全保留（<ResourceHub />）。
 */
import { useState } from 'react';
import { CgResource, RESOURCE_TYPE_LABELS, ResourceType } from '../../../types/codegarden';
import { useCodegardenResources } from '../../../hooks/useCodegardenResources';
import { Icon } from '../../Icon';
import { PortPool } from './PortPool';
import { ResourceCard } from './ResourceCard';

type Tab = ResourceType;

export function ResourceHub() {
  const [tab, setTab] = useState<Tab>('port');
  const {
    items, total, loading, error,
    resourceType, resourceStatus,
    setResourceType, setResourceStatus,
    refresh, allocatePort, releasePort, remove,
  } = useCodegardenResources();

  // 切换 tab 时同步筛选
  const switchTab = (t: Tab) => {
    setTab(t);
    setResourceType(t);
    setResourceStatus('all');
  };

  const handleRemove = async (id: string) => {
    await remove(id);
  };

  const filteredByType = (t: Tab) => items.filter((it) => it.type === t);

  return (
    <div>
      <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
        <div
          className="flex items-center gap-1 border-b"
          style={{ borderColor: 'var(--border-color)' }}
        >
          {(Object.keys(RESOURCE_TYPE_LABELS) as Tab[]).map((t) => (
            <button
              key={t}
              onClick={() => switchTab(t)}
              className="px-3 py-1.5 text-[11px]"
              style={{
                color: tab === t ? 'var(--color-ai)' : 'var(--text-secondary)',
                borderBottom: tab === t ? '2px solid var(--color-ai)' : '2px solid transparent',
              }}
            >
              {RESOURCE_TYPE_LABELS[t]}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
            共 {total}
          </span>
          <button
            onClick={refresh}
            className="btn-ghost px-2 py-1.5 text-xs"
            title="刷新"
          >
            <Icon>
              <polyline points="23 4 23 10 17 10" />
              <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
            </Icon>
          </button>
        </div>
      </div>

      {tab === 'port' && (
        <PortPool
          items={filteredByType('port')}
          onAllocate={allocatePort}
          onRelease={releasePort}
        />
      )}

      {tab !== 'port' && (
        <ResourceListSection
          items={filteredByType(tab)}
          loading={loading}
          error={error}
          typeLabel={RESOURCE_TYPE_LABELS[tab]}
          onRemove={handleRemove}
        />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// ResourceListSection — 非端口资源的列表区（loading / empty / 卡片网格）
// ---------------------------------------------------------------------------
interface ResourceListSectionProps {
  items: CgResource[];
  loading: boolean;
  error: string | null;
  typeLabel: string;
  onRemove: (id: string) => void | Promise<void>;
}

function ResourceListSection({
  items, loading, error, typeLabel, onRemove,
}: ResourceListSectionProps) {
  if (loading) {
    return (
      <div
        className="text-xs text-center py-6"
        style={{ color: 'var(--text-muted)' }}
      >
        加载中…
      </div>
    );
  }
  if (error) {
    return (
      <div className="text-xs text-center py-6" style={{ color: '#e85d5d' }}>
        {error}
      </div>
    );
  }
  if (items.length === 0) {
    return (
      <div
        className="text-xs text-center py-6"
        style={{ color: 'var(--text-muted)' }}
      >
        暂无{typeLabel}
      </div>
    );
  }
  return (
    <div
      className="grid gap-2"
      style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))' }}
    >
      {items.map((r) => (
        <ResourceCard
          key={r.id}
          resource={r}
          onRemove={() => onRemove(r.id)}
        />
      ))}
    </div>
  );
}
