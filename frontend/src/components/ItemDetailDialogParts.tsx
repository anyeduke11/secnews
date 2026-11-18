// 拆分自 ItemDetailDialog.tsx: 详情正文的各展示区块
// (基本信息 / 分类编辑 / 标签 / 概念只读 / 标注笔记 / 掌握度 / Markdown 正文)。
// 均为纯展示件, 状态与请求仍由主组件持有。
import { KnowledgeItem } from '../types';
import { ItemAnnotation } from './ItemDetailDialog.types';

const DOMAINS = ['security', 'ai', 'finance', 'startup', 'engineering', 'product'];
const TYPES = ['news', 'analysis', 'paper', 'tutorial', 'tool', 'opinion'];
const DIFFICULTIES = ['beginner', 'intermediate', 'advanced', 'expert'];

const labelStyle: React.CSSProperties = {
  color: 'var(--text-muted)',
  fontSize: '10px',
  marginBottom: '2px',
  display: 'block',
};

/** 1. 基本信息 — 标题 / 来源 / 原文链接 / 录入时间 (只读) */
export function BasicInfoSection({ item }: { item: KnowledgeItem }) {
  return (
    <div>
      <p className="text-[10px] mb-1" style={{ color: 'var(--text-muted)' }}>基本信息</p>
      <div className="rounded-[var(--radius-sm)] p-2.5" style={{ backgroundColor: 'var(--bg-hover)' }}>
        <div className="text-sm font-semibold mb-1" style={{ color: 'var(--text-primary)' }}>
          {item.title}
        </div>
        <div className="text-[10px] space-y-0.5" style={{ color: 'var(--text-muted)' }}>
          <div>来源: {item.source} {item.source_url && <span>· <a href={item.source_url} target="_blank" rel="noreferrer" style={{ color: 'var(--color-ai)' }}>原文链接</a></span>}</div>
          <div>录入时间: {item.ingested_at}</div>
        </div>
      </div>
    </div>
  );
}

type CategoryEditSectionProps = {
  domain: string;
  topic: string;
  type: string;
  difficulty: string;
  onDomainChange: (v: string) => void;
  onTopicChange: (v: string) => void;
  onTypeChange: (v: string) => void;
  onDifficultyChange: (v: string) => void;
};

/** 2. 分类编辑 — domain / topic / type / difficulty */
export function CategoryEditSection({
  domain,
  topic,
  type,
  difficulty,
  onDomainChange,
  onTopicChange,
  onTypeChange,
  onDifficultyChange,
}: CategoryEditSectionProps) {
  return (
    <div>
      <p className="text-[10px] mb-1" style={{ color: 'var(--text-muted)' }}>分类</p>
      <div className="grid grid-cols-2 gap-2">
        <div>
          <label style={labelStyle}>domain</label>
          <select className="tech-select px-2 py-1 text-xs w-full" value={domain} onChange={e => onDomainChange(e.target.value)}>
            <option value="">(未设置)</option>
            {DOMAINS.map(d => <option key={d} value={d}>{d}</option>)}
          </select>
        </div>
        <div>
          <label style={labelStyle}>topic</label>
          <input type="text" className="tech-input px-2 py-1 text-xs w-full" value={topic} onChange={e => onTopicChange(e.target.value)} placeholder="主题" />
        </div>
        <div>
          <label style={labelStyle}>type</label>
          <select className="tech-select px-2 py-1 text-xs w-full" value={type} onChange={e => onTypeChange(e.target.value)}>
            <option value="">(未设置)</option>
            {TYPES.map(t => <option key={t} value={t}>{t}</option>)}
          </select>
        </div>
        <div>
          <label style={labelStyle}>difficulty</label>
          <select className="tech-select px-2 py-1 text-xs w-full" value={difficulty} onChange={e => onDifficultyChange(e.target.value)}>
            <option value="">(未设置)</option>
            {DIFFICULTIES.map(d => <option key={d} value={d}>{d}</option>)}
          </select>
        </div>
      </div>
    </div>
  );
}

