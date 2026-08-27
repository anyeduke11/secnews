/**
 * JudgeBidAnalysisPage — 判断层标讯分析页
 *
 * Phase 3: 标讯地区分布、状态分布、业务线分类可视化。
 * 数据来源于现有 `/api/hotspots?category=bid` 接口。
 */
import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Icon } from '../Icon';

/* ─── 类型 ─── */

interface BidItem {
  id: string;
  title: string;
  region?: string;
  bid_status?: string;
  source?: string;
  url?: string;
  published_at?: string;
}

/* ─── 常量 ─── */

const BID_LINES = [
  { key: 'security', label: '安全', keywords: ['安全', '防火墙', '入侵检测', '漏洞', '加密', '认证', '审计', 'SOC', 'SIEM', 'WAF', '堡垒机', '态势感知', '零信任', 'VPN', 'DLP', '数据安全', '网络安全', '信息安全'] },
  { key: 'ai',       label: 'AI',   keywords: ['AI', '人工智能', '大模型', '机器学习', '深度学习', '自然语言', '计算机视觉', '智能', '自动化', 'RPA', '机器人', '算法'] },
  { key: 'finance',  label: '金融', keywords: ['金融', '银行', '保险', '证券', '基金', '支付', '风控', '信贷', '理财', '监管'] },
  { key: 'general',  label: '通用', keywords: [] },
];

function classifyBidLine(title: string): string {
  for (const line of BID_LINES) {
    if (line.key === 'general') continue;
    if (line.keywords.some(kw => title.includes(kw))) return line.key;
  }
  return 'general';
}

/* ─── 地区映射 ─── */

const REGION_MAP: Record<string, string> = {
  '北京': '华北', '天津': '华北', '河北': '华北', '山西': '华北', '内蒙古': '华北',
  '上海': '华东', '江苏': '华东', '浙江': '华东', '安徽': '华东', '福建': '华东', '江西': '华东', '山东': '华东',
  '广东': '华南', '广西': '华南', '海南': '华南',
  '湖北': '华中', '湖南': '华中', '河南': '华中',
  '四川': '西南', '重庆': '西南', '贵州': '西南', '云南': '西南', '西藏': '西南',
  '陕西': '西北', '甘肃': '西北', '青海': '西北', '宁夏': '西北', '新疆': '西北',
  '辽宁': '东北', '吉林': '东北', '黑龙江': '东北',
};

function mapRegion(region: string): string {
  if (!region || region === '未知') return '未知';
  for (const [key, value] of Object.entries(REGION_MAP)) {
    if (region.includes(key)) return value;
  }
  return '其他';
}

/* ─── 主组件 ─── */

