import { useState, useEffect, useCallback } from 'react';
import { KnowledgeItem } from '../types';
import { createAnnotation, deleteKnowledgeItem, getKnowledgeItem, listAnnotations, updateKnowledgeItem } from '../api/knowledge';
import type { KnowledgeItemPatch } from '../api/knowledge';
import { ItemDetailDialogProps, ItemAnnotation } from './ItemDetailDialog.types';
import { ItemDetailDialogHeader } from './ItemDetailDialogHeader';
import { ItemDetailDialogFooter } from './ItemDetailDialogFooter';
import {
  BasicInfoSection,
  CategoryEditSection,
  TagsSection,
  ConceptsSection,
  AnnotationSection,
  MasterySection,
  ContentSection,
} from './ItemDetailDialogParts';

export function ItemDetailDialog({ item_id, onClose }: ItemDetailDialogProps) {
  const [item, setItem] = useState<KnowledgeItem | null>(null);
  const [content, setContent] = useState<string>('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  // P3-3: 标注 (此前 NoteEditor 只在不可达的死路由 /reviews /deep 中,
  // annotations 表恒 0 → 标注功能在实际 UI 中不存在)
  const [notes, setNotes] = useState<ItemAnnotation[]>([]);
  const [noteText, setNoteText] = useState('');
  const [noteSaving, setNoteSaving] = useState(false);

  const loadNotes = useCallback((id: string) => {
    // 原 r.ok ? json : null 语义经 apiFetch 归一: 非 ok 也走 catch → null → 清空 notes
    listAnnotations<ItemAnnotation>('knowledge_item', id)
      .catch(() => null)
      .then(data => {
        const items = data?.items ?? data?.annotations ?? [];
        setNotes(Array.isArray(items) ? items : []);
      });
  }, []);

  // 编辑字段
  const [domain, setDomain] = useState('');
  const [topic, setTopic] = useState('');
  const [type, setType] = useState('');
  const [difficulty, setDifficulty] = useState('');
  const [tagsText, setTagsText] = useState('');
  const [mastery, setMastery] = useState(0);

  const loadItem = useCallback((id: string) => {
    setLoading(true);
    setError(null);
    getKnowledgeItem(id)
      .then(it => {
        setItem(it);
        setContent(it.content || '');
        setDomain(it.domain || '');
        setTopic(it.topic || '');
        setType(it.type || '');
        setDifficulty(it.difficulty || '');
        setTagsText((it.tags || []).join(', '));
        setMastery(it.mastery ?? 0);
        setLoading(false);
      })
      .catch(e => {
        setError(e?.message || String(e));
        setLoading(false);
      });
  }, []);

  useEffect(() => {
    if (item_id) {
      // 重置状态
      setItem(null);
      setContent('');
      setError(null);
      setConfirmDelete(false);
      setToast(null);
      setNotes([]);
      setNoteText('');
      loadItem(item_id);
      loadNotes(item_id);
    }
  }, [item_id, loadItem, loadNotes]);

  const handleAddNote = () => {
    if (!item_id || !noteText.trim()) return;
    setNoteSaving(true);
    createAnnotation({
      entity_type: 'knowledge_item',
      entity_id: item_id,
      content: noteText.trim(),
    })
      .then(() => {
        setNoteText('');
        loadNotes(item_id);
      })
      .catch(e => {
        setToast(`✗ 标注失败: ${e?.message || String(e)}`);
        setTimeout(() => setToast(null), 2500);
      })
      .finally(() => setNoteSaving(false));
  };

  if (!item_id) return null;

  const handleSave = () => {
    if (!item_id) return;
    const tagsArray = tagsText
      .split(',')
      .map(t => t.trim())
      .filter(t => t.length > 0);
    const body: KnowledgeItemPatch = {
      domain: domain || null,
      topic: topic || null,
      type: type || null,
      difficulty: difficulty || null,
      tags: tagsArray,
      mastery,
    };
    setSaving(true);
    updateKnowledgeItem(item_id, body)
      .then(() => {
        setToast('✓ 保存成功');
        setTimeout(() => setToast(null), 2500);
        // 重新加载
        loadItem(item_id);
      })
      .catch(e => {
        setToast(`✗ 保存失败: ${e?.message || String(e)}`);
        setTimeout(() => setToast(null), 2500);
      })
      .finally(() => setSaving(false));
  };

  const handleDelete = () => {
    if (!item_id) return;
    setDeleting(true);
    deleteKnowledgeItem(item_id)
      .then(() => {
        onClose();
      })
      .catch(e => {
        setToast(`✗ 删除失败: ${e?.message || String(e)}`);
        setTimeout(() => setToast(null), 2500);
      })
      .finally(() => setDeleting(false));
  };

  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed', inset: 0, zIndex: 50,
        backgroundColor: 'var(--bg-overlay)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}
    >
      <div
        onClick={e => e.stopPropagation()}
        className="tech-modal p-4"
        style={{
          width: '800px',
          maxWidth: '90vw',
          maxHeight: '80vh',
          overflowY: 'auto',
        }}
      >
        {/* 顶部标题 */}
        <ItemDetailDialogHeader onClose={onClose} />

        {loading && (
          <p className="text-xs py-4 text-center" style={{ color: 'var(--text-muted)' }}>
            加载中…
          </p>
        )}

        {error && (
          <div
            className="rounded-[var(--radius-sm)] p-2.5 mb-3 text-xs"
            style={{ backgroundColor: 'color-mix(in srgb, var(--color-error) 12%, transparent)', border: '1px solid var(--color-error)', color: 'var(--color-error)' }}
          >
            加载失败: {error}
          </div>
        )}

        {item && !loading && (
          <div className="space-y-3">
            <BasicInfoSection item={item} />
            <CategoryEditSection
              domain={domain}
              topic={topic}
              type={type}
              difficulty={difficulty}
              onDomainChange={setDomain}
              onTopicChange={setTopic}
              onTypeChange={setType}
              onDifficultyChange={setDifficulty}
            />
            <TagsSection tagsText={tagsText} onTagsTextChange={setTagsText} />
            <ConceptsSection concepts={item.concepts} />
            <AnnotationSection
              notes={notes}
              noteText={noteText}
              noteSaving={noteSaving}
              onNoteTextChange={setNoteText}
              onAddNote={handleAddNote}
            />
            <MasterySection mastery={mastery} onMasteryChange={setMastery} />
            <ContentSection content={content} />
            <ItemDetailDialogFooter
              saving={saving}
              deleting={deleting}
              confirmDelete={confirmDelete}
              toast={toast}
              onSave={handleSave}
              onRequestDelete={() => setConfirmDelete(true)}
              onCancelDelete={() => setConfirmDelete(false)}
              onDelete={handleDelete}
            />
          </div>
        )}
      </div>
    </div>
  );
}