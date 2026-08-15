/**
 * KnowledgeCompound — 知识复利子页面
 *
 * 学习、掌握、产出:
 *  - 学习路径 (LearningPanel)
 *  - 掌握度雷达图 (MasteryGauge)
 *  - 创作日历 (ContentCalendar)
 *  - 草稿箱 (ContentDraftList)
 *  - 技能入口 (SkillEntryGrid)
 */
import React from 'react';
import { LearningPanel } from '../LearningPanel';
import { MasteryGauge } from '../MasteryGauge';
import { ContentCalendar } from '../ContentCalendar';
import { ContentDraftList } from '../ContentDraftList';
import { SkillEntryGrid } from '../SkillEntryGrid';
import { KnowledgeCompoundingDashboard } from './KnowledgeCompoundingDashboard'; // P3-5 挂载
import { KnowledgePlanningPanel } from './KnowledgePlanningPanel'; // P3-5 挂载
import { Icon } from '../Icon';
import { KNOWLEDGE_AREAS } from './KnowledgeTabs';

export function KnowledgeCompound() {
  const area = KNOWLEDGE_AREAS.find(a => a.key === 'compound')!;

  return (
    <div
      className="space-y-4"
      style={
        {
          '--area-accent': area.accentVar,
        } as React.CSSProperties
      }
      data-area-page="compound"
    >
      {/* 顶部 hero — 复利理念 */}
      <section
        className="rounded-[var(--radius-md)] p-3.5"
        style={{
          backgroundColor: 'var(--bg-elevated)',
          border: '1px solid var(--border-color)',
          borderLeft: '3px solid var(--area-accent)',
        }}
      >
        <div className="flex items-start gap-3">
          <div
            className="w-9 h-9 rounded-md flex items-center justify-center shrink-0"
            style={{
              backgroundColor: 'color-mix(in srgb, var(--area-accent) 12%, transparent)',
              color: 'var(--area-accent)',
            }}
          >
            <Icon size={18}>
              <path d="M3 17l6-6 4 4 8-8" />
              <polyline points="14 7 21 7 21 14" />
            </Icon>
          </div>
          <div className="flex-1 min-w-0">
            <h3 className="text-sm font-bold mb-0.5" style={{ color: 'var(--text-primary)' }}>
              知识复利 · 学习、掌握、产出
            </h3>
            <p className="text-xs leading-relaxed" style={{ color: 'var(--text-secondary)' }}>
              从「输入」到「产出」的价值闭环：学习路径驱动掌握度，积累到阈值后转化为创作草稿，最终发布为可复用技能。
            </p>
          </div>
        </div>
      </section>

      {/* 学习路径 + 掌握度 */}
      <section className="grid grid-cols-1 lg:grid-cols-3 gap-3">
        <div
          className="rounded-[var(--radius-md)] p-3.5 lg:col-span-2"
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
                <path d="M9 11l3 3L22 4" />
                <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11" />
              </Icon>
            </span>
            学习路径
          </h3>
          <LearningPanel />
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
                <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
              </Icon>
            </span>
            掌握度
          </h3>
          <MasteryGauge />
        </div>
      </section>

      {/* 创作日历 */}
      <section>
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
                <rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
                <line x1="16" y1="2" x2="16" y2="6" />
                <line x1="8" y1="2" x2="8" y2="6" />
                <line x1="3" y1="10" x2="21" y2="10" />
              </Icon>
            </span>
            创作日历
          </h3>
          <ContentCalendar />
        </div>
      </section>

      {/* 草稿箱 + 技能入口 */}
      <section className="grid grid-cols-1 lg:grid-cols-2 gap-3">
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
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                <polyline points="14 2 14 8 20 8" />
              </Icon>
            </span>
            草稿箱
          </h3>
          <ContentDraftList />
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
                <polyline points="16 18 22 12 16 6" />
                <polyline points="8 6 2 12 8 18" />
                <line x1="12" y1="2" x2="12" y2="22" />
              </Icon>
            </span>
            技能入口
          </h3>
          <SkillEntryGrid />
        </div>
      </section>

      {/* P3-5: 复利仪表盘 (KL 触发器健康度 + 阶段分布) + 规划动作 —
          此前两组件仅被测试引用, 文档承诺的复利入口从未挂载 */}
      <section
        className="rounded-[var(--radius-md)] p-3.5"
        style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}
      >
        <KnowledgeCompoundingDashboard />
      </section>
      <section
        className="rounded-[var(--radius-md)] p-3.5"
        style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}
      >
        <KnowledgePlanningPanel />
      </section>
    </div>
  );
}
