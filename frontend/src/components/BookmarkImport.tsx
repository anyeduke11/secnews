import React, { useState, useRef } from 'react';
import type { BookmarkImportResult } from '../types';

interface BookmarkImportProps {
  onImported?: () => void;
}

export function BookmarkImport({ onImported }: BookmarkImportProps) {
  const [busy, setBusy] = useState(false);
  const [validate, setValidate] = useState(false);
  const [toast, setToast] = useState<{ msg: string; ok: boolean } | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const flashToast = (msg: string, ok: boolean) => {
    setToast({ msg, ok });
    setTimeout(() => setToast(null), 3500);
  };

  const handleButtonClick = () => {
    if (busy) return;
    fileInputRef.current?.click();
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    // 重置 input value 以便同一文件可重复选择
    e.target.value = '';
    if (!file) return;

    // Phase 1i Task 9.12: 按文件类型分流（JSON 现有 / HTML 新分支）
    const isHtml =
      file.type === 'text/html' ||
      file.name.toLowerCase().endsWith('.html') ||
      file.name.toLowerCase().endsWith('.htm');

    const reader = new FileReader();
    reader.onload = () => {
      const text = String(reader.result || '');
      if (isHtml) {
        submitImport({ html: text });
      } else {
        let parsed: unknown;
        try {
          parsed = JSON.parse(text);
        } catch (err) {
          flashToast(`✗ JSON 解析失败: ${err instanceof Error ? err.message : String(err)}`, false);
          return;
        }
        submitImport({ bookmarks: parsed });
      }
    };
    reader.onerror = () => {
      flashToast('✗ 文件读取失败', false);
    };
    reader.readAsText(file);
  };

  const submitImport = (payload: { bookmarks?: unknown } | { html?: string }) => {
    setBusy(true);
    const url = new URL('/api/knowledge/bookmarks/import', window.location.origin);
    url.searchParams.set('validate', validate ? 'true' : 'false');
    fetch(url.toString(), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
      .then(async r => {
        const data = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(data?.detail || `HTTP ${r.status}`);
        return data as BookmarkImportResult;
      })
      .then(result => {
        const parts: string[] = [`导入 ${result.imported ?? 0}`];
        if (result.skipped_duplicates) parts.push(`重复 ${result.skipped_duplicates}`);
        if (result.skipped_invalid) parts.push(`无效 ${result.skipped_invalid}`);
        if (result.dead_links) parts.push(`死链 ${result.dead_links}`);
        flashToast(`✓ ${parts.join(' / ')}`, true);
        onImported?.();
      })
      .catch(e => {
        flashToast(`✗ 导入失败: ${e?.message || String(e)}`, false);
      })
      .finally(() => setBusy(false));
  };

  return (
    <div className="inline-flex items-center gap-2">
      <button
        onClick={handleButtonClick}
        disabled={busy}
        className="btn-ghost px-3 py-1.5 text-xs"
        style={{
          color: 'var(--color-ai)',
          opacity: busy ? 0.6 : 1,
          cursor: busy ? 'wait' : undefined,
        }}
        title="导入浏览器书签（支持 Chrome JSON 或 HTML 导出文件）"
        aria-label="导入书签"
      >
        {busy ? '导入中…' : '导入书签'}
      </button>

      <label
        className="inline-flex items-center gap-1 text-[10px] cursor-pointer"
        style={{ color: 'var(--text-muted)' }}
        title="勾选后会通过代理验证 URL 可达性（较慢）"
      >
        <input
          type="checkbox"
          checked={validate}
          onChange={e => setValidate(e.target.checked)}
          style={{ accentColor: 'var(--color-ai)' }}
        />
        验证 URL
      </label>

      <input
        ref={fileInputRef}
        type="file"
        accept=".json,application/json,.html,text/html,.htm"
        style={{ display: 'none' }}
        onChange={handleFileChange}
      />

      {toast && (
        <span
          className="text-[10px] px-2 py-0.5 rounded-[var(--radius-sm)]"
          style={{
            backgroundColor: 'var(--bg-hover)',
            color: toast.ok ? 'var(--color-ai)' : '#e85d5d',
          }}
        >
          {toast.msg}
        </span>
      )}
    </div>
  );
}
