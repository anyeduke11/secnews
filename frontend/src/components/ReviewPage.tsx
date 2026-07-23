// ReviewPage — v1.7 Phase 2 复习页面 (SM-2 间隔复习 + 笔记)
//
// 功能:
//  1. 显示到期复习队列 (useReviews.items)
//  2. ReviewCard 翻转 + 评分 → submitGrade → 队列刷新
//  3. 统计面板 (total / due / avg_easiness)
//  4. 选中某卡片时, 右侧 NoteEditor 展示该实体笔记 (useAnnotations)
//
// 验收 1: 新学概念 24h 出现在复习队列 (由后端 create_review + 24h due 体现)
// 验收 2: 评分后间隔按 SM-2 延长 (评分后该卡片 due_at 推后, 离开队列)
// 验收 3: 笔记 CRUD 正常 (NoteEditor 增删改)
import { useState, useEffect, useMemo } from 'react';
import { useReviews } from '../hooks/useReviews';
import { useAnnotations } from '../hooks/useAnnotations';
import { ReviewCard } from './shared/ReviewCard';
import { NoteEditor } from './shared/NoteEditor';
import { useGoHome } from '../hooks/useGoHome';
import { Icon } from './Icon';

export function ReviewPage() {
  const goHome = useGoHome();
  const { items, stats, loading, error, refresh, submitGrade } = useReviews();
  const {
    items: notes,
    loading: notesLoading,
    load: loadNotes,
    add: addNote,
    update: updateNote,
    remove: removeNote,
  } = useAnnotations();

  const [selected, setSelected] = useState<string | null>(null);

  // 选中项详情
  const selectedItem = useMemo(
    () => items.find((it) => `${it.entity_type}/${it.entity_id}` === selected) || null,
    [items, selected]
  );

  // 选中项变化 → 加载笔记
  useEffect(() => {
    if (selectedItem) {
      loadNotes(selectedItem.entity_type, selectedItem.entity_id);
    }
  }, [selectedItem, loadNotes]);

  const handleGrade = async (grade: number) => {
    if (!selectedItem) return;
    try {
      await submitGrade(selectedItem.entity_type, selectedItem.entity_id, grade);
      setSelected(null);
    } catch (e) {
      console.error('grade failed:', e);
    }
  };

  const selectCard = (key: string) => {
    setSelected(selected === key ? null : key);
  };

  return (
    <div style={pageStyle}>
      {/* 顶部栏 */}
      <div style={topBarStyle}>
        <button type="button" style={backBtnStyle} onClick={goHome} aria-label="返回首页">
          <Icon>
            <line x1="19" y1="12" x2="5" y2="12" />
            <polyline points="12 19 5 12 12 5" />
          </Icon>
          返回
        </button>
        <h1 style={titleStyle}>复习</h1>
        <button type="button" style={refreshBtnStyle} onClick={refresh} disabled={loading}>
          ⟳ 刷新
        </button>
      </div>

      {/* 统计 */}
      <div style={statsRowStyle}>
        <div style={statCardStyle}>
          <div style={statLabelStyle}>总计</div>
          <div style={statValueStyle}>{stats?.total ?? 0}</div>
        </div>
        <div style={{ ...statCardStyle, borderColor: 'var(--color-ai, #00d4e0)' }}>
          <div style={statLabelStyle}>到期</div>
          <div style={{ ...statValueStyle, color: 'var(--color-ai, #00d4e0)' }}>
            {stats?.due ?? 0}
          </div>
        </div>
        <div style={statCardStyle}>
          <div style={statLabelStyle}>平均难度</div>
          <div style={statValueStyle}>
            {stats?.avg_easiness ? stats.avg_easiness.toFixed(2) : '—'}
          </div>
        </div>
      </div>

      {error && <div style={errorBannerStyle}>{error}</div>}

      <div style={contentRowStyle}>
        {/* 复习卡片列表 */}
        <div style={cardsColStyle}>
          {loading && items.length === 0 && (
            <div style={emptyStyle}>加载复习队列…</div>
          )}
          {!loading && items.length === 0 && (
            <div style={emptyStyle}>
              <div style={{ fontSize: 32, marginBottom: 8 }}>✓</div>
              <div>暂无到期复习项</div>
              <div style={subHintStyle}>新概念创建后会自动进入队列</div>
            </div>
          )}
          <div style={cardsGridStyle}>
            {items.map((it) => {
              const key = `${it.entity_type}/${it.entity_id}`;
              const isSelected = selected === key;
              return (
                <div
                  key={it.id}
                  style={isSelected ? cardWrapperActiveStyle : cardWrapperStyle}
                  onClick={() => selectCard(key)}
                >
                  <ReviewCard
                    item={it}
                    onGrade={handleGrade}
                  />
                </div>
              );
            })}
          </div>
        </div>

        {/* 右侧笔记面板 (选中时显示) */}
        {selectedItem && (
          <div style={notesColStyle}>
            <NoteEditor
              entityType={selectedItem.entity_type}
              entityId={selectedItem.entity_id}
              items={notes}
              loading={notesLoading}
              onAdd={(content) =>
                addNote(selectedItem.entity_type, selectedItem.entity_id, content)
              }
              onUpdate={(id, content) => updateNote(id, content)}
              onRemove={(id) => removeNote(id)}
            />
          </div>
        )}
      </div>
    </div>
  );
}

