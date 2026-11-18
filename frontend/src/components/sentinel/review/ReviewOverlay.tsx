/**
 * ReviewOverlay — 复习栈页内全屏弹层 (2026-09-21 复习栈能力丰富设计稿 §4.2)
 *
 * 单弹层三视图, 页内 state 切换, 零新增路由:
 *  - session 会话视图: 翻卡 (正面=标题+类型+领域徽标, 背面=摘要 excerpt+SM-2 参数),
 *    空格翻面, 1/3/5 评分进下一张; 结束汇总页: 已评数 / 评分分布 / 每张可撤销。
 *  - data 数据视图: 7 日到期预报柱状 / 复习历史流 / 保留率 30d / 评分分布 / 在册+暂停计数。
 *  - manage 管理视图: 全部卡片表格 (暂停/恢复/删除) + 搜索加卡
 *    (GET /api/search?sources=hotspot,knowledge → POST /api/reviews/{type}/{id},
 *    type 按 search 来源映射 hotspot→hotspot, knowledge→knowledge_item)。
 *
 * 视觉: 沿用 sentinel 设计语言, ac-rv-* 命名空间 (sentinel-action.css);
 * 网络调用: 全部经 api/action.ts 强类型函数, 与 SentinelActionPage 同款。
 *
 * B5 (2026-11-18) 绞杀者拆分: 原 584 行单文件按天然边界拆为 review/ 下 4 个文件
 * (reviewModel / ReviewSessionView / ReviewDataView / ReviewManageView),
 * 本文件只保留弹层壳 (tab 切换 + Escape 关闭) 与视图组合; DOM / class / aria 逐字一致。
 */
import { useEffect } from 'react';
import '../sentinel-action.css';
import { RV_TABS, isEditableTarget, type RvView } from './reviewModel';
import { ReviewSessionView } from './ReviewSessionView';
import { ReviewDataView } from './ReviewDataView';
import { ReviewManageView } from './ReviewManageView';

export type { RvView };

/* =====================================================================
 * 弹层壳 (三视图切换 + Escape 关闭)
 * ==================================================================== */
export function ReviewOverlay({
  open,
  view,
  onViewChange,
  onClose,
  onDataChanged,
}: {
  open: boolean;
  view: RvView;
  onViewChange: (v: RvView) => void;
  onClose: () => void;
  onDataChanged: () => void;
}) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !isEditableTarget(e.target)) onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="ac-rv-backdrop" onClick={onClose}>
      <section
        className="ac-rv-modal"
        role="dialog"
        aria-modal="true"
        aria-label="复习栈工作台"
        onClick={e => e.stopPropagation()}
      >
        <header className="ac-rv-head">
          <div className="ac-rv-tabs" role="tablist" aria-label="复习栈视图">
            {RV_TABS.map(t => (
              <button
                key={t.key}
                type="button"
                role="tab"
                aria-selected={view === t.key}
                className={`ac-rv-tab${view === t.key ? ' is-active' : ''}`}
                onClick={() => onViewChange(t.key)}
              >
                {t.label}
              </button>
            ))}
          </div>
          <button type="button" className="ac-rv-close" aria-label="关闭复习栈" onClick={onClose}>
            ✕
          </button>
        </header>
        <div className="ac-rv-body">
          {view === 'session' && <ReviewSessionView onDataChanged={onDataChanged} />}
          {view === 'data' && <ReviewDataView />}
          {view === 'manage' && <ReviewManageView onDataChanged={onDataChanged} />}
        </div>
      </section>
    </div>
  );
}
