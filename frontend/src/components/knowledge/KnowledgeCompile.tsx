/**
 * KnowledgeCompile — 知识库编译子页面
 *
 * LLM 提炼与运维:
 *  - 编译触发 (CompileTrigger, 带预览确认)
 *  - 任务监控 (TaskMonitor, 实时状态)
 *  - 手动提交任务 (TaskSubmitDialog)
 *  - SOUL 角色画像 (SoulViewer)
 *  - 健康度 (HealthDashboard)
 *  - 联邦状态 (FederationStatus)
 */
import React, { useState } from 'react';
import { CompileTrigger } from '../CompileTrigger';
import { TaskMonitor } from '../TaskMonitor';
import { TaskSubmitDialog } from '../TaskSubmitDialog';
import { SoulViewer } from '../SoulViewer';
import { HealthDashboard } from '../HealthDashboard';
import { FederationStatus } from '../FederationStatus';
import { Icon } from '../Icon';
import { KNOWLEDGE_AREAS } from './KnowledgeTabs';

export function KnowledgeCompile() {
  const [taskRefreshKey, setTaskRefreshKey] = useState(0);
  const [taskDialogOpen, setTaskDialogOpen] = useState(false);
  const area = KNOWLEDGE_AREAS.find(a => a.key === 'compile')!;

  return (
    <div
      className="space-y-4"
      style={
        {
          '--area-accent': area.accentVar,
        } as React.CSSProperties
      }
      data-area-page="compile"
    >
      {/* 顶部操作区: 编译 + 提交任务 */}
      <section
        className="rounded-[var(--radius-md)] p-3.5"
        style={{
          backgroundColor: 'var(--bg-elevated)',
          border: '1px solid var(--border-color)',
          borderLeft: '3px solid var(--area-accent)',
        }}
      >
        <div className="flex items-start gap-3 mb-3">
          <div
            className="w-9 h-9 rounded-md flex items-center justify-center shrink-0"
            style={{
              backgroundColor: 'color-mix(in srgb, var(--area-accent) 12%, transparent)',
              color: 'var(--area-accent)',
            }}
          >
            <Icon size={18}>
              <polyline points="16 18 22 12 16 6" />
              <polyline points="8 6 2 12 8 18" />
            </Icon>
          </div>
          <div className="flex-1 min-w-0">
            <h3 className="text-sm font-bold mb-0.5" style={{ color: 'var(--text-primary)' }}>
              知识库编译 · LLM 提炼
            </h3>
            <p className="text-xs leading-relaxed" style={{ color: 'var(--text-secondary)' }}>
              触发 LLM 编译任务，提取概念、生成摘要、归一化标签。所有任务在后台队列异步执行。
            </p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <CompileTrigger onTaskCreated={() => setTaskRefreshKey(k => k + 1)} />
          <button
            onClick={() => setTaskDialogOpen(true)}
            className="btn-ghost px-3 py-1.5 text-xs"
            style={{ color: 'var(--area-accent)' }}
          >
            <span className="flex items-center gap-1.5">
              <Icon size={12}>
                <line x1="12" y1="5" x2="12" y2="19" />
                <line x1="5" y1="12" x2="19" y2="12" />
              </Icon>
              提交任务
            </span>
          </button>
        </div>
      </section>

      {/* 任务监控 */}
      <section>
        <h3
          className="text-sm font-semibold flex items-center gap-2 mb-2"
          style={{ color: 'var(--text-primary)' }}
        >
          <span
            className="w-5 h-5 rounded-sm flex items-center justify-center"
            style={{
              backgroundColor: 'color-mix(in srgb, var(--area-accent) 14%, transparent)',
              color: 'var(--area-accent)',
            }}
          >
            <Icon size={11}>
              <rect x="3" y="3" width="7" height="7" />
              <rect x="14" y="3" width="7" height="7" />
              <rect x="14" y="14" width="7" height="7" />
              <rect x="3" y="14" width="7" height="7" />
            </Icon>
          </span>
          任务监控
        </h3>
        <TaskMonitor refreshKey={taskRefreshKey} />
      </section>

      {/* SOUL 角色画像 + 健康度 + 联邦状态 三栏 */}
      <section className="grid grid-cols-1 lg:grid-cols-3 gap-3">
        <div
          className="rounded-[var(--radius-md)] p-3.5"
          style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}
        >
          <h3
            className="text-sm font-semibold flex items-center gap-2 mb-2"
            style={{ color: 'var(--text-primary)' }}
          >
            <span
              className="w-5 h-5 rounded-sm flex items-center justify-center"
              style={{
                backgroundColor: 'color-mix(in srgb, var(--area-accent) 14%, transparent)',
                color: 'var(--area-accent)',
              }}
            >
              <Icon size={11}>
                <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
                <circle cx="12" cy="7" r="4" />
              </Icon>
            </span>
            角色画像
          </h3>
          <SoulViewer />
        </div>

        <div
          className="rounded-[var(--radius-md)] p-3.5"
          style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}
        >
          <h3
            className="text-sm font-semibold flex items-center gap-2 mb-2"
            style={{ color: 'var(--text-primary)' }}
          >
            <span
              className="w-5 h-5 rounded-sm flex items-center justify-center"
              style={{
                backgroundColor: 'color-mix(in srgb, var(--area-accent) 14%, transparent)',
                color: 'var(--area-accent)',
              }}
            >
              <Icon size={11}>
                <path d="M22 12h-4l-3 9L9 3l-3 9H2" />
              </Icon>
            </span>
            健康度
          </h3>
          <HealthDashboard />
        </div>

        <div
          className="rounded-[var(--radius-md)] p-3.5"
          style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}
        >
          <h3
            className="text-sm font-semibold flex items-center gap-2 mb-2"
            style={{ color: 'var(--text-primary)' }}
          >
            <span
              className="w-5 h-5 rounded-sm flex items-center justify-center"
              style={{
                backgroundColor: 'color-mix(in srgb, var(--area-accent) 14%, transparent)',
                color: 'var(--area-accent)',
              }}
            >
              <Icon size={11}>
                <circle cx="12" cy="12" r="10" />
                <line x1="2" y1="12" x2="22" y2="12" />
                <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
              </Icon>
            </span>
            联邦状态
          </h3>
          <FederationStatus />
        </div>
      </section>

      <TaskSubmitDialog
        open={taskDialogOpen}
        onClose={() => setTaskDialogOpen(false)}
        onSubmitted={() => setTaskRefreshKey(k => k + 1)}
      />
    </div>
  );
}
