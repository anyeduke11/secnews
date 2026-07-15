import React, { useState, useEffect, useCallback } from 'react';
import type { ContentCalendarEntry } from '../types';

const WEEKDAYS = ['日', '一', '二', '三', '四', '五', '六'];

function fmtMonth(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
}

function fmtDate(year: number, month: number, day: number): string {
  return `${year}-${String(month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
}

export function ContentCalendar() {
  const [month, setMonth] = useState(() => {
    const now = new Date();
    return new Date(now.getFullYear(), now.getMonth(), 1);
  });
  const [entries, setEntries] = useState<ContentCalendarEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedDate, setSelectedDate] = useState<string | null>(null);
  const [form, setForm] = useState({ topic: '', type: '文章', platform: '微信' });

  const loadEntries = useCallback(() => {
    setLoading(true);
    setError(null);
    fetch(`/api/content/calendar?month=${fmtMonth(month)}`)
      .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then(data => {
        setEntries(data.entries || []);
        setLoading(false);
      })
      .catch(e => {
        setError(e?.message || String(e));
        setLoading(false);
      });
  }, [month]);

  useEffect(() => {
    loadEntries();
  }, [loadEntries]);

  const handleCreate = () => {
    if (!selectedDate || !form.topic.trim()) return;
    fetch('/api/content/calendar', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        date: selectedDate,
        topic: form.topic.trim(),
        type: form.type,
        platform: form.platform,
      }),
    })
      .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then(() => {
        setForm({ topic: '', type: '文章', platform: '微信' });
        setSelectedDate(null);
        loadEntries();
      })
      .catch(e => setError(e?.message || String(e)));
  };

  const handleDelete = (id: number) => {
    fetch(`/api/content/calendar/${id}`, { method: 'DELETE' })
      .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        loadEntries();
      })
      .catch(e => setError(e?.message || String(e)));
  };

  const prevMonth = () => setMonth(new Date(month.getFullYear(), month.getMonth() - 1, 1));
  const nextMonth = () => setMonth(new Date(month.getFullYear(), month.getMonth() + 1, 1));

  const year = month.getFullYear();
  const monthIdx = month.getMonth();
  const daysInMonth = new Date(year, monthIdx + 1, 0).getDate();
  const firstWeekday = new Date(year, monthIdx, 1).getDay();

  const cells: (number | null)[] = [];
  for (let i = 0; i < firstWeekday; i++) cells.push(null);
  for (let d = 1; d <= daysInMonth; d++) cells.push(d);
  while (cells.length < 35) cells.push(null);

  const entriesByDate = new Map<string, ContentCalendarEntry[]>();
  entries.forEach(e => {
    const arr = entriesByDate.get(e.date) || [];
    arr.push(e);
    entriesByDate.set(e.date, arr);
  });

  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <button onClick={prevMonth} className="btn-ghost px-1.5 py-0.5 text-[10px]" style={{ color: 'var(--text-muted)' }}>‹</button>
        <span className="text-xs font-semibold" style={{ color: 'var(--text-primary)' }}>
          {fmtMonth(month)}
        </span>
        <button onClick={nextMonth} className="btn-ghost px-1.5 py-0.5 text-[10px]" style={{ color: 'var(--text-muted)' }}>›</button>
      </div>

      {error && (
        <p className="text-[10px] mb-1" style={{ color: '#e85d5d' }}>{error}</p>
      )}

      <div className="grid grid-cols-7 gap-0.5 mb-1">
        {WEEKDAYS.map(d => (
          <div key={d} className="text-center text-[9px]" style={{ color: 'var(--text-muted)' }}>{d}</div>
        ))}
      </div>

      <div className="grid grid-cols-7 gap-0.5">
        {cells.map((day, i) => {
          if (day === null) {
            return <div key={i} style={{ minHeight: '32px', backgroundColor: 'var(--bg-hover)', borderRadius: 'var(--radius-sm)', opacity: 0.3 }} />;
          }
          const dateStr = fmtDate(year, monthIdx, day);
          const dayEntries = entriesByDate.get(dateStr) || [];
          return (
            <div
              key={i}
              onClick={() => setSelectedDate(dateStr)}
              className="cursor-pointer p-0.5 rounded-[var(--radius-sm)]"
              style={{
                minHeight: '32px',
                backgroundColor: selectedDate === dateStr ? 'rgba(0, 188, 212, 0.15)' : 'var(--bg-hover)',
                border: selectedDate === dateStr ? '1px solid var(--color-ai)' : '1px solid transparent',
              }}
            >
              <div className="text-[9px]" style={{ color: 'var(--text-muted)' }}>{day}</div>
              {dayEntries.map(e => (
                <div
                  key={e.id}
                  onClick={(ev) => { ev.stopPropagation(); handleDelete(e.id); }}
                  className="text-[8px] truncate rounded px-0.5 mt-0.5"
                  style={{ backgroundColor: 'var(--color-ai)', color: '#fff' }}
                  title={`${e.topic} (点击删除)`}
                >
                  {e.topic}
                </div>
              ))}
            </div>
          );
        })}
      </div>

      {selectedDate && (
        <div className="mt-2 p-2 rounded-[var(--radius-sm)]" style={{ backgroundColor: 'var(--bg-hover)' }}>
          <p className="text-[10px] mb-1" style={{ color: 'var(--text-muted)' }}>新建选题: {selectedDate}</p>
          <input
            type="text"
            placeholder="选题标题"
            value={form.topic}
            onChange={e => setForm({ ...form, topic: e.target.value })}
            className="w-full mb-1 px-2 py-1 text-[10px] rounded-[var(--radius-sm)]"
            style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)', color: 'var(--text-primary)' }}
          />
          <div className="flex gap-1 mb-1">
            <select
              value={form.type}
              onChange={e => setForm({ ...form, type: e.target.value })}
              className="flex-1 px-1 py-1 text-[10px] rounded-[var(--radius-sm)]"
              style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)', color: 'var(--text-primary)' }}
            >
              <option value="文章">文章</option>
              <option value="信息图">信息图</option>
              <option value="幻灯片">幻灯片</option>
              <option value="视频">视频</option>
            </select>
            <select
              value={form.platform}
              onChange={e => setForm({ ...form, platform: e.target.value })}
              className="flex-1 px-1 py-1 text-[10px] rounded-[var(--radius-sm)]"
              style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)', color: 'var(--text-primary)' }}
            >
              <option value="微信">微信</option>
              <option value="X">X</option>
              <option value="微博">微博</option>
              <option value="小红书">小红书</option>
            </select>
          </div>
          <div className="flex gap-1">
            <button
              onClick={handleCreate}
              disabled={!form.topic.trim()}
              className="btn-ghost px-2 py-0.5 text-[10px] flex-1"
              style={{ color: 'var(--color-ai)', opacity: form.topic.trim() ? 1 : 0.5 }}
            >
              创建
            </button>
            <button
              onClick={() => setSelectedDate(null)}
              className="btn-ghost px-2 py-0.5 text-[10px]"
              style={{ color: 'var(--text-muted)' }}
            >
              取消
            </button>
          </div>
        </div>
      )}

      {loading && entries.length === 0 && (
        <p className="text-[10px] mt-1" style={{ color: 'var(--text-muted)' }}>加载中…</p>
      )}
    </div>
  );
}
