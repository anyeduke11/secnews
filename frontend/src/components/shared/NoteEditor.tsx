import { useState, useEffect } from 'react';
import type { Annotation } from '../../hooks/useAnnotations';
import { NoteEditorComposer } from './NoteEditorComposer';
import { NoteEditorList } from './NoteEditorList';
import {
  countStyle,
  errorStyle,
  headerStyle,
  mutedStyle,
  titleStyle,
  wrapperStyle,
} from './noteEditorModel';

/**
 * v1.7 Phase 2 — NoteEditor 笔记编辑器
 *
 * Props:
 *  - entityType / entityId:  当前实体 (笔记归属)
 *  - items:                  该实体的笔记列表
 *  - onAdd:     (content, rangeStart?, rangeEnd?) => Promise<Annotation>
 *  - onUpdate:  (annotationId, content) => Promise<Annotation>
 *  - onRemove:  (annotationId) => Promise<void>
 *
 * 行为:
 *  - 顶部输入框 + 添加按钮 (验收 3: 笔记 CRUD 正常)
 *  - 列表显示已有笔记, 每条可编辑/删除
 *  - 编辑模式: 点击编辑 → 文本框 + 保存/取消
 *
 * B5.6 拆分: 本文件只保留容器 (状态 + CRUD 编排); 展示区块见同目录
 * NoteEditorComposer.tsx / NoteEditorList.tsx, 内联 style 常量见 noteEditorModel.ts。
 */

export interface NoteEditorProps {
  entityType: string;
  entityId: string;
  items: Annotation[];
  loading?: boolean;
  onAdd: (content: string, rangeStart?: number, rangeEnd?: number) => Promise<Annotation>;
  onUpdate: (annotationId: string, content: string) => Promise<Annotation>;
  onRemove: (annotationId: string) => Promise<void>;
}

export function NoteEditor({
  entityType,
  entityId,
  items,
  loading,
  onAdd,
  onUpdate,
  onRemove,
}: NoteEditorProps) {
  const [draft, setDraft] = useState('');
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingContent, setEditingContent] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 切换实体时清空草稿
  useEffect(() => {
    setDraft('');
    setEditingId(null);
    setError(null);
  }, [entityType, entityId]);

  const handleAdd = async () => {
    const content = draft.trim();
    if (!content) return;
    setBusy(true);
    setError(null);
    try {
      await onAdd(content);
      setDraft('');
    } catch (e: any) {
      setError(e?.message || '添加笔记失败');
    } finally {
      setBusy(false);
    }
  };

  const startEdit = (a: Annotation) => {
    setEditingId(a.id);
    setEditingContent(a.content);
  };

  const cancelEdit = () => {
    setEditingId(null);
    setEditingContent('');
  };

  const saveEdit = async () => {
    if (!editingId) return;
    const content = editingContent.trim();
    if (!content) return;
    setBusy(true);
    setError(null);
    try {
      await onUpdate(editingId, content);
      cancelEdit();
    } catch (e: any) {
      setError(e?.message || '更新笔记失败');
    } finally {
      setBusy(false);
    }
  };

  const handleRemove = async (id: string) => {
    setBusy(true);
    setError(null);
    try {
      await onRemove(id);
    } catch (e: any) {
      setError(e?.message || '删除笔记失败');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="note-editor" style={wrapperStyle}>
      <div style={headerStyle}>
        <span style={titleStyle}>笔记</span>
        <span style={countStyle}>{items.length} 条</span>
      </div>

      {/* 新建输入 */}
      <NoteEditorComposer
        entityType={entityType}
        entityId={entityId}
        draft={draft}
        busy={busy}
        onDraftChange={setDraft}
        onAdd={handleAdd}
      />

      {error && <div style={errorStyle}>{error}</div>}
      {loading && <div style={mutedStyle}>加载中…</div>}

      {/* 笔记列表 */}
      <NoteEditorList
        items={items}
        loading={!!loading}
        busy={busy}
        editingId={editingId}
        editingContent={editingContent}
        onEditingContentChange={setEditingContent}
        onStartEdit={startEdit}
        onSaveEdit={saveEdit}
        onCancelEdit={cancelEdit}
        onRemove={handleRemove}
      />
    </div>
  );
}

export default NoteEditor;
