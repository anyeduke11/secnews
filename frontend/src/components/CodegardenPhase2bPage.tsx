// frontend/src/components/CodegardenPhase2bPage.tsx
// Phase 2b 主页 — Service Mesh + Resource Hub + Orchestration Engine
// 三个 tab：M2 服务网格 / M3 资源中枢 / M4 联动引擎（含子 tab：依赖图谱/事件流/Playbook）
import { useState } from 'react';
import { ServiceMesh } from './codegarden/service-mesh';
import { ServiceTopology } from './codegarden/ServiceTopology';
import { ResourceHub } from './codegarden/resource-hub';
import { DependencyGraph } from './codegarden/dependency-graph';
import { EventBus } from './codegarden/EventBus';
import { PlaybookList } from './codegarden/PlaybookList';
import { useCodegardenServices } from '../hooks/useCodegardenServices';
import { Icon } from './Icon';

type MainTab = 'services' | 'resources' | 'orchestration';
type OrchestrationTab = 'dependencies' | 'events' | 'playbooks';

interface CodegardenPhase2bPageProps {
  onBack: () => void;
}

export function CodegardenPhase2bPage({ onBack }: CodegardenPhase2bPageProps) {
  const [mainTab, setMainTab] = useState<MainTab>('services');
  const [orchTab, setOrchTab] = useState<OrchestrationTab>('dependencies');
  const [showTopology, setShowTopology] = useState(false);

  // ServiceMesh 内部已有自己的 hook，这里只为 ServiceTopology 单独取数据
  const topologyHook = useCodegardenServices();

  return (
    <div className="codegarden-phase2b-page">
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
            🌐 CodeGarden Phase 2b
          </h2>
          <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
            服务网格 · 资源中枢 · 联动引擎
          </span>
        </div>
      </div>

      {/* 主 tab */}
      <div className="flex items-center gap-1 mb-3 border-b" style={{ borderColor: 'var(--border-color)' }}>
        <MainTabButton active={mainTab === 'services'} onClick={() => setMainTab('services')}>
          M2 服务网格
        </MainTabButton>
        <MainTabButton active={mainTab === 'resources'} onClick={() => setMainTab('resources')}>
          M3 资源中枢
        </MainTabButton>
        <MainTabButton active={mainTab === 'orchestration'} onClick={() => setMainTab('orchestration')}>
          M4 联动引擎
        </MainTabButton>
      </div>

      {/* 内容区 */}
      {mainTab === 'services' && (
        <>
          {showTopology ? (
            <ServiceTopology fetchTopology={topologyHook.getTopology} onClose={() => setShowTopology(false)} />
          ) : (
            <ServiceMesh onShowTopology={() => setShowTopology(true)} />
          )}
        </>
      )}

      {mainTab === 'resources' && <ResourceHub />}

      {mainTab === 'orchestration' && (
        <>
          <div className="flex items-center gap-1 mb-3">
            <SubTabButton active={orchTab === 'dependencies'} onClick={() => setOrchTab('dependencies')}>
              依赖图谱
            </SubTabButton>
            <SubTabButton active={orchTab === 'events'} onClick={() => setOrchTab('events')}>
              事件流
            </SubTabButton>
            <SubTabButton active={orchTab === 'playbooks'} onClick={() => setOrchTab('playbooks')}>
              Playbook
            </SubTabButton>
          </div>
          {orchTab === 'dependencies' && <DependencyGraph />}
          {orchTab === 'events' && <EventBus />}
          {orchTab === 'playbooks' && <PlaybookList />}
        </>
      )}
    </div>
  );
}

function MainTabButton({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      className="px-3 py-1.5 text-xs"
      style={{
        color: active ? 'var(--color-ai)' : 'var(--text-secondary)',
        borderBottom: active ? '2px solid var(--color-ai)' : '2px solid transparent',
        fontWeight: active ? 600 : 400,
      }}
    >
      {children}
    </button>
  );
}

function SubTabButton({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      className="px-2.5 py-1 text-[11px] rounded"
      style={{
        color: active ? 'var(--color-ai)' : 'var(--text-secondary)',
        backgroundColor: active ? 'var(--bg-hover)' : 'transparent',
        border: `1px solid ${active ? 'var(--color-ai)' : 'var(--border-color)'}`,
      }}
    >
      {children}
    </button>
  );
}
