// frontend/src/components/codegarden/GithubImportDialog.tsx
import { useState, useEffect, CSSProperties } from 'react';
import {
  GithubImportRequest,
  GithubRepoMetadata,
  ProjectSourceType,
  ProjectType,
  SourceTypeDetail,
} from '../../types/codegarden';
import { Icon } from '../Icon';

interface GithubImportDialogProps {
  open: boolean;
  onClose: () => void;
  onImported: () => void;
  importFn: (req: GithubImportRequest) => Promise<unknown>;
}

const labelStyle: CSSProperties = {
  color: 'var(--text-muted)',
  fontSize: '10px',
  marginBottom: '2px',
  display: 'block',
};

export function GithubImportDialog({ open, onClose, onImported, importFn }: GithubImportDialogProps) {
  const [repoUrl, setRepoUrl] = useState('');
  const [localPath, setLocalPath] = useState('');
  const [sourceType, setSourceType] = useState<ProjectSourceType>('fork');
  const [sourceTypeDetail, setSourceTypeDetail] = useState<SourceTypeDetail>('trending');
  const [projectType, setProjectType] = useState<ProjectType>('web_application');
  const [tags, setTags] = useState('');
  const [techStack, setTechStack] = useState('');
  const [domain, setDomain] = useState('');
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState<{ kind: 'ok' | 'err'; msg: string } | null>(null);

  useEffect(() => {
    if (open) {
      setRepoUrl(''); setLocalPath(''); setTags(''); setTechStack(''); setDomain('');
      setSourceType('fork'); setSourceTypeDetail('trending'); setProjectType('web_application');
      setToast(null);
    }
  }, [open]);

  if (!open) return null;

  const flash = (kind: 'ok' | 'err', msg: string) => {
    setToast({ kind, msg });
    setTimeout(() => setToast(null), 3500);
  };

  const handlePreview = async () => {
    if (!repoUrl.trim()) { flash('err', '请输入 GitHub repo URL'); return; }
    try {
      const r = await fetch(`/api/codegarden/github/metadata?url=${encodeURIComponent(repoUrl.trim())}`);
      if (r.status === 424) { flash('err', '未配置 github_token'); return; }
      if (!r.ok) { flash('err', `获取元数据失败 (${r.status})`); return; }
      const data: GithubRepoMetadata = await r.json();
      // 修复 spec bug: API 实际返回 {owner, repo, description, language, ...}
      // 不存在 full_name / stars 字段
      if (data.language) setTechStack(prev => prev || data.language!);
      const desc = data.description ? ` | ${data.description.slice(0, 60)}` : '';
      flash('ok', `✓ ${data.owner}/${data.repo} | ${data.default_branch}${desc}`);
    } catch (e: any) {
      flash('err', `预览失败: ${e?.message || e}`);
    }
  };

  const handleSubmit = async () => {
    if (!repoUrl.trim()) { flash('err', '请输入 GitHub repo URL'); return; }
    setBusy(true);
    try {
      const req: GithubImportRequest = {
        repo_url: repoUrl.trim(),
        source_type: sourceType,
        source_type_detail: sourceTypeDetail,
        type: projectType,
        tags: tags.split(',').map(s => s.trim()).filter(Boolean),
        tech_stack: techStack.split(',').map(s => s.trim()).filter(Boolean),
        domain: domain.trim() || undefined,
      };
      if (localPath.trim()) req.local_path = localPath.trim();
      await importFn(req);
      flash('ok', '✓ 已导入');
      setTimeout(() => { onClose(); onImported(); }, 800);
    } catch (e: any) {
      flash('err', e?.message || String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ backgroundColor: 'var(--bg-overlay)' }}
      onClick={onClose}
    >
      <div
        className="tech-modal w-full max-w-lg p-4"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-bold flex items-center gap-2" style={{ color: 'var(--text-primary)' }}>
            <Icon size={16}>
              <path d="M9 19c-5 1.5-5-2.5-7-3m14 6v-3.87a3.37 3.37 0 0 0-.94-2.61c3.14-.35 6.44-1.54 6.44-7A5.44 5.44 0 0 0 20 4.77 5.07 5.07 0 0 0 19.91 1S18.73.65 16 2.48a13.38 13.38 0 0 0-7 0C6.27.65 5.09 1 5.09 1A5.07 5.07 0 0 0 5 4.77a5.44 5.44 0 0 0-1.5 3.78c0 5.42 3.3 6.61 6.44 7A3.37 3.37 0 0 0 9 18.13V22" />
            </Icon>
            GitHub 导入
          </h3>
          <button onClick={onClose} className="btn-ghost px-2 py-1 text-xs" aria-label="关闭">
            <Icon size={14}>
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </Icon>
          </button>
        </div>

        <div className="grid grid-cols-2 gap-2 mb-3">
          <div className="col-span-2">
            <label style={labelStyle}>Repo URL *</label>
            <div className="flex gap-1">
              <input
                className="tech-input px-2 py-1 text-xs w-full"
                placeholder="https://github.com/owner/repo"
                value={repoUrl}
                onChange={(e) => setRepoUrl(e.target.value)}
              />
              <button onClick={handlePreview} className="btn-ghost px-2 py-1 text-[10px]">预览</button>
            </div>
          </div>
          <div className="col-span-2">
            <label style={labelStyle}>Local Path (可选)</label>
            <input className="tech-input px-2 py-1 text-xs w-full" placeholder="~/code/repo" value={localPath} onChange={(e) => setLocalPath(e.target.value)} />
          </div>
          <div>
            <label style={labelStyle}>Source Type</label>
            <select className="tech-select px-2 py-1 text-xs w-full" value={sourceType} onChange={(e) => setSourceType(e.target.value as ProjectSourceType)}>
              <option value="fork">fork</option>
              <option value="imported">imported</option>
              <option value="reference">reference</option>
            </select>
          </div>
          <div>
            <label style={labelStyle}>Source Detail</label>
            <select className="tech-select px-2 py-1 text-xs w-full" value={sourceTypeDetail} onChange={(e) => setSourceTypeDetail(e.target.value as SourceTypeDetail)}>
              <option value="trending">trending</option>
              <option value="github_search">github_search</option>
              <option value="manual">manual</option>
            </select>
          </div>
          <div>
            <label style={labelStyle}>Type</label>
            <select className="tech-select px-2 py-1 text-xs w-full" value={projectType} onChange={(e) => setProjectType(e.target.value as ProjectType)}>
              <option value="web_application">web_application</option>
              <option value="api_service">api_service</option>
              <option value="cli">cli</option>
              <option value="crawler">crawler</option>
              <option value="library">library</option>
              <option value="experiment">experiment</option>
            </select>
          </div>
          <div>
            <label style={labelStyle}>Domain</label>
            <input className="tech-input px-2 py-1 text-xs w-full" placeholder="security / ai / web" value={domain} onChange={(e) => setDomain(e.target.value)} />
          </div>
          <div className="col-span-2">
            <label style={labelStyle}>Tags (逗号分隔)</label>
            <input className="tech-input px-2 py-1 text-xs w-full" placeholder="tool, automation" value={tags} onChange={(e) => setTags(e.target.value)} />
          </div>
          <div className="col-span-2">
            <label style={labelStyle}>Tech Stack (逗号分隔)</label>
            <input className="tech-input px-2 py-1 text-xs w-full" placeholder="Python, FastAPI" value={techStack} onChange={(e) => setTechStack(e.target.value)} />
          </div>
        </div>

        <div className="flex justify-end gap-2 mt-3">
          <button onClick={onClose} className="btn-ghost px-3 py-1.5 text-xs">取消</button>
          <button
            onClick={handleSubmit}
            disabled={busy}
            className="btn-ghost px-3 py-1.5 text-xs"
            style={{ color: 'var(--color-ai)', borderColor: 'var(--color-ai)' }}
          >
            {busy ? '导入中…' : '导入'}
          </button>
        </div>

        {toast && (
          <div
            className="mt-2 text-xs px-2 py-1 rounded"
            style={{
              backgroundColor: toast.kind === 'ok' ? 'color-mix(in srgb, var(--color-success) 13%, transparent)' : 'var(--color-error)20',
              color: toast.kind === 'ok' ? 'var(--color-success)' : 'var(--color-error)',
            }}
          >
            {toast.msg}
          </div>
        )}
      </div>
    </div>
  );
}
