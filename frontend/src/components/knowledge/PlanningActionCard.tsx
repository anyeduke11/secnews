/**
 * PlanningActionCard — 单条规划动作卡 (B5 续拆: 从 KnowledgePlanningPanel 抽出的纯展示区块)
 *
 * DOM 结构、class、内联样式与原容器内联 JSX 一致; 取数与状态更新仍由容器负责。
 */
import { Icon } from '../../primitives/Icon';
import { ACTION_CONFIG, priorityBadgeStyle, stageColor, stageLabel, type PlanningAction } from './planningModel';

// ---------------------------------------------------------------------------
// Action type icons (Lucide-style)
// ---------------------------------------------------------------------------

function ActionTypeIcon({ type }: { type: string }) {
  switch (type) {
    case 'read':
      return (
        <Icon size={13}>
          <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
          <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
        </Icon>
      );
    case 'review':
      return (
        <Icon size={13}>
          <circle cx="12" cy="12" r="3" />
          <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
        </Icon>
      );
    case 'link':
      return (
        <Icon size={13}>
          <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71" />
          <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" />
        </Icon>
      );
    case 'refine':
      return (
        <Icon size={13}>
          <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
          <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
        </Icon>
      );
    case 'publish':
      return (
        <Icon size={13}>
          <line x1="12" y1="19" x2="12" y2="5" />
          <polyline points="5 12 12 5 19 12" />
        </Icon>
      );
    default:
      return (
        <Icon size={13}>
          <circle cx="12" cy="12" r="10" />
          <line x1="12" y1="16" x2="12" y2="12" />
          <line x1="12" y1="8" x2="12.01" y2="8" />
        </Icon>
      );
  }
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

interface PlanningActionCardProps {
  action: PlanningAction;
  isUpdating: boolean;
  onUpdateStatus: (id: number, status: string) => void;
}

export function PlanningActionCard({ action, isUpdating, onUpdateStatus }: PlanningActionCardProps) {
  const cfg = ACTION_CONFIG[action.action_type] || { color: 'var(--text-muted)', label: action.action_type };

  return (
    <div
      className="rounded-md p-2.5 transition-colors duration-150"
      style={{
        backgroundColor: 'color-mix(in srgb, var(--bg-base) 50%, transparent)',
        border: '1px solid var(--border-color)',
        opacity: isUpdating ? 0.5 : 1,
      }}
    >
      <div className="flex items-start gap-2.5">
        {/* 动作类型徽章 */}
        <div
          className="w-7 h-7 rounded-md flex items-center justify-center shrink-0 mt-0.5"
          style={{
            backgroundColor: `color-mix(in srgb, ${cfg.color} 14%, transparent)`,
            color: cfg.color,
          }}
        >
          <ActionTypeIcon type={action.action_type} />
        </div>

        {/* 内容区 */}
        <div className="flex-1 min-w-0">
          {/* 标题行 */}
          <div className="flex items-center gap-1.5 flex-wrap">
            <span
              className="text-xs font-medium"
              style={{ color: 'var(--text-primary)' }}
            >
              {action.title}
            </span>
            {/* 优先级徽章 */}
            <span
              className="text-[10px] font-semibold px-1 rounded"
              style={priorityBadgeStyle(action.priority)}
            >
              P{action.priority}
            </span>
          </div>

          {/* 描述 */}
          {action.description && (
            <p
              className="text-[11px] mt-0.5 leading-relaxed"
              style={{ color: 'var(--text-secondary)' }}
            >
              {action.description}
            </p>
          )}

          {/* 阶段流转 */}
          {(action.current_stage || action.target_stage) && (
            <div className="flex items-center gap-1 mt-1.5">
              {action.current_stage && (
                <span
                  className="text-[10px] px-1.5 py-0.5 rounded"
                  style={{
                    backgroundColor: `color-mix(in srgb, ${stageColor(action.current_stage)} 12%, transparent)`,
                    color: stageColor(action.current_stage),
                  }}
                >
                  {stageLabel(action.current_stage)}
                </span>
              )}
              <span style={{ color: 'var(--text-muted)', fontSize: 10 }}>→</span>
              {action.target_stage && (
                <span
                  className="text-[10px] px-1.5 py-0.5 rounded font-medium"
                  style={{
                    backgroundColor: `color-mix(in srgb, ${stageColor(action.target_stage)} 14%, transparent)`,
                    color: stageColor(action.target_stage),
                  }}
                >
                  {stageLabel(action.target_stage)}
                </span>
              )}
            </div>
          )}
        </div>

        {/* 操作按钮 */}
        <div className="flex items-center gap-1 shrink-0">
          <button
            className="text-[11px] px-2 py-1 rounded transition-colors duration-100"
            style={{
              backgroundColor: 'color-mix(in srgb, var(--area-accent) 10%, transparent)',
              color: 'var(--area-accent)',
            }}
            disabled={isUpdating}
            onClick={() => onUpdateStatus(action.id, 'completed')}
            title="标记完成"
          >
            标记完成
          </button>
          <button
            className="text-[11px] px-2 py-1 rounded transition-colors duration-100"
            style={{
              color: 'var(--text-muted)',
            }}
            disabled={isUpdating}
            onClick={() => onUpdateStatus(action.id, 'dismissed')}
            title="忽略"
          >
            忽略
          </button>
        </div>
      </div>
    </div>
  );
}
