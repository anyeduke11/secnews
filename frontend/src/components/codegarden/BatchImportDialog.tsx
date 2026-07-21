// frontend/src/components/codegarden/BatchImportDialog.tsx
// Phase 1 — 项目扫描与批量导入对话框
// 支持 3 种路径源: 本地目录 / Git URL / 压缩包上传
import { useState, useEffect, useRef, CSSProperties } from 'react';
import {
  BatchScanResult,
  DetectedProject,
  ProjectType,
  ProjectSourceType,
  LifecycleStage,
  BatchImportItemRequest,
  BatchImportResult,
  BatchImportRequest,
} from '../../types/codegarden';
import { Icon } from '../Icon';

// ---------------------------------------------------------------------------
// 样式 (与现有 dialog 对齐: GitHubImportDialog / FromKnowledgeDialog)
// ---------------------------------------------------------------------------
const inputStyle: CSSProperties = {
  backgroundColor: 'var(--bg-hover)',
  border: '1px solid var(--border-color)',
  color: 'var(--text-primary)',
  borderRadius: 'var(--radius-sm)',
  padding: '4px 8px',
  fontSize: '12px',
  width: '100%',
};

const labelStyle: CSSProperties = {
  color: 'var(--text-muted)',
  fontSize: '10px',
  marginBottom: '2px',
  display: 'block',
};

const tabStyle = (active: boolean): CSSProperties => ({
  padding: '6px 12px',
  fontSize: '12px',
  borderRadius: 'var(--radius-sm)',
  cursor: 'pointer',
  backgroundColor: active ? 'var(--color-ai)' : 'transparent',
  color: active ? 'var(--text-on-light)' : 'var(--text-secondary)',
  border: '1px solid',
  borderColor: active ? 'var(--color-ai)' : 'var(--border-color)',
  fontWeight: active ? 600 : 400,
  transition: 'all var(--motion-fast) var(--motion-ease)',
});

type TabKey = 'local' | 'git' | 'archive';

interface BatchImportDialogProps {
  open: boolean;
  onClose: () => void;
  onImported: () => void;
  // 依赖注入: 从 hook 来的扫描 + 导入函数
  scanLocalFn: (path: string) => Promise<BatchScanResult>;
  scanGitFn: (url: string) => Promise<BatchScanResult>;
  scanUploadFn: (file: File) => Promise<BatchScanResult>;
  scanCleanupFn: (tempId: string) => Promise<{ cleaned: boolean }>;
  batchImportFn: (req: BatchImportRequest) => Promise<BatchImportResult>;
}

interface RowState {
  selected: boolean;
  override_name: string;
  override_type: ProjectType;
  override_lifecycle: LifecycleStage;
  override_description: string;
  override_tags: string;
}

const DEFAULT_LIFECYCLE: LifecycleStage = 'ideation';

