// NotePanel — v1.7 Phase 4 笔记面板 (DeepReadView 专用)
//
// 功能:
//  1. 根据 entityType + entityId 加载该实体的笔记 (useAnnotations)
//  2. 委托给 NoteEditor 渲染 (复用 Phase 2 组件)
//  3. 提供 add / update / remove 操作
//
// 与 ReviewPage 区别: ReviewPage 的 NoteEditor 依赖 ReviewCard 选中状态;
// 此处 NotePanel 独立加载当前实体笔记, 用于 DeepReadView 三栏布局.
import { useEffect } from 'react';
import { useAnnotations } from '../hooks/useAnnotations';
import { NoteEditor } from './shared/NoteEditor';

export interface NotePanelProps {
  entityType: string;
  entityId: string;
}

export function NotePanel({ entityType, entityId }: NotePanelProps) {
  const {
    items,
    loading,
    load,
    add,
    update,
    remove,
  } = useAnnotations();

  // 实体变化 → 加载笔记
  useEffect(() => {
    if (entityType && entityId) {
      load(entityType, entityId);
    }
  }, [entityType, entityId, load]);

  return (
    <div style={panelStyle} aria-label="笔记面板">
      <NoteEditor
        entityType={entityType}
        entityId={entityId}
        items={items}
        loading={loading}
        onAdd={(content) => add(entityType, entityId, content)}
        onUpdate={(id, content) => update(id, content)}
        onRemove={(id) => remove(id)}
      />
    </div>
  );
}

const panelStyle: React.CSSProperties = {
  width: 360,
  flexShrink: 0,
};

export default NotePanel;
