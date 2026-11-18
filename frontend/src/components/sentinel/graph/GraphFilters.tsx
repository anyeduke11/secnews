/**
 * GraphFilters — 知识图谱页的域过滤条 + 画布模式开关 + 回首页 (B5 从 SentinelGraphPage 抽出)
 *
 * 纯展示: 状态与回调全部由容器传入; DOM / class / aria-pressed 与拆分前逐字一致。
 * 「画布模式」开关的 canvasMode 状态留在容器 (Phase 5 DEV-0184 守卫口径)。
 */
import type { Dispatch, SetStateAction } from 'react';
import { domainFill, domainLabel } from './graphModel';

export function GraphFilters({ domain, domainChips, total, hiddenCount, canvasMode, onDomainChange, onShowHidden, onToggleCanvas, onNavigate }: {
  domain: string;
  domainChips: [string, number][];
  total: number;
  hiddenCount: number;
  canvasMode: boolean;
  onDomainChange: Dispatch<SetStateAction<string>>;
  onShowHidden: () => void;
  onToggleCanvas: () => void;
  onNavigate: (to: string) => void;
}) {
  return (
    <div className="kg-filters" role="group" aria-label="按知识域过滤节点">
      <button
        type="button"
        className={`kg-chip${domain === 'all' ? ' is-on' : ''}`}
        aria-pressed={domain === 'all'}
        onClick={() => onDomainChange('all')}
      >
        全部 <span className="num">{total}</span>
      </button>
      {domainChips.map(([d, c]) => (
        <button
          key={d}
          type="button"
          className={`kg-chip${domain === d ? ' is-on' : ''}`}
          aria-pressed={domain === d}
          onClick={() => onDomainChange(cur => (cur === d ? 'all' : d))}
        >
          <i className={`kg-dot ${domainFill(d)}`} aria-hidden="true" />{domainLabel(d)} <span className="num">{c}</span>
        </button>
      ))}
      {hiddenCount > 0 && (
        <button type="button" className="kg-chip" onClick={onShowHidden}>
          显示已隐藏的 {hiddenCount} 个
        </button>
      )}
      <button
        type="button"
        className={`kg-chip${canvasMode ? ' is-on' : ''}`}
        aria-pressed={canvasMode}
        title="同一图谱挂入无限画布: 拖拽平移 / 滚轮缩放 / 双击重置"
        onClick={onToggleCanvas}
      >
        画布模式
      </button>
      <button type="button" className="kg-chip kg-chip-nav" onClick={() => onNavigate('/')}>回资讯首页</button>
    </div>
  );
}