export function JudgeBidAnalysisPage() {
  const navigate = useNavigate();
  const [items, setItems] = useState<BidItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [view, setView] = useState<'region' | 'status' | 'line' | 'table'>('region');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await fetch('/api/hotspots?category=bid&limit=1000');
      if (!r.ok) return;
      const data = await r.json();
      setItems(data.items || []);
    } catch {}
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  /* 聚合计算 */
  const regionDist = aggregate(items, 'region', mapRegion);
  const statusDist = aggregate(items, 'bid_status', s => s || '未知');
  const lineDist = aggregate(items, 'title', classifyBidLine);

  return (
    <div className="min-h-[50vh]">
      {/* 页面头部 */}
      <div className="flex items-center gap-3 mb-4 pb-3" style={{ borderBottom: '2px solid var(--text-primary)' }}>
        <button
          onClick={() => navigate('/judge')}
          className="btn-ghost px-2.5 py-1.5 text-xs"
          title="返回判断层"
          aria-label="返回判断层"
        >
          <Icon size={14}>
            <line x1="19" y1="12" x2="5" y2="12" />
            <polyline points="12 19 5 12 12 5" />
          </Icon>
          返回
        </button>
        <h2 className="font-mono text-base font-bold" style={{ color: 'var(--text-primary)' }}>
          标讯分析
        </h2>
        <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
          判断层 · {loading ? '加载中...' : `${items.length} 条标讯`}
        </span>
      </div>

      {/* 视图切换 */}
      <div className="flex items-center gap-2 mb-4">
        {[
          { key: 'region' as const, label: '地区分布' },
          { key: 'status' as const, label: '状态分布' },
          { key: 'line' as const,   label: '业务线' },
          { key: 'table' as const,  label: '明细列表' },
        ].map(tab => {
          const active = tab.key === view;
          return (
            <button
              key={tab.key}
              onClick={() => setView(tab.key)}
              className="ink-chip focus-ring transition-colors"
              style={{
                padding: '3px 9px',
                color: active ? 'var(--text-on-light)' : 'var(--text-secondary)',
                backgroundColor: active ? 'var(--accent)' : 'var(--bg-hover)',
                borderColor: active ? 'var(--accent)' : 'var(--border-color)',
                fontWeight: active ? 600 : 400,
              }}
              aria-current={active ? 'page' : undefined}
            >
              {tab.label}
            </button>
          );
        })}
      </div>

      {/* 内容区 */}
      {loading ? (
        <div className="py-12 text-center text-xs" style={{ color: 'var(--text-muted)' }}>加载中...</div>
      ) : items.length === 0 ? (
        <div className="py-12 text-center text-xs" style={{ color: 'var(--text-muted)' }}>暂无标讯数据</div>
      ) : (
        <>
          {view === 'region' && <DistributionView data={regionDist} title="地区分布" unit="条" />}
          {view === 'status' && <DistributionView data={statusDist} title="状态分布" unit="条" />}
          {view === 'line' && <DistributionView data={lineDist} title="业务线分类" unit="条" />}
          {view === 'table' && (
            <div className="space-y-1">
              {items.slice(0, 200).map(item => (
                <div
                  key={item.id}
                  className="flex items-center gap-3 px-3 py-2 rounded-[var(--radius-sm)] transition-colors hover:bg-[var(--bg-hover)]"
                  style={{ borderBottom: '1px solid var(--border-color)' }}
                >
                  <div className="min-w-0 flex-1">
                    <a
                      href={item.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-[11.5px] hover:underline block truncate"
                      style={{ color: 'var(--text-primary)' }}
                    >
                      {item.title}
                    </a>
                    <div className="flex items-center gap-2 mt-0.5">
                      {item.region && (
                        <span className="text-[10px] px-1 py-0.5 rounded-sm" style={{ backgroundColor: 'var(--bg-hover)', color: 'var(--text-muted)' }}>
                          {item.region}
                        </span>
                      )}
                      {item.bid_status && (
                        <span className="text-[10px]" style={{ color: 'var(--text-muted)' }}>{item.bid_status}</span>
                      )}
                      {item.source && (
                        <span className="text-[10px]" style={{ color: 'var(--text-muted)' }}>{item.source}</span>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}

/* ══════════════════════════════════════════════
   辅助函数
   ══════════════════════════════════════════════ */

function aggregate<T>(items: T[], key: keyof T, mapper: (v: string) => string): Record<string, number> {
  const dist: Record<string, number> = {};
  for (const item of items) {
    const raw = item[key];
    const val = typeof raw === 'string' ? mapper(raw) : '未知';
    dist[val] = (dist[val] || 0) + 1;
  }
  return dist;
}

/* ══════════════════════════════════════════════
   子组件
   ══════════════════════════════════════════════ */

function DistributionView({ data, title, unit }: { data: Record<string, number>; title: string; unit: string }) {
  const entries = Object.entries(data).sort((a, b) => b[1] - a[1]);
  const maxVal = Math.max(...entries.map(e => e[1]), 1);

  return (
    <div
      className="p-4 rounded-[var(--radius-md)]"
      style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}
    >
      <h3 className="text-xs font-bold tracking-[0.12em] uppercase mb-3" style={{ color: 'var(--text-primary)' }}>
        {title}
      </h3>
      <div className="space-y-2">
        {entries.map(([label, count]) => (
          <div key={label} className="flex items-center gap-2">
            <span className="text-[11px] w-16 shrink-0 text-right" style={{ color: 'var(--text-secondary)' }}>{label}</span>
            <div className="flex-1 h-4 rounded-sm relative" style={{ backgroundColor: 'var(--bg-hover)' }}>
              <div
                className="h-full rounded-sm transition-all"
                style={{
                  width: `${(count / maxVal) * 100}%`,
                  backgroundColor: 'var(--accent)',
                  opacity: 0.6,
                }}
              />
              <span className="absolute right-1 top-0.5 text-[9px] font-mono tabular-nums" style={{ color: 'var(--text-muted)' }}>
                {count}{unit}
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
