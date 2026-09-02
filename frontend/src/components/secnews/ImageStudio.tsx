/**
 * ImageStudio — 文生图 + 图理解 工具页 (v0.7.4-image).
 *
 * - 文生图: textarea → POST /api/image/generate → <img> 预览 + 下载链接
 * - 图理解: 上传 → POST /api/image/understand → 文本框显示
 * - 两个动作都显示 provider / model / latency_ms 角标
 */
import { useState, useCallback } from 'react';

interface ImageGenResponse {
  ok: boolean;
  images?: Array<{ url?: string; b64_json?: string }>;
  provider?: string;
  model?: string;
  latency_ms?: number;
  error?: string;
}

interface UnderstandResponse {
  ok: boolean;
  text?: string;
  provider?: string;
  model?: string;
  latency_ms?: number;
  error?: string;
}

const SIZES = ['512x512', '768x768', '1024x1024', '1280x720'];

async function fileToB64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => {
      const result = r.result as string;
      // data:image/png;base64,XXX — 去掉前缀
      const idx = result.indexOf(',');
      resolve(idx >= 0 ? result.slice(idx + 1) : result);
    };
    r.onerror = reject;
    r.readAsDataURL(file);
  });
}

export function ImageStudio() {
  // 文生图状态
  const [prompt, setPrompt] = useState('');
  const [size, setSize] = useState('1024x1024');
  const [n, setN] = useState(1);
  const [watermark, setWatermark] = useState(false);
  const [genResult, setGenResult] = useState<ImageGenResponse | null>(null);
  const [genBusy, setGenBusy] = useState(false);
  const [genError, setGenError] = useState<string | null>(null);

  // 图理解状态
  const [understandFile, setUnderstandFile] = useState<File | null>(null);
  const [understandPrompt, setUnderstandPrompt] = useState('');
  const [understandResult, setUnderstandResult] = useState<UnderstandResponse | null>(null);
  const [understandBusy, setUnderstandBusy] = useState(false);
  const [understandError, setUnderstandError] = useState<string | null>(null);

  const handleGenerate = useCallback(async () => {
    if (!prompt.trim()) return;
    setGenBusy(true);
    setGenError(null);
    setGenResult(null);
    try {
      const r = await fetch('/api/image/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt, size, n, watermark, actor: 'web' }),
      });
      const d = await r.json();
      setGenResult(d);
      if (!d.ok) {
        setGenError(d.error || '生成失败');
      }
    } catch (e) {
      setGenError('网络错误');
      setGenResult({ ok: false, error: '网络错误' });
    } finally {
      setGenBusy(false);
    }
  }, [prompt, size, n, watermark]);

  const handleUnderstand = useCallback(async () => {
    if (!understandFile || !understandPrompt.trim()) return;
    setUnderstandBusy(true);
    setUnderstandError(null);
    setUnderstandResult(null);
    try {
      const b64 = await fileToB64(understandFile);
      const r = await fetch('/api/image/understand', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ image_b64: b64, prompt: understandPrompt, actor: 'web' }),
      });
      const d = await r.json();
      setUnderstandResult(d);
      if (!d.ok) {
        setUnderstandError(d.error || '理解失败');
      }
    } catch (e) {
      setUnderstandError('网络错误');
      setUnderstandResult({ ok: false, error: '网络错误' });
    } finally {
      setUnderstandBusy(false);
    }
  }, [understandFile, understandPrompt]);

  return (
    <div className="space-y-4">
      {/* 文生图 */}
      <section
        className="p-3 rounded"
        style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}
      >
        <h3 className="text-xs font-mono font-semibold mb-2" style={{ color: 'var(--text-primary)' }}>
          🎨 文生图 (sensenova-u1.5-lite)
        </h3>
        <textarea
          value={prompt}
          onChange={e => setPrompt(e.target.value)}
          placeholder="描述要生成的图片..."
          rows={3}
          data-testid="image-gen-prompt"
          className="w-full px-2 py-1 text-xs rounded"
          style={{ backgroundColor: 'var(--bg-hover)', border: '1px solid var(--border-color)', color: 'var(--text-primary)' }}
        />
        <div className="flex items-center gap-2 mt-2 flex-wrap">
          <label className="text-[11px]" style={{ color: 'var(--text-secondary)' }}>尺寸</label>
          <select
            value={size}
            onChange={e => setSize(e.target.value)}
            data-testid="image-gen-size"
            className="text-xs px-2 py-1 rounded"
            style={{ backgroundColor: 'var(--bg-hover)', border: '1px solid var(--border-color)', color: 'var(--text-primary)' }}
          >
            {SIZES.map(s => <option key={s} value={s}>{s}</option>)}
          </select>
          <label className="text-[11px] flex items-center gap-1" style={{ color: 'var(--text-secondary)' }}>
            n
            <input
              type="number"
              min={1}
              max={4}
              value={n}
              onChange={e => setN(Math.max(1, Math.min(4, parseInt(e.target.value) || 1)))}
              data-testid="image-gen-n"
              className="w-12 px-1 py-0.5 text-xs rounded"
              style={{ backgroundColor: 'var(--bg-hover)', border: '1px solid var(--border-color)', color: 'var(--text-primary)' }}
            />
          </label>
          <label className="text-[11px] flex items-center gap-1" style={{ color: 'var(--text-secondary)' }}>
            <input
              type="checkbox"
              checked={watermark}
              onChange={e => setWatermark(e.target.checked)}
              data-testid="image-gen-watermark"
            />
            watermark (true 才计费)
          </label>
          <button
            onClick={handleGenerate}
            disabled={genBusy || !prompt.trim()}
            data-testid="image-gen-submit"
            className="ml-auto px-3 py-1 text-[11px] rounded"
            style={{
              backgroundColor: 'var(--color-general)',
              color: 'var(--text-on-color)',
              opacity: (genBusy || !prompt.trim()) ? 0.6 : 1,
              border: 'none',
            }}
          >
            {genBusy ? '生成中...' : '生成'}
          </button>
        </div>
        {genResult?.ok && (
          <div className="mt-2" data-testid="image-gen-result">
            <div className="text-[10px] mb-2" style={{ color: 'var(--text-muted)' }}>
              {genResult.provider} · {genResult.model} · {genResult.latency_ms}ms
            </div>
            <div className="grid grid-cols-2 gap-2">
              {(genResult.images || []).map((img, i) => (
                <div key={i}>
                  {img.url && <img src={img.url} alt="" className="w-full rounded" />}
                  {img.b64_json && (
                    <img
                      src={`data:image/png;base64,${img.b64_json}`}
                      alt=""
                      className="w-full rounded"
                    />
                  )}
                </div>
              ))}
            </div>
          </div>
        )}
        {genError && (
          <p
            className="text-[11px] mt-2"
            data-testid="image-gen-error"
            style={{ color: 'var(--color-error)' }}
          >
            {genError}
          </p>
        )}
      </section>

      {/* 图理解 */}
      <section
        className="p-3 rounded"
        style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}
      >
        <h3 className="text-xs font-mono font-semibold mb-2" style={{ color: 'var(--text-primary)' }}>
          🔍 图理解 (多模态)
        </h3>
        <input
          type="file"
          accept="image/*"
          onChange={e => setUnderstandFile(e.target.files?.[0] ?? null)}
          data-testid="image-und-file"
          className="text-xs mb-2"
        />
        <textarea
          value={understandPrompt}
          onChange={e => setUnderstandPrompt(e.target.value)}
          placeholder="要问图片什么..."
          rows={2}
          data-testid="image-und-prompt"
          className="w-full px-2 py-1 text-xs rounded"
          style={{ backgroundColor: 'var(--bg-hover)', border: '1px solid var(--border-color)', color: 'var(--text-primary)' }}
        />
        <button
          onClick={handleUnderstand}
          disabled={understandBusy || !understandFile || !understandPrompt.trim()}
          data-testid="image-und-submit"
          className="px-3 py-1 text-[11px] rounded"
          style={{
            backgroundColor: 'var(--color-general)',
            color: 'var(--text-on-color)',
            opacity: (understandBusy || !understandFile || !understandPrompt.trim()) ? 0.6 : 1,
            border: 'none',
          }}
        >
          {understandBusy ? '理解中...' : '理解'}
        </button>
        {understandResult?.ok && (
          <div className="mt-2" data-testid="image-und-result">
            <div className="text-[10px] mb-1" style={{ color: 'var(--text-muted)' }}>
              {understandResult.provider} · {understandResult.model} · {understandResult.latency_ms}ms
            </div>
            <pre
              className="text-xs p-2 rounded whitespace-pre-wrap"
              data-testid="image-und-text"
              style={{ backgroundColor: 'var(--bg-hover)', color: 'var(--text-primary)' }}
            >
              {understandResult.text}
            </pre>
          </div>
        )}
        {understandError && (
          <p
            className="text-[11px] mt-2"
            data-testid="image-und-error"
            style={{ color: 'var(--color-error)' }}
          >
            {understandError}
          </p>
        )}
      </section>
    </div>
  );
}

export default ImageStudio;