/** 3. 标签 — 逗号分隔文本输入 */
export function TagsSection({ tagsText, onTagsTextChange }: { tagsText: string; onTagsTextChange: (v: string) => void }) {
  return (
    <div>
      <label style={labelStyle}>tags (逗号分隔)</label>
      <input type="text" className="tech-input px-2 py-1 text-xs w-full" value={tagsText} onChange={e => onTagsTextChange(e.target.value)} placeholder="tag1, tag2, ..." />
    </div>
  );
}

/** 4. 概念列表 — 只读胶囊 */
export function ConceptsSection({ concepts }: { concepts?: string[] }) {
  return (
    <div>
      <label style={labelStyle}>concepts (只读)</label>
      <div className="flex flex-wrap gap-1">
        {concepts && concepts.length > 0 ? (
          concepts.map(c => (
            <span
              key={c}
              className="px-2 py-0.5 rounded-[var(--radius-sm)] text-[10px]"
              style={{ backgroundColor: 'var(--bg-hover)', color: 'var(--color-ai)' }}
            >
              {c}
            </span>
          ))
        ) : (
          <span className="text-[10px]" style={{ color: 'var(--text-muted)' }}>(无)</span>
        )}
      </div>
    </div>
  );
}

type AnnotationSectionProps = {
  notes: ItemAnnotation[];
  noteText: string;
  noteSaving: boolean;
  onNoteTextChange: (v: string) => void;
  onAddNote: () => void;
};

/** 5. 标注 / 笔记 (P3-3) — 输入 + 已有标注列表 */
export function AnnotationSection({
  notes,
  noteText,
  noteSaving,
  onNoteTextChange,
  onAddNote,
}: AnnotationSectionProps) {
  return (
    <div>
      <label style={labelStyle}>标注 / 笔记</label>
      <div className="space-y-1.5">
        <div className="flex gap-1.5">
          <input
            type="text"
            className="tech-input px-2 py-1 text-xs w-full"
            value={noteText}
            onChange={e => onNoteTextChange(e.target.value)}
            placeholder="写一条笔记…"
            onKeyDown={e => { if (e.key === 'Enter') onAddNote(); }}
          />
          <button
            onClick={onAddNote}
            disabled={noteSaving || !noteText.trim()}
            className="btn-ghost px-2.5 py-1 text-xs shrink-0"
            style={{ color: 'var(--color-ai)', opacity: noteSaving ? 0.6 : 1 }}
          >
            {noteSaving ? '保存…' : '添加'}
          </button>
        </div>
        {notes.length > 0 ? (
          <div className="space-y-1">
            {notes.map(n => (
              <div
                key={n.id}
                className="rounded-[var(--radius-sm)] px-2 py-1.5 text-[11px]"
                style={{ backgroundColor: 'var(--bg-hover)', color: 'var(--text-primary)' }}
              >
                {n.content}
              </div>
            ))}
          </div>
        ) : (
          <span className="text-[10px]" style={{ color: 'var(--text-muted)' }}>
            (暂无标注 — 在上方输入后回车添加)
          </span>
        )}
      </div>
    </div>
  );
}

/** 6. 掌握度 — 0~100 滑块 */
export function MasterySection({ mastery, onMasteryChange }: { mastery: number; onMasteryChange: (v: number) => void }) {
  return (
    <div>
      <label style={labelStyle}>mastery: {mastery}</label>
      <input
        type="range"
        min={0}
        max={100}
        value={mastery}
        onChange={e => onMasteryChange(Number(e.target.value))}
        style={{ width: '100%', accentColor: 'var(--color-ai)' }}
      />
    </div>
  );
}

/** 6. Markdown 正文 (只读) */
export function ContentSection({ content }: { content: string }) {
  return (
    <div>
      <label style={labelStyle}>正文 (Markdown, 只读)</label>
      <pre
        className="rounded-[var(--radius-sm)] p-2.5 text-[11px] overflow-auto"
        style={{
          backgroundColor: 'var(--bg-hover)',
          color: 'var(--text-primary)',
          border: '1px solid var(--border-color)',
          maxHeight: '240px',
          whiteSpace: 'pre-wrap',
          wordBreak: 'break-word',
          margin: 0,
        }}
      >
{content || '(无正文)'}
      </pre>
    </div>
  );
}