export function BatchImportDialog({
  open,
  onClose,
  onImported,
  scanLocalFn,
  scanGitFn,
  scanUploadFn,
  scanCleanupFn,
  batchImportFn,
}: BatchImportDialogProps) {
  const [tab, setTab] = useState<TabKey>('local');

  // 输入
  const [localPath, setLocalPath] = useState('');
  const [gitUrl, setGitUrl] = useState('');
  const [archiveFile, setArchiveFile] = useState<File | null>(null);

  // 扫描状态
  const [scanning, setScanning] = useState(false);
  const [scanResult, setScanResult] = useState<BatchScanResult | null>(null);
  const [rows, setRows] = useState<Record<string, RowState>>({});

  // 导入状态
  const [importing, setImporting] = useState(false);
  const [importResult, setImportResult] = useState<BatchImportResult | null>(null);

  // 通用 toast
  const [toast, setToast] = useState<{ kind: 'ok' | 'err' | 'info'; msg: string } | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // 导入参数 (顶部全局)
  const [sourceType, setSourceType] = useState<ProjectSourceType>('imported');
  const [defaultLifecycle, setDefaultLifecycle] = useState<LifecycleStage>(DEFAULT_LIFECYCLE);

  // -------------------------------------------------------------------------
  // 重置
  // -------------------------------------------------------------------------
  useEffect(() => {
    if (open) {
      setTab('local');
      setLocalPath('');
      setGitUrl('');
      setArchiveFile(null);
      setScanResult(null);
      setRows({});
      setImportResult(null);
      setSourceType('imported');
      setDefaultLifecycle(DEFAULT_LIFECYCLE);
      setToast(null);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  }, [open]);

  if (!open) return null;

  const flash = (kind: 'ok' | 'err' | 'info', msg: string, ms = 3500) => {
    setToast({ kind, msg });
    setTimeout(() => setToast((cur) => (cur?.msg === msg ? null : cur)), ms);
  };

  // -------------------------------------------------------------------------
  // 扫描触发
  // -------------------------------------------------------------------------
  const handleScan = async () => {
    setScanning(true);
    setScanResult(null);
    setImportResult(null);
    setRows({});
    try {
      let r: BatchScanResult;
      if (tab === 'local') {
        if (!localPath.trim()) { flash('err', '请输入本地路径'); setScanning(false); return; }
        r = await scanLocalFn(localPath.trim());
      } else if (tab === 'git') {
        if (!gitUrl.trim()) { flash('err', '请输入 Git URL'); setScanning(false); return; }
        r = await scanGitFn(gitUrl.trim());
      } else {
        if (!archiveFile) { flash('err', '请选择压缩包'); setScanning(false); return; }
        r = await scanUploadFn(archiveFile);
      }
      setScanResult(r);
      // 默认全选
      const initial: Record<string, RowState> = {};
      r.detected.forEach((d) => {
        initial[d.absolute_path] = {
          selected: true,
          override_name: '',
          override_type: d.inferred_type,
          override_lifecycle: DEFAULT_LIFECYCLE,
          override_description: d.description,
          override_tags: '',
        };
      });
      setRows(initial);
      if (r.detected.length === 0) {
        flash('info', r.message || '未检测到任何项目');
      } else {
        flash('ok', `✓ ${r.message}`);
      }
    } catch (e: any) {
      flash('err', e?.message || String(e));
    } finally {
      setScanning(false);
    }
  };

  // -------------------------------------------------------------------------
  // 关闭时清理临时目录
  // -------------------------------------------------------------------------
  const handleClose = async () => {
    // 如果有未导入的 temp 目录, 主动清理
    if (scanResult?.is_temporary && scanResult.temp_id && !importResult) {
      try { await scanCleanupFn(scanResult.temp_id); } catch { /* ignore */ }
    }
    onClose();
  };

  // -------------------------------------------------------------------------
  // 行操作
  // -------------------------------------------------------------------------
  const updateRow = (key: string, patch: Partial<RowState>) => {
    setRows((cur) => ({ ...cur, [key]: { ...cur[key], ...patch } }));
  };

  const toggleAll = (selected: boolean) => {
    if (!scanResult) return;
    setRows((cur) => {
      const next: Record<string, RowState> = { ...cur };
      scanResult.detected.forEach((d) => {
        if (next[d.absolute_path]) next[d.absolute_path].selected = selected;
      });
      return next;
    });
  };

  const selectedCount = scanResult
    ? scanResult.detected.filter((d) => rows[d.absolute_path]?.selected).length
    : 0;

  // -------------------------------------------------------------------------
  // 提交批量导入
  // -------------------------------------------------------------------------
  const handleBatchImport = async () => {
    if (!scanResult) return;
    const items: BatchImportItemRequest[] = scanResult.detected
      .filter((d) => rows[d.absolute_path]?.selected)
      .map((d) => {
        const r = rows[d.absolute_path];
        const tagsArr = r.override_tags.split(',').map((s) => s.trim()).filter(Boolean);
        return {
          name: d.name,
          absolute_path: d.absolute_path,
          relative_path: d.relative_path,
          marker_file: d.marker_file,
          language: d.language,
          inferred_type: d.inferred_type,
          description: d.description,
          tech_stack: d.tech_stack,
          override_name: r.override_name || undefined,
          override_type: r.override_type,
          override_lifecycle: r.override_lifecycle,
          override_description: r.override_description || undefined,
          override_tags: tagsArr.length > 0 ? tagsArr : undefined,
        };
      });

    if (items.length === 0) {
      flash('err', '请至少勾选一个项目');
      return;
    }

    setImporting(true);
    try {
      const result = await batchImportFn({
        projects: items,
        temp_id: scanResult.temp_id || undefined,
        source_type: sourceType,
        default_lifecycle: defaultLifecycle,
      });
      setImportResult(result);
      const failTxt = result.failed_count > 0 ? `, ${result.failed_count} 个失败` : '';
      flash('ok', `✓ 导入 ${result.imported_count} 个项目${failTxt}`);
    } catch (e: any) {
      flash('err', e?.message || String(e));
    } finally {
      setImporting(false);
    }
  };

  // -------------------------------------------------------------------------
  // 渲染
  // -------------------------------------------------------------------------
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ backgroundColor: 'var(--bg-overlay)' }}
      onClick={handleClose}
    >
      <div
        className="w-full max-w-4xl rounded-[var(--radius-md)] p-4 max-h-[90vh] flex flex-col"
        style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* 标题 */}
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-base font-bold" style={{ color: 'var(--text-primary)' }}>
            批量导入项目
          </h3>
          <button onClick={handleClose} className="btn-ghost px-2 py-1 text-xs">✕</button>
        </div>

        {/* 路径源选择 — 3 tabs */}
        <div className="flex gap-2 mb-3">
          {(['local', 'git', 'archive'] as TabKey[]).map((k) => (
            <button
              key={k}
              type="button"
              onClick={() => setTab(k)}
              style={tabStyle(tab === k)}
            >
              {k === 'local' ? '本地目录' : k === 'git' ? 'Git 仓库' : '压缩包上传'}
            </button>
          ))}
        </div>

        {/* 路径输入 */}
        <div className="mb-3">
          {tab === 'local' && (
            <div>
              <label style={labelStyle}>本地绝对路径 *</label>
              <input
                style={inputStyle}
                placeholder="/Users/you/code 或 /Users/you/projects/repo-root"
                value={localPath}
                onChange={(e) => setLocalPath(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') handleScan(); }}
              />
              <div className="text-[10px] mt-1" style={{ color: 'var(--text-muted)' }}>
                扫描子目录识别项目边界 (package.json / pyproject.toml / go.mod 等)
              </div>
            </div>
          )}
          {tab === 'git' && (
            <div>
              <label style={labelStyle}>Git 仓库 URL *</label>
              <input
                style={inputStyle}
                placeholder="https://github.com/owner/repo[.git]"
                value={gitUrl}
                onChange={(e) => setGitUrl(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') handleScan(); }}
              />
              <div className="text-[10px] mt-1" style={{ color: 'var(--text-muted)' }}>
                浅克隆到临时目录, 扫描后暂存以便导入 (导入成功后自动清理)
              </div>
            </div>
          )}
          {tab === 'archive' && (
            <div>
              <label style={labelStyle}>压缩包文件 * (.zip / .tar / .tar.gz / .tgz, ≤50MB)</label>
              <input
                ref={fileInputRef}
                type="file"
                accept=".zip,.tar,.tar.gz,.tgz"
                onChange={(e) => setArchiveFile(e.target.files?.[0] || null)}
                style={{ fontSize: '12px', color: 'var(--text-primary)' }}
              />
              {archiveFile && (
                <div className="text-[10px] mt-1" style={{ color: 'var(--text-muted)' }}>
                  已选择: {archiveFile.name} ({(archiveFile.size / 1024 / 1024).toFixed(2)} MB)
                </div>
              )}
            </div>
          )}
        </div>

        {/* 全局参数 */}
        <div className="grid grid-cols-3 gap-2 mb-3">
          <div>
            <label style={labelStyle}>Source Type</label>
            <select style={inputStyle} value={sourceType} onChange={(e) => setSourceType(e.target.value as ProjectSourceType)}>
              <option value="vibe">vibe</option>
              <option value="fork">fork</option>
              <option value="imported">imported</option>
              <option value="reference">reference</option>
            </select>
          </div>
          <div>
            <label style={labelStyle}>Default Lifecycle</label>
            <select style={inputStyle} value={defaultLifecycle} onChange={(e) => setDefaultLifecycle(e.target.value as LifecycleStage)}>
              <option value="ideation">ideation</option>
              <option value="prototype">prototype</option>
              <option value="development">development</option>
              <option value="testing">testing</option>
              <option value="running">running</option>
            </select>
          </div>
          <div className="flex items-end">
            <button
              onClick={handleScan}
              disabled={scanning}
              className="btn-ghost px-3 py-1.5 text-xs w-full"
              style={{ color: 'var(--color-ai)', borderColor: 'var(--color-ai)' }}
            >
              {scanning ? '扫描中…' : '开始扫描'}
            </button>
          </div>
        </div>

        {/* 扫描结果 */}
        {scanResult && (
          <div
            className="rounded-[var(--radius-sm)] overflow-hidden flex-1 flex flex-col min-h-0"
            style={{ border: '1px solid var(--border-color)' }}
          >
            {/* 摘要 */}
            <div
              className="px-2 py-1.5 flex items-center justify-between text-[10px]"
              style={{ backgroundColor: 'var(--bg-hover)', color: 'var(--text-secondary)' }}
            >
              <span>
                源: {scanResult.source_type} · 根: <code style={{ fontSize: '10px' }}>{scanResult.scan_root}</code>
                {scanResult.is_temporary && scanResult.temp_id && (
                  <span style={{ color: 'var(--color-finance)' }}> · temp_id={scanResult.temp_id}</span>
                )}
              </span>
              <span>
                {scanResult.detected.length} 个项目
                {selectedCount !== scanResult.detected.length && (
                  <span style={{ color: 'var(--text-muted)' }}> · 已选 {selectedCount}</span>
                )}
                <button
                  onClick={() => toggleAll(true)}
                  className="ml-2 underline"
                  style={{ color: 'var(--color-ai)' }}
                >
                  全选
                </button>
                <button
                  onClick={() => toggleAll(false)}
                  className="ml-1 underline"
                  style={{ color: 'var(--text-muted)' }}
                >
                  全不选
                </button>
              </span>
            </div>

            {/* 项目列表 */}
            <div className="flex-1 overflow-y-auto" style={{ maxHeight: '46vh' }}>
              {scanResult.detected.length === 0 ? (
                <div className="text-xs text-center py-4" style={{ color: 'var(--text-muted)' }}>
                  未检测到项目 (尝试更深目录或检查 marker 文件)
                </div>
              ) : (
                <table className="w-full text-[11px]" style={{ borderCollapse: 'collapse' }}>
                  <thead style={{ position: 'sticky', top: 0, backgroundColor: 'var(--bg-card)', zIndex: 1 }}>
                    <tr style={{ borderBottom: '1px solid var(--border-color)', color: 'var(--text-muted)' }}>
                      <th style={{ width: 30, padding: '6px 4px' }}></th>
                      <th style={{ textAlign: 'left', padding: '6px 4px' }}>项目</th>
                      <th style={{ textAlign: 'left', padding: '6px 4px' }}>语言/类型</th>
                      <th style={{ textAlign: 'left', padding: '6px 4px' }}>覆盖 (可编辑)</th>
                    </tr>
                  </thead>
                  <tbody>
                    {scanResult.detected.map((d) => (
                      <BatchImportRow
                        key={d.absolute_path}
                        detected={d}
                        state={rows[d.absolute_path]}
                        onChange={(patch) => updateRow(d.absolute_path, patch)}
                      />
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </div>
        )}

        {/* 操作栏 */}
        {scanResult && scanResult.detected.length > 0 && (
          <div className="flex justify-end items-center gap-2 mt-3">
            {importResult && (
              <span className="text-[11px]" style={{ color: 'var(--color-general)' }}>
                ✓ 已导入 {importResult.imported_count} 个
                {importResult.failed_count > 0 && (
                  <span style={{ color: 'var(--color-error)' }}>, 失败 {importResult.failed_count}</span>
                )}
              </span>
            )}
            <button
              onClick={handleClose}
              className="btn-ghost px-3 py-1.5 text-xs"
            >
              {importResult ? '完成' : '取消'}
            </button>
            {!importResult && (
              <button
                onClick={handleBatchImport}
                disabled={importing || selectedCount === 0}
                className="btn-ghost px-3 py-1.5 text-xs"
                style={{ color: 'var(--color-ai)', borderColor: 'var(--color-ai)' }}
              >
                {importing ? `导入中… (0/${selectedCount})` : `批量导入 (${selectedCount})`}
              </button>
            )}
            {importResult && (
              <button
                onClick={() => { onImported(); onClose(); }}
                className="btn-ghost px-3 py-1.5 text-xs"
                style={{ color: 'var(--color-ai)', borderColor: 'var(--color-ai)' }}
              >
                刷新列表
              </button>
            )}
          </div>
        )}

        {/* 失败详情 */}
        {importResult && (importResult.failed || []).length > 0 && (
          <div
            className="mt-2 p-2 rounded text-[10px]"
            style={{ backgroundColor: 'color-mix(in srgb, var(--color-error) 8%, transparent)', border: '1px solid color-mix(in srgb, var(--color-error) 30%, transparent)' }}
          >
            <div className="font-semibold mb-1" style={{ color: 'var(--color-error)' }}>
              失败明细 ({(importResult.failed || []).length})
            </div>
            <ul className="space-y-0.5" style={{ color: 'var(--text-secondary)' }}>
              {(importResult.failed || []).map((f, i) => (
                <li key={i}>
                  · {f.name}: <span style={{ color: 'var(--color-error)' }}>{f.error}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Toast */}
        {toast && (
          <div
            className="mt-2 text-xs px-2 py-1 rounded"
            style={{
              backgroundColor:
                toast.kind === 'ok' ? 'color-mix(in srgb, var(--color-success) 13%, transparent)' :
                toast.kind === 'err' ? 'var(--color-error)20' : 'color-mix(in srgb, var(--color-info) 12%, transparent)',
              color:
                toast.kind === 'ok' ? 'var(--color-success)' :
                toast.kind === 'err' ? 'var(--color-error)' : 'var(--color-ai)',
            }}
          >
            {toast.msg}
          </div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// 单行组件 (提取出来避免主函数过长)
// ---------------------------------------------------------------------------
interface BatchImportRowProps {
  detected: DetectedProject;
  state: RowState;
  onChange: (patch: Partial<RowState>) => void;
}

function BatchImportRow({ detected, state, onChange }: BatchImportRowProps) {
  const [expanded, setExpanded] = useState(false);
  if (!state) return null;

  return (
    <>
      <tr style={{ borderBottom: '1px solid var(--border-color)' }}>
        <td style={{ textAlign: 'center', padding: '6px 4px' }}>
          <input
            type="checkbox"
            checked={state.selected}
            onChange={(e) => onChange({ selected: e.target.checked })}
          />
        </td>
        <td style={{ padding: '6px 4px' }}>
          <div style={{ color: 'var(--text-primary)', fontWeight: 500 }}>
            {detected.name}
          </div>
          <div className="text-[10px]" style={{ color: 'var(--text-muted)' }} title={detected.absolute_path}>
            {detected.relative_path} · {detected.marker_file}
          </div>
          {detected.description && (
            <div className="text-[10px] mt-0.5" style={{ color: 'var(--text-secondary)' }}>
              {detected.description.slice(0, 100)}
            </div>
          )}
        </td>
        <td style={{ padding: '6px 4px' }}>
          <div className="text-[10px]" style={{ color: 'var(--color-ai)' }}>
            {detected.language}
          </div>
          <div className="text-[10px]" style={{ color: 'var(--text-muted)' }}>
            {detected.inferred_type}
          </div>
          {detected.tech_stack.length > 0 && (
            <div className="text-[10px]" style={{ color: 'var(--text-muted)' }}>
              {detected.tech_stack.slice(0, 4).join(', ')}
            </div>
          )}
        </td>
        <td style={{ padding: '6px 4px' }}>
          <div className="flex gap-1 items-center">
            <input
              style={{ ...inputStyle, width: 100 }}
              placeholder="name"
              value={state.override_name}
              onChange={(e) => onChange({ override_name: e.target.value })}
            />
            <select
              style={{ ...inputStyle, width: 110 }}
              value={state.override_type}
              onChange={(e) => onChange({ override_type: e.target.value as ProjectType })}
            >
              <option value="web_application">web_application</option>
              <option value="api_service">api_service</option>
              <option value="cli">cli</option>
              <option value="crawler">crawler</option>
              <option value="library">library</option>
              <option value="experiment">experiment</option>
            </select>
            <button
              type="button"
              onClick={() => setExpanded(!expanded)}
              className="btn-ghost px-2 py-0.5 text-[10px]"
            >
              {expanded ? '收起' : '更多'}
            </button>
          </div>
          {expanded && (
            <div className="mt-1 space-y-1">
              <div className="flex gap-1 items-center">
                <label style={{ ...labelStyle, marginBottom: 0, minWidth: 60 }}>lifecycle</label>
                <select
                  style={{ ...inputStyle, width: 130 }}
                  value={state.override_lifecycle}
                  onChange={(e) => onChange({ override_lifecycle: e.target.value as LifecycleStage })}
                >
                  <option value="ideation">ideation</option>
                  <option value="prototype">prototype</option>
                  <option value="development">development</option>
                  <option value="testing">testing</option>
                  <option value="running">running</option>
                  <option value="maintenance">maintenance</option>
                </select>
              </div>
              <input
                style={{ ...inputStyle, fontSize: '10px' }}
                placeholder="tags (逗号分隔, 覆盖默认)"
                value={state.override_tags}
                onChange={(e) => onChange({ override_tags: e.target.value })}
              />
              <input
                style={{ ...inputStyle, fontSize: '10px' }}
                placeholder="description 覆盖"
                value={state.override_description}
                onChange={(e) => onChange({ override_description: e.target.value })}
              />
            </div>
          )}
        </td>
      </tr>
    </>
  );
}
