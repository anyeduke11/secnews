/**
 * ExportActionsCard — 导出动作卡 (原 export cat 迁入运维区; 一次性动作, 非配置)。
 * 三个入口: HTML 报告 / XLSX 导出 (浏览器直下) + 报告页跳转 (订阅类)。
 */
import { Link } from 'react-router-dom';

export function ExportActionsCard() {
  return (
    <div className="st-card">
      <h3>数据导出</h3>
      <p className="st-section-desc">
        一次性导出动作（非配置）: HTML 报告适合分发，XLSX 适合二次分析；日报 / 周报在报告页订阅。
      </p>
      <div className="st-ctrlrow" style={{ flexWrap: 'wrap' }}>
        <a className="st-btn primary" href="/api/export" download>HTML 报告 →</a>
        <a className="st-btn" href="/api/export/xlsx" download>XLSX 导出 →</a>
        <Link className="st-btn" to="/report">日报 / 周报 (报告页) →</Link>
      </div>
    </div>
  );
}
