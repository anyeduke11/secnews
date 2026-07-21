// frontend/src/components/CodegardenPage.tsx
// Phase 4: 错误态用 --color-error, Loading/Empty/Error 走 EmptyState 原子组件。
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useCodegardenProjects } from '../hooks/useCodegardenProjects';
import { ProjectBoard } from './codegarden/ProjectBoard';
import { ProjectDetail } from './codegarden/ProjectDetail';
import { GithubImportDialog } from './codegarden/GithubImportDialog';
import { FromKnowledgeDialog } from './codegarden/FromKnowledgeDialog';
import { CgProject, LifecycleStage, ProjectSourceType, ProjectType } from '../types/codegarden';
import { Icon } from './Icon';
import { EmptyState } from './EmptyState';

interface CodegardenPageProps {
  onBack: () => void;
}

export function CodegardenPage({ onBack }: CodegardenPageProps) {
  const navigate = useNavigate();
  const {
    items, total, loading, error,
    lifecycle, sourceType, projectType, keyword,
    setLifecycle, setSourceType, setProjectType, setKeyword,
    refresh, transition, syncUpstream,
    importFromGithub, importFromKnowledge, listCandidates,
  } = useCodegardenProjects();

  const [selected, setSelected] = useState<CgProject | null>(null);
  const [githubOpen, setGithubOpen] = useState(false);
  const [knowledgeOpen, setKnowledgeOpen] = useState(false);

  return (
    <div className="codegarden-page">
      {/* 顶部标题区 */}
      <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
        <div className="flex items-center gap-3">
          <button
            onClick={onBack}
            className="btn-ghost px-2.5 py-1.5 text-xs"
            title="返回首页"
            aria-label="返回首页"
          >
            <Icon>
              <line x1="19" y1="12" x2="5" y2="12" />
              <polyline points="12 19 5 12 12 5" />
            </Icon>
            返回首页
          </button>
          <h2 className="text-base font-bold" style={{ color: 'var(--text-primary)' }}>
            🌱 CodeGarden
          </h2>
          <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
            vibecoding 工作台 + 二开项目管理
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs" style={{ color: 'var(--text-muted)' }}>共 {total} 项</span>
          <button
            onClick={() => navigate('/codegarden/phase2b')}
            className="btn-ghost px-3 py-1.5 text-xs"
            title="Service Mesh / Resource Hub / Orchestration Engine"
            style={{ color: 'var(--color-ai)', border: '1px solid var(--color-ai)' }}
          >
            🌐 Phase 2b
          </button>
          <button
            onClick={() => setKnowledgeOpen(true)}
            className="btn-ghost px-3 py-1.5 text-xs"
            style={{ color: 'var(--color-ai)' }}
          >
            + 从知识库
          </button>
          <button
            onClick={() => setGithubOpen(true)}
            className="btn-ghost px-3 py-1.5 text-xs"
            style={{ color: 'var(--color-ai)' }}
          >
            + GitHub 导入
          </button>
          <button
            onClick={refresh}
            className="btn-ghost px-2 py-1.5 text-xs"
            title="刷新"
          >
            <Icon>
              <polyline points="23 4 23 10 17 10" />
              <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
            </Icon>
          </button>
        </div>
      </div>

      {/* 过滤器 */}
      <div className="flex items-center gap-2 mb-3 flex-wrap">
        <select
          value={lifecycle}
          onChange={(e) => setLifecycle(e.target.value as LifecycleStage | 'all')}
          className="text-[11px] px-2 py-1 rounded"
          style={{ backgroundColor: 'var(--bg-hover)', color: 'var(--text-primary)', border: '1px solid var(--border-color)' }}
        >
          <option value="all">全部状态</option>
          <option value="ideation">构想中</option>
          <option value="prototype">原型</option>
          <option value="development">开发中</option>
          <option value="testing">测试中</option>
          <option value="running">运行中</option>
          <option value="maintenance">维护中</option>
          <option value="archived">已归档</option>
          <option value="deprecated">已废弃</option>
        </select>
        <select
          value={sourceType}
          onChange={(e) => setSourceType(e.target.value as ProjectSourceType | 'all')}
          className="text-[11px] px-2 py-1 rounded"
          style={{ backgroundColor: 'var(--bg-hover)', color: 'var(--text-primary)', border: '1px solid var(--border-color)' }}
        >
          <option value="all">全部来源</option>
          <option value="vibe">原创</option>
          <option value="fork">Fork</option>
          <option value="imported">导入</option>
          <option value="reference">参考</option>
        </select>
        <select
          value={projectType}
          onChange={(e) => setProjectType(e.target.value as ProjectType | 'all')}
          className="text-[11px] px-2 py-1 rounded"
          style={{ backgroundColor: 'var(--bg-hover)', color: 'var(--text-primary)', border: '1px solid var(--border-color)' }}
        >
          <option value="all">全部类型</option>
          <option value="web_application">web_application</option>
          <option value="api_service">api_service</option>
          <option value="cli">cli</option>
          <option value="crawler">crawler</option>
          <option value="library">library</option>
          <option value="experiment">experiment</option>
        </select>
        <input
          value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
          placeholder="搜索 name / description"
          className="text-[11px] px-2 py-1 rounded flex-1 min-w-[180px]"
          style={{ backgroundColor: 'var(--bg-hover)', color: 'var(--text-primary)', border: '1px solid var(--border-color)' }}
        />
      </div>

      {/* 看板 */}
      {loading ? (
        <p className="text-xs text-center py-6" style={{ color: 'var(--text-muted)' }}>
          加载中…
        </p>
      ) : error ? (
        <div
          className="rounded-[var(--radius-md)] p-2.5 text-xs"
          style={{
            backgroundColor: 'color-mix(in srgb, var(--color-error) 12%, transparent)',
            border: '1px solid var(--color-error)',
            color: 'var(--color-error)',
          }}
        >
          加载失败: {error}
        </div>
      ) : items.length === 0 ? (
        <EmptyState
          title="暂无项目"
          description="点击右上角 + 添加，或从 GitHub / 知识库导入"
        />
      ) : (
        <ProjectBoard
          items={items}
          onSelect={setSelected}
          onTransition={(id, to) => transition(id, to).catch(e => window.alert(e?.message || e))}
        />
      )}

      {/* 详情弹窗 */}
      {selected && (
        <ProjectDetail
          project={selected}
          onClose={() => setSelected(null)}
          onTransition={transition}
          onSync={syncUpstream}
        />
      )}

      {/* GitHub 导入弹窗 */}
      <GithubImportDialog
        open={githubOpen}
        onClose={() => setGithubOpen(false)}
        onImported={refresh}
        importFn={importFromGithub}
      />

      {/* 从知识库导入弹窗 */}
      <FromKnowledgeDialog
        open={knowledgeOpen}
        onClose={() => setKnowledgeOpen(false)}
        onImported={refresh}
        listCandidates={listCandidates}
        importFn={importFromKnowledge}
      />
    </div>
  );
}
