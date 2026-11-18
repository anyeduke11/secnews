/**
 * UrlImport — URL 导入入库 (POST /api/kl/import/url), B4 从 SentinelHomePage 抽出。
 * 后端 ImportUrlRequest 只有 `url: str`, 不做 scheme 校验, 也不校验重复,
 * 所以这里必须自己挡住非 http(s) 输入, 否则会往库里造垃圾条目。
 */
import { useState } from 'react';
import { importKlUrl } from '../../../api/shared';

export function UrlImport({ onDone }: { onDone: () => void }) {
  const [open, setOpen] = useState(false);
  const [url, setUrl] = useState('');
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ kind: 'ok' | 'err'; text: string } | null>(null);

  const valid = /^https?:\/\/\S+$/i.test(url.trim());

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!valid || busy) return;
    setBusy(true);
    setMsg(null);
    try {
      // apiFetch 非 ok 抛错 → catch 显式报错 (message 为后端 detail; 原实现拼接 HTTP 状态)
      const data = await importKlUrl(url.trim());
      setMsg({ kind: 'ok', text: `已入库 ${data.id ?? ''} · kl:raw` });
      setUrl('');
      onDone();
    } catch {
      setMsg({ kind: 'err', text: '导入失败: 网络或后端不可达' });
    } finally {
      setBusy(false);
    }
  }

  return (
    <span className="sn-import">
      <button
        type="button"
        className="btn-ghost"
        aria-expanded={open}
        onClick={() => setOpen(o => !o)}
      >
        导入 URL
      </button>
      {open && (
        <form className="sn-import-form" onSubmit={submit}>
          <input
            type="url"
            className="editorial-input sn-import-input"
            placeholder="https://example.com/article"
            aria-label="待导入的文章 URL"
            value={url}
            onChange={e => { setUrl(e.target.value); setMsg(null); }}
            autoComplete="off"
          />
          <button type="submit" className="btn-primary" disabled={!valid || busy}>
            {busy ? '导入中' : '导入'}
          </button>
          <span className="sn-import-msg num" aria-live="polite">
            {msg?.text ?? (url && !valid ? '需以 http:// 或 https:// 开头' : '')}
          </span>
        </form>
      )}
    </span>
  );
}