// ── styles (tech-style: 青色主调, 暗色卡片) ───────────────────────
const pageStyle: React.CSSProperties = {
  padding: 'var(--space-4, 16px)',
  maxWidth: 1200,
  margin: '0 auto',
};

const topBarStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 'var(--space-3, 12px)',
  marginBottom: 'var(--space-4, 16px)',
};

const backBtnStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 'var(--space-1, 4px)',
  padding: '4px 10px',
  fontSize: 12,
  border: '1px solid var(--border-color, #1c1c2e)',
  borderRadius: 'var(--radius-sm, 4px)',
  background: 'transparent',
  color: 'var(--text-secondary, #9a9ab2)',
  cursor: 'pointer',
};

const titleStyle: React.CSSProperties = {
  fontSize: 18,
  fontWeight: 600,
  color: 'var(--text-primary, #f0f0f7)',
  flex: 1,
};

const refreshBtnStyle: React.CSSProperties = {
  padding: '4px 12px',
  fontSize: 12,
  border: '1px solid var(--border-color, #1c1c2e)',
  borderRadius: 'var(--radius-sm, 4px)',
  background: 'transparent',
  color: 'var(--text-secondary, #9a9ab2)',
  cursor: 'pointer',
};

const statsRowStyle: React.CSSProperties = {
  display: 'flex',
  gap: 'var(--space-3, 12px)',
  marginBottom: 'var(--space-4, 16px)',
};

const statCardStyle: React.CSSProperties = {
  flex: 1,
  padding: 'var(--space-3, 12px)',
  border: '1px solid var(--border-color, #1c1c2e)',
  borderRadius: 'var(--radius-md, 8px)',
  background: 'var(--bg-card, #0d0d14)',
  textAlign: 'center',
};

const statLabelStyle: React.CSSProperties = {
  fontSize: 11,
  color: 'var(--text-muted, #5b5b72)',
  fontFamily: 'monospace',
  textTransform: 'uppercase',
};

const statValueStyle: React.CSSProperties = {
  fontSize: 24,
  fontWeight: 700,
  color: 'var(--text-primary, #f0f0f7)',
  fontFamily: 'monospace',
  marginTop: 'var(--space-1, 4px)',
};

const errorBannerStyle: React.CSSProperties = {
  padding: 'var(--space-2, 8px) var(--space-3, 12px)',
  marginBottom: 'var(--space-3, 12px)',
  border: '1px solid var(--color-error, #ef4444)',
  borderRadius: 'var(--radius-sm, 4px)',
  background: 'rgba(239, 68, 68, 0.08)',
  color: 'var(--color-error, #ef4444)',
  fontSize: 12,
};

const contentRowStyle: React.CSSProperties = {
  display: 'flex',
  gap: 'var(--space-4, 16px)',
  alignItems: 'flex-start',
};

const cardsColStyle: React.CSSProperties = {
  flex: 1,
  minWidth: 0,
};

const cardsGridStyle: React.CSSProperties = {
  display: 'grid',
  gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))',
  gap: 'var(--space-3, 12px)',
};

const cardWrapperStyle: React.CSSProperties = {
  borderRadius: 'var(--radius-md, 8px)',
  transition: 'box-shadow 0.2s',
};

const cardWrapperActiveStyle: React.CSSProperties = {
  ...cardWrapperStyle,
  boxShadow: '0 0 0 2px var(--color-ai, #00d4e0), 0 0 16px rgba(0, 212, 224, 0.3)',
};

const emptyStyle: React.CSSProperties = {
  padding: 'var(--space-6, 32px)',
  textAlign: 'center',
  color: 'var(--text-muted, #5b5b72)',
  fontSize: 14,
};

const subHintStyle: React.CSSProperties = {
  fontSize: 11,
  marginTop: 'var(--space-1, 4px)',
  color: 'var(--text-disabled, #414155)',
};

const notesColStyle: React.CSSProperties = {
  width: 360,
  flexShrink: 0,
};

export default ReviewPage;
