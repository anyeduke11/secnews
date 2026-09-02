/**
 * settings/ExportSettings — 数据导出 (Sentinel V2)。
 *
 * 设计原则:
 * - 顶部 st-head 用途说明 (合规交付 / 离线归档 / 周报分享)
 * - 3 种导出动作用 st-cellgrid + st-btn primary 表达
 * - st-info 块写"何时用哪个"
 * - Sentinel 5 disciplines: zero-neon / semantic-3-color / mono-data / mute-text / reduced-motion
 */
import { useNavigate } from 'react-router-dom';
import '../settings/settings-shell.css';

export function ExportSettings() {
  const navigate = useNavigate();

  return (
    <div className="settings-shell" style={{ display: 'flex', flexDirection: 'column', gap: 'var(--sn-row)' }}>
      <div className="st-head">
        <h2 className="st-title">数据导出</h2>
        <p className="st-sub2">
          把热点 / 知识条目导出为可分享的离线资产. 三种格式互补:
          HTML 报告适合邮件附档 + 团队分发;
          XLSX 适合二次二次分析 (Excel / Pandas);
          日报 / 周报适合定时邮件订阅 + 周会回顾.
          全部在浏览器内触发, 文件直出, 不经过第三服务。
        </p>
      </div>

      <div className="st-cellgrid">
        <div className="st-cell">
          <span className="st-cellk">HTML 报告</span>
          <span className="st-cellv sm">.html</span>
          <span className="st-cellnote">单文件 · 邮件分发</span>
        </div>
        <div className="st-cell">
          <span className="st-cellk">XLSX 导出</span>
          <span className="st-cellv sm">.xlsx</span>
          <span className="st-cellnote">结构化 · 二次分析</span>
        </div>
        <div className="st-cell">
          <span className="st-cellk">日报 / 周报</span>
          <span className="st-cellv sm">订阅</span>
          <span className="st-cellnote">周期回顾 · 团队同步</span>
        </div>
      </div>

      <div className="st-section">
        <div className="st-section-body">
          <div className="st-rule" style={{ borderBottom: 'none' }}>
            <span className="st-label">立即导出</span>
            <div className="st-ctrlrow" style={{ flexWrap: 'wrap' }}>
              <button
                className="st-btn primary"
                onClick={() => window.open('/api/export', '_blank')}
              >
                HTML 报告 →
              </button>
              <button
                className="st-btn"
                onClick={() => window.open('/api/export/xlsx', '_blank')}
              >
                XLSX 导出 →
              </button>
              <button
                className="st-btn"
                onClick={() => navigate('/report')}
              >
                日报 / 周报 →
              </button>
            </div>
          </div>
        </div>
      </div>

      <div className="st-info">
        <strong>何时用哪个</strong>
        <br />
        客户/外部: HTML 一份足够; 数据/分析师: 拉 XLSX 自己过滤;
        周会/复盘: 订阅日报或周报自动推送到飞书 / 邮箱。
      </div>
    </div>
  );
}