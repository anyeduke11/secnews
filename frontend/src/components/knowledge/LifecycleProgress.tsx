/**
 * LifecycleProgress — 知识条目生命周期 5 阶段进度条
 *
 * 5 阶段: raw → refine → link → structure → publish
 * 用于展示知识条目在知识库中的加工进度。
 */
import React from 'react';

export const ALL_STAGES = ['kl:raw', 'kl:refine', 'kl:link', 'kl:structure', 'kl:publish'] as const;

export const STAGE_LABELS: Record<string, string> = {
  'kl:raw': '原始',
  'kl:refine': '精炼',
  'kl:link': '关联',
  'kl:structure': '结构化',
  'kl:publish': '发布',
};

export const STAGE_COLORS: Record<string, string> = {
  'kl:raw': '#6b7280',
  'kl:refine': '#3b82f6',
  'kl:link': '#8b5cf6',
  'kl:structure': '#f97316',
  'kl:publish': '#22c55e',
};

export interface LifecycleProgressProps {
  currentStage: string;
  stages?: readonly string[];
}

export function LifecycleProgress({ currentStage, stages = ALL_STAGES }: LifecycleProgressProps) {
  const currentIdx = stages.indexOf(currentStage);

  return (
    <div
      className="flex items-start w-full py-2"
      data-lifecycle-progress
      data-current-stage={currentStage}
    >
      {stages.map((stage, i) => {
        const isCompleted = currentIdx !== -1 && i < currentIdx;
        const isCurrent = stage === currentStage;
        const isFuture = !isCompleted && !isCurrent;
        const color = STAGE_COLORS[stage] || 'var(--text-muted)';
        const label = STAGE_LABELS[stage] || stage;

        return (
          <React.Fragment key={stage}>
            {/* 连接线（第一个节点前没有） */}
            {i > 0 && (
              <div
                className="flex-1 h-0.5 mt-3.5 mx-1 transition-colors duration-300"
                style={{
                  backgroundColor: i <= currentIdx
                    ? STAGE_COLORS[stages[i - 1]] || 'var(--text-muted)'
                    : 'var(--border-color)',
                }}
                aria-hidden="true"
              />
            )}

            {/* 节点：圆点 + 标签 */}
            <div className="flex flex-col items-center gap-1.5 min-w-0">
              {/* 圆点 */}
              <div
                className="relative flex items-center justify-center"
                style={{ width: 24, height: 24 }}
                role="img"
                aria-label={`${label}${isCurrent ? '（当前）' : ''}`}
              >
                {isCompleted && (
                  /* 已完成：实心圆 + 白色勾 */
                  <svg
                    width="24"
                    height="24"
                    viewBox="0 0 24 24"
                    fill={color}
                    aria-hidden="true"
                  >
                    <circle cx="12" cy="12" r="10" />
                    <path
                      d="M8 12l3 3 5-5"
                      stroke="white"
                      strokeWidth="2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      fill="none"
                    />
                  </svg>
                )}
                {isCurrent && (
                  /* 当前阶段：外圈光晕 + 实心圆 */
                  <svg
                    width="24"
                    height="24"
                    viewBox="0 0 24 24"
                    aria-hidden="true"
                  >
                    <circle
                      cx="12" cy="12" r="10"
                      fill={color}
                      opacity="0.15"
                    />
                    <circle
                      cx="12" cy="12" r="6"
                      fill={color}
                    />
                  </svg>
                )}
                {isFuture && (
                  /* 未来阶段：空心虚线圆 */
                  <svg
                    width="24"
                    height="24"
                    viewBox="0 0 24 24"
                    aria-hidden="true"
                  >
                    <circle
                      cx="12" cy="12" r="8"
                      fill="none"
                      stroke="var(--border-color)"
                      strokeWidth="2"
                      strokeDasharray="4 3"
                    />
                  </svg>
                )}
              </div>

              {/* 阶段标签 */}
              <span
                className="text-[10px] font-medium whitespace-nowrap px-1"
                style={{
                  color: isCompleted || isCurrent ? color : 'var(--text-muted)',
                  transition: 'color var(--duration-fast) var(--ease-out)',
                }}
              >
                {label}
              </span>
            </div>
          </React.Fragment>
        );
      })}
    </div>
  );
}