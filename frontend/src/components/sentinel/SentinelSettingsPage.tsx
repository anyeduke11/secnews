/**
 * SentinelSettingsPage — 哨兵终端 · 06 设置 (只读控制台)
 *
 * 设计契约 (V2 参考稿 settings 屏):
 *  - 布局: .st-grid{minmax(0,1fr) 340px} 主栏 + 右栏; .st-rule{212px minmax(0,1fr)}
 *    的「标签列 / 控件列」行式布局; 窄屏降为单列。
 *  - 五条哨兵纪律: 零霓虹 (hairline + 1~3% 亮度差, 圆角只 6/8/10px)、语义三色锁
 *    (mint 正常 / amber 需注意 / red 仅破坏性与漏洞语境)、等宽承载全部数据、
 *    辅助文字 ≥11px、尊重 prefers-reduced-motion。全部落在 sentinel-settings.css。
 *
 * ⚠️ 安全边界 (2026-08 实测: 后端 HOTSPOT_HOST=0.0.0.0 暴露局域网, 且 174 条
 * 状态变更路由中 167 条零凭证):
 *  1. 本屏**零写操作**: 只发 GET, 不接 POST/PUT/DELETE, 因此所有开关都渲染为
 *     disabled 的只读指示器 + 一行「改法」说明。
 *  2. 不读取、不缓存、不回显任何密钥/口令; 不落 localStorage/sessionStorage。
 *     密钥相关只呈现 /api/secrets/status 的非敏感布尔与 TTL 计数。
 *  3. 不渲染任何来自 API 的 href (无需外链白名单跳转); 无 dangerouslySetInnerHTML。
 *  4. DANGER ZONE 仅做只读能力清单 (哪些破坏性端点存在 / 本屏是否可达),
 *     操作一律指向本地终端。
 *
 * 数据源 (全部 GET):
 *  - /api/settings/features   能力开关 (feature_gates.toml 运行时视图)
 *  - /api/health              采集间隔 collect_interval_seconds / 调度器 job / 版本 / proxy 模式
 *  - /api/llm/status          模型就绪态 (scenario / default_provider / providers)
 *  - /api/secrets/status      主密钥状态 (setup / unlocked / remaining_seconds) — 非敏感
 *  - /api/sources/health      源健康, 复用 SentinelShell 的 usePipe(), 本页不重复请求
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { SentinelShell, usePipe } from './SentinelShell';
import './sentinel.css';
import './sentinel-settings.css';

/* ------------------------------------------------------------------ 类型 */

interface FeaturesPayload {
  codegarden?: boolean;
  codegarden_phase2b?: boolean;
  mcp?: boolean;
  sync?: boolean;
  tech_stack?: boolean;
  security_graph?: boolean;
  secnews?: boolean;
  crm?: boolean;
  workbench_ui?: boolean;
  enabled_extensions?: string[];
}

interface LlmProviderRow {
  type?: string;
  model_score?: string;
  model_summary?: string;
  configured?: boolean;
}

interface LlmStatus {
  scenario?: string;
  description?: string;
  requires_external_agent?: boolean;
  t1_available?: boolean;
  t3_available?: boolean;
  llm_enabled?: boolean;
  default_provider?: string | null;
  fallback_order?: string[];
  providers?: Record<string, LlmProviderRow>;
}

/** /api/secrets/status — 只有布尔与剩余秒数, 无任何密钥材料 */
interface SecretsStatus {
  setup?: boolean;
  unlocked?: boolean;
  remaining_seconds?: number;
  keychain_persisted?: boolean;
}

interface HealthPayload {
  version?: string;
  status?: string;
  uptime_s?: number;
  collect_interval_seconds?: number;
  components?: {
    db?: { ok?: boolean };
    scheduler?: { ok?: boolean; jobs?: string[]; details?: { id: string; name?: string; next?: string }[] };
    proxy?: { ok?: boolean; mode?: string };
    collectors?: { ok?: boolean };
  };
}

type TabKey = 'collect' | 'features' | 'model' | 'danger';

const TABS: { key: TabKey; label: string; panelId: string }[] = [
  { key: 'collect', label: '采集与调度', panelId: 'st-panel-collect' },
  { key: 'features', label: '能力开关', panelId: 'st-panel-features' },
  { key: 'model', label: '模型与密钥', panelId: 'st-panel-model' },
  { key: 'danger', label: '危险区', panelId: 'st-panel-danger' },
];

/** 扩展开关清单 — 与 backend/api/settings.py get_features() 字段一一对应 */
const FEATURE_DEFS: { key: keyof FeaturesPayload; label: string; desc: string }[] = [
  { key: 'secnews', label: 'SecNews 情报核心', desc: '三层工作流、判读台与知识管线的总归属域。' },
  { key: 'codegarden', label: 'CodeGarden 代码花园', desc: 'Phase 2a 代码资产视图。' },
  { key: 'codegarden_phase2b', label: 'CodeGarden 运维层', desc: '服务网格 / 资源中枢 / 联动引擎 (M2-M4)。关闭时相关路由直接 404。' },
  { key: 'mcp', label: 'MCP 工具面', desc: '对外暴露 MCP 适配器与 agent 工具端点。' },
  { key: 'sync', label: '跨设备同步', desc: 'WebDAV 加密同步通道 (唯一默认开启的扩展域)。' },
  { key: 'tech_stack', label: '技术栈图谱', desc: '技术栈关联分析与图谱视图。' },
  { key: 'security_graph', label: '安全图谱', desc: 'ATT&CK / CVE 安全关联图谱。' },
  { key: 'crm', label: 'CRM 业绩座舱', desc: '客户与商机状态机视图。' },
  { key: 'workbench_ui', label: '工作台 UI 壳', desc: '五视图统一工作台外壳 (config.feature_workbench_ui)。' },
];

/**
 * 危险区能力清单 — 只读盘点, 不接线。
 * 端点存在性来自 backend/api/{maintenance,cache,secrets,sources,refresh,settings}.py 实测 grep。
 */
const DANGER_ITEMS: { cap: string; ep: string; note: string }[] = [
  { cap: '保留期裁剪 / 清空采集历史', ep: 'POST /api/maintenance/cleanup', note: '按天数物理删除已收录条目与日志, 执行后不可撤销。' },
  { cap: '删除重复条目', ep: 'POST /api/maintenance/cleanup-duplicates', note: '批量物理删除重复行, 仅保留最早一条。' },
  { cap: '清理质量日志', ep: 'POST /api/maintenance/cleanup-quality-logs', note: '删除历史门禁日志, 影响质量趋势回溯。' },
  { cap: '数据库 VACUUM', ep: 'POST /api/maintenance/vacuum', note: '重写 SQLite 文件回收空间, 运行期独占写锁。' },
  { cap: '清空缓存', ep: 'POST /api/cache/clear', note: '丢弃全部列表缓存, 下一轮采集前查询显著变慢。' },
  { cap: '重置全部主密钥', ep: 'POST /api/secrets/reset', note: '需二次确认字符串; 执行后既有密文永久不可解。' },
  { cap: '整库导入 / 覆盖密钥', ep: 'POST /api/secrets/import', note: '以导出文件整体覆盖本地密钥库。' },
  { cap: '停用 / 删除自定义源', ep: 'POST|DELETE /api/sources/custom…', note: '改动采集面清单, 影响后续收录范围。' },
  { cap: '手工触发采集 / 追抓', ep: 'POST /api/refresh', note: '立即抢占调度器并发抓取, 与定时轮次争抢资源。' },
  { cap: '改写采集间隔', ep: 'POST /api/settings/refresh-interval', note: '运行时改调度器 (1-1440 分钟), 重启后回到配置值。' },
];

/* ------------------------------------------------------------------ 工具 */

function relTime(iso?: string | null): string {
  if (!iso) return '--';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '--';
  const m = Math.floor((Date.now() - d.getTime()) / 60000);
  if (m < 1) return '刚刚';
  if (m < 60) return `${m} 分钟前`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h} 小时前`;
  return `${Math.floor(h / 24)} 天前`;
}

// 采集间隔秒数 → 哨兵 cron 风格周期串 (300 → 星号斜杠 300s), 一律等宽呈现
function schedCell(sec: number | null | undefined): string {
  if (sec == null || !Number.isFinite(sec) || sec <= 0) return '--';
  return `*/${Math.round(sec)}s`;
}

function minsOf(sec: number | null | undefined): string {
  if (sec == null || !Number.isFinite(sec) || sec <= 0) return '--';
  const v = sec / 60;
  return Number.isInteger(v) ? `${v} min` : `${v.toFixed(1)} min`;
}

function uptimeCell(s?: number | null): string {
  if (s == null || !Number.isFinite(s) || s < 0) return '--';
  const d = Math.floor(s / 86400);
  const h = Math.floor((s % 86400) / 3600);
  const m = Math.floor((s % 3600) / 60);
  return d > 0 ? `${d}d ${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}` : `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`;
}

function ttlCell(sec?: number | null): string {
  if (sec == null || !Number.isFinite(sec) || sec <= 0) return '00:00';
  return `${String(Math.floor(sec / 60)).padStart(2, '0')}:${String(Math.floor(sec % 60)).padStart(2, '0')}`;
}

function nextRunText(next?: string): string {
  if (!next || next === 'None') return '未排程';
  const d = new Date(next);
  if (Number.isNaN(d.getTime())) return next;
  const delta = Math.round((d.getTime() - Date.now()) / 1000);
  if (delta <= 0) return '正在运行';
  if (delta < 60) return `${delta}s 后`;
  return `${Math.floor(delta / 60)}m${String(delta % 60).padStart(2, '0')}s 后`;
}

/* ------------------------------------------------------- 子组件 (在壳内) */

/** 采集源表 — 源健康来自壳的 usePipe, 本页不重复请求 /api/sources/health */
function SourceTable({ intervalSec }: { intervalSec: number | null }) {
  const { pipe } = usePipe();
  const rank = (s: string) => (s === 'active' ? 0 : s === 'stale' ? 1 : 2);
  const rows = useMemo(
    () => [...(pipe?.sources ?? [])]
      .sort((a, b) => rank(a.status) - rank(b.status) || (b.total_items ?? 0) - (a.total_items ?? 0))
      .slice(0, 12),
    [pipe],
  );
  if (!pipe || pipe.total === 0) {
    return <p className="st-empty">源清单尚未就绪 — 与顶栏心跳条同源, 心跳返回后自动填充。</p>;
  }
  return (
    <>
      <table className="st-table">
        <colgroup><col className="st-c-nm" /><col className="st-c-sched" /><col className="st-c-last" /><col className="st-c-stat" /><col className="st-c-oper" /></colgroup>
        <thead>
          <tr>
            <th scope="col">源名</th><th scope="col">调度</th><th scope="col">上次活动</th><th scope="col">状态</th><th scope="col">启停</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((s, idx) => {
            const on = s.status === 'active';
            const key = `${s.category}-${s.source_name}-${idx}`;
            return (
              <tr key={key} className={`st-row${on ? '' : s.status === 'stale' ? ' is-warn' : ' is-off'}`}>
                <td>
                  <span className="st-nm">{s.source_name}</span>
                  <span className="st-sub">{s.category}{s.total_items != null ? ` · ${s.total_items} 篇` : ''}</span>
                </td>
                <td className="st-sched">{schedCell(intervalSec)}</td>
                <td className="st-last">{relTime(s.last_seen_at)}</td>
                <td>
                  <span className={`st-chip${on ? ' ok' : s.status === 'stale' ? ' warn' : ' bad'}`}>
                    <i aria-hidden="true" />{on ? '正常' : s.status === 'stale' ? '重试中' : '离线'}
                  </span>
                </td>
                <td className="st-oper">
                  {/* 只读指示器: 启停需写接口, 本屏不接线 */}
                  <button
                    type="button"
                    className="st-switch"
                    role="switch"
                    aria-checked={on}
                    disabled
                    title="只读展示 — 启停需后端写接口, 请在本地终端操作"
                    aria-label={`${s.source_name} 抓取${on ? '启用中' : '未启用'}（只读）`}
                  />
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <p className="st-tblfoot">
        共 {pipe.total} 个采集源 · 此处按状态与累计产出显示前 {rows.length} 个 · 调度列为全局 collect_all 间隔,
        后端未按源暴露独立周期
      </p>
    </>
  );
}

/** 右栏 · 管道体检 (同样复用壳的 usePipe) */
function PipeCard() {
  const { pipe } = usePipe();
  return (
    <div className="st-card">
      <h3>
        <svg width="13" height="13" viewBox="0 0 13 13" fill="none" aria-hidden="true"><path d="M1.5 9.5l3-3 2.5 2.5 4.5-5.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" /></svg>
        管道体检
      </h3>
      <p className="st-raildesc">数据与顶栏心跳条同源, 本页不重复拉取源健康接口。</p>
      <div className="st-cellgrid">
        <div className="st-cell"><span className="st-cellk">源在线</span><span className="st-cellv">{pipe ? `${pipe.active}/${pipe.total}` : '…'}</span></div>
        <div className="st-cell"><span className="st-cellk">重试中</span><span className="st-cellv amber">{pipe?.stale ?? '…'}</span></div>
        <div className="st-cell"><span className="st-cellk">离线</span><span className="st-cellv red">{pipe?.dead ?? '…'}</span></div>
        <div className="st-cell"><span className="st-cellk">整体</span><span className="st-cellv sm">{pipe?.health ?? '…'}</span></div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ 页面 */

export function SentinelSettingsPage() {
  const navigate = useNavigate();
  const [features, setFeatures] = useState<FeaturesPayload | null>(null);
  const [llm, setLlm] = useState<LlmStatus | null>(null);
  const [health, setHealth] = useState<HealthPayload | null>(null);
  const [secrets, setSecrets] = useState<SecretsStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [offline, setOffline] = useState(false);
  const [tab, setTab] = useState<TabKey>('collect');

  const load = useCallback(async () => {
    setLoading(true);
    const get = (path: string) =>
      fetch(path, { headers: { Accept: 'application/json' } })
        .then(r => (r.ok ? r.json() : null))
        .catch(() => null);
    const [f, l, h, s] = await Promise.all([
      get('/api/settings/features'),
      get('/api/llm/status'),
      get('/api/health'),
      get('/api/secrets/status'),
    ]);
    setFeatures(f); setLlm(l); setHealth(h); setSecrets(s);
    setOffline(f === null && l === null && h === null && s === null);
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  const intervalSec = health?.collect_interval_seconds ?? null;
  const jobDetails = health?.components?.scheduler?.details ?? [];
  const collectJob = jobDetails.find(j => j.id === 'collect_all');
  const providerRows = useMemo(
    () => Object.entries(llm?.providers ?? {}).map(([name, cfg]) => ({ name, ...cfg })),
    [llm],
  );
  const keyReady = Boolean(secrets?.setup);
  /** proxy.mode ∈ {off, auto, manual} (backend/proxy_config.py); off = 直连 */
  const proxyMode = health?.components?.proxy?.mode;
  const proxyRouted = proxyMode === 'auto' || proxyMode === 'manual';
  const enabledExt = useMemo(() => features?.enabled_extensions ?? [], [features]);

  const onTabKey = (e: React.KeyboardEvent) => {
    const i = TABS.findIndex(t => t.key === tab);
    if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') {
      e.preventDefault();
      const step = e.key === 'ArrowRight' ? 1 : -1;
      setTab(TABS[(i + step + TABS.length) % TABS.length].key);
    }
  };

  return (
    <SentinelShell layer="data" ingested={null}>
      <section className="st-scr scr" aria-label="系统设置 · 只读控制台">
        <div className="st-head">
          <div>
            <h2 className="st-title">设置</h2>
            <p className="st-sub2">
              这台工作站怎么配置的：采集节奏、能力开关、模型就绪度与危险区清单。
              {offline ? '后端未响应, 以下均为占位。' : '全部为只读读取, 本页不写入任何状态。'}
            </p>
          </div>
          <div className="st-headops">
            <span className="st-readonlypill"><i aria-hidden="true" />READ-ONLY CONSOLE</span>
            <button type="button" className="st-btn" onClick={load} disabled={loading}>
              <svg width="12" height="12" viewBox="0 0 12 12" fill="none" aria-hidden="true"><path d="M10 6a4 4 0 1 1-1.2-2.85M10 1.5V4H7.5" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" /></svg>
              {loading ? '读取中' : '刷新状态'}
            </button>
            <button type="button" className="st-btn" onClick={() => navigate('/')}>回到资料层</button>
          </div>
        </div>

        <div className="st-grid">
          <div className="st-main">
            <div className="st-tabs" role="tablist" aria-label="设置分区" onKeyDown={onTabKey}>
              {TABS.map(t => (
                <button
                  key={t.key}
                  type="button"
                  role="tab"
                  id={`st-tab-${t.key}`}
                  className="st-tab"
                  aria-selected={tab === t.key}
                  aria-controls={t.panelId}
                  tabIndex={tab === t.key ? 0 : -1}
                  onClick={() => setTab(t.key)}
                >
                  {t.label}
                </button>
              ))}
            </div>

            {loading && (
              <section className="st-panel" id={TABS.find(t => t.key === tab)?.panelId ?? 'st-panel-collect'} role="tabpanel" aria-labelledby={`st-tab-${tab}`} aria-busy="true">
                <div className="skel-line w1" /><div className="skel-line w2" /><div className="skel-line w3" />
              </section>
            )}

            {/* ===== Tab 1 采集与调度 ===== */}
            {!loading && tab === 'collect' && (
              <section className="st-panel" id="st-panel-collect" role="tabpanel" aria-labelledby="st-tab-collect">
                <h2 className="st-ph">采集节奏与源状态</h2>
                <p className="st-tblmeta">
                  <b>{health?.components?.scheduler?.ok ? '调度器在线' : '调度器状态未知'}</b>
                  {' · '}间隔改法：编辑 <code className="st-code">.env</code> 的
                  <code className="st-code"> COLLECT_INTERVAL_SECONDS</code> 后重启后端
                  （<code className="st-code">POST /api/settings/refresh-interval</code> 为写接口, 本屏不接线）
                </p>
                <div className="st-cellgrid">
                  <div className="st-cell"><span className="st-cellk">采集间隔</span><span className="st-cellv">{schedCell(intervalSec)}</span><span className="st-cellnote">{minsOf(intervalSec)} / 轮 · collect_all + trend_rebuild 同频</span></div>
                  <div className="st-cell"><span className="st-cellk">下一轮</span><span className="st-cellv sm">{collectJob ? nextRunText(collectJob.next) : '--'}</span><span className="st-cellnote">取自 /api/health scheduler.details</span></div>
                  <div className="st-cell"><span className="st-cellk">注册 job</span><span className="st-cellv">{jobDetails.length || '--'}</span><span className="st-cellnote">调度器当前载入的定时任务数</span></div>
                  <div className="st-cell"><span className="st-cellk">已运行</span><span className="st-cellv sm">{uptimeCell(health?.uptime_s)}</span><span className="st-cellnote">服务进程存活时长</span></div>
                </div>
                <SourceTable intervalSec={intervalSec} />
                <p className="st-fnote">源启停、探测与删除均需写接口；本屏只显示后端已聚合出的只读健康视图。</p>
              </section>
            )}

            {/* ===== Tab 2 能力开关 ===== */}
            {!loading && tab === 'features' && (
              <section className="st-panel" id="st-panel-features" role="tabpanel" aria-labelledby="st-tab-features">
                <h2 className="st-ph">扩展域开关</h2>
                <p className="st-tblmeta">
                  源：<code className="st-code">backend/config/feature_gates.toml</code>；
                  改法：编辑该文件或设 <code className="st-code">HOTSPOT_FEATURE_GATES</code> 环境变量后重启（无写接口, 本屏只读）
                </p>
                {features
                  ? FEATURE_DEFS.map(def => {
                    const on = Boolean(features[def.key]);
                    return (
                      <div className="st-rule" key={String(def.key)}>
                        <div>
                          <p className="st-flabel">{def.label}</p>
                          <p className="st-fcode">{String(def.key)}</p>
                        </div>
                        <div>
                          <div className="st-ctrlrow">
                            <button
                              type="button"
                              className="st-switch"
                              role="switch"
                              aria-checked={on}
                              disabled
                              title="只读展示 — 该开关由配置文件驱动, 需重启后端"
                              aria-label={`${def.label}${on ? '已启用' : '已停用'}（只读）`}
                            />
                            <span className={`st-chip${on ? ' ok' : ''}`}><i aria-hidden="true" />{on ? '已注册' : '未注册'}</span>
                            <span className="st-when">{on ? '路由与 job 均已挂载' : '路由 404 / job 不注册'}</span>
                          </div>
                          <p className="st-fdesc">{def.desc}</p>
                        </div>
                      </div>
                    );
                  })
                  : <p className="st-empty">未能读取 /api/settings/features — 后端不可达时不显示默认值, 以免误判。</p>}
                {enabledExt.length > 0 && (
                  <p className="st-tblfoot">enabled_extensions · <span className="mono">{enabledExt.join(' · ')}</span></p>
                )}
              </section>
            )}

            {/* ===== Tab 3 模型与密钥 ===== */}
            {!loading && tab === 'model' && (
              <section className="st-panel" id="st-panel-model" role="tabpanel" aria-labelledby="st-tab-model">
                <h2 className="st-ph">判读模型与密钥就绪度</h2>
                <p className="st-tblmeta">
                  来源 <code className="st-code">GET /api/llm/status</code> 与 <code className="st-code">GET /api/secrets/status</code>
                  {' · '}仅非敏感状态；本页不读取也不缓存任何密钥明文
                </p>
                <div className="st-rule">
                  <div><p className="st-flabel">降级场景</p><p className="st-fcode">scenario</p></div>
                  <div>
                    <div className="st-ctrlrow">
                      <span className={`st-chip${llm?.llm_enabled ? ' ok' : ' warn'}`}><i aria-hidden="true" />{llm?.scenario ?? '--'}</span>
                      <span className="st-when">{llm?.description ?? '未获取到场景描述'}</span>
                    </div>
                    <p className="st-fdesc">
                      T1 评分链 {llm?.t1_available ? '可用' : '不可用'} · T3 生成链 {llm?.t3_available ? '可用' : '不可用'} ·
                      需外部 agent {llm?.requires_external_agent ? '是' : '否'}
                    </p>
                  </div>
                </div>
                <div className="st-rule">
                  <div><p className="st-flabel">默认 provider</p><p className="st-fcode">default_provider</p></div>
                  <div>
                    <div className="st-ctrlrow">
                      <span className="st-provider">{llm?.default_provider ?? '--'}</span>
                      <span className="st-when">回退序 {llm?.fallback_order?.length ? llm.fallback_order.join(' → ') : '--'}</span>
                    </div>
                    {providerRows.length > 0 && (
                      <ul className="st-provs">
                        {providerRows.map(p => (
                          <li key={p.name}>
                            <span className={`st-secdot${p.configured ? ' ok' : ' warn'}`} aria-hidden="true" />
                            <span className="st-provname">{p.name}</span>
                            <span className="st-provmodel mono">{p.type ?? '--'}</span>
                            <span className="st-provmodel mono">{p.model_score ?? '--'} / {p.model_summary ?? '--'}</span>
                          </li>
                        ))}
                      </ul>
                    )}
                    <p className="st-fnote">模型名与供应商来自后端配置视图；切换 provider 需改 config/llm.yaml 或密钥库, 均为写操作。</p>
                  </div>
                </div>
                <div className="st-rule last">
                  <div><p className="st-flabel">主密钥</p><p className="st-fcode">fernet / keychain</p></div>
                  <div>
                    <div className="st-ctrlrow">
                      <span className={`st-chip${keyReady ? ' ok' : ' warn'}`}><i aria-hidden="true" />{keyReady ? 'KEY READY' : 'KEY NOT SETUP'}</span>
                      <span className="st-chip">{secrets?.unlocked ? '解锁窗口内' : '已锁定'}</span>
                      {secrets?.unlocked && <span className="st-when mono">剩余 {ttlCell(secrets.remaining_seconds)}</span>}
                      <span className="st-when">{secrets?.keychain_persisted ? '系统钥匙串已持久化' : '未持久化到钥匙串'}</span>
                    </div>
                    <p className="st-fdesc">
                      密钥条目内容、明文与主密钥一律不在本屏出现, 也不写入 sessionStorage / localStorage。
                      新增、轮换或导出请到密钥管理页, 或直接在本地终端完成。
                    </p>
                  </div>
                </div>
              </section>
            )}

            {/* ===== Tab 4 危险区 (只读盘点) ===== */}
            {!loading && tab === 'danger' && (
              <section className="st-panel" id="st-panel-danger" role="tabpanel" aria-labelledby="st-tab-danger">
                <h2 className="st-ph">危险区</h2>
                <div className="st-dangerline"><span>DANGER ZONE</span></div>
                <p className="st-dangerhint">
                  以下能力会不可逆地改写数据或密钥库。本屏<b>只盘点不接线</b>：不渲染任何触发按钮,
                  也不会在测试或交互中调用写接口。需要执行时请在<b>本地终端</b>完成,
                  并先把后端监听收回 <code className="st-code">127.0.0.1</code>。
                </p>
                <table className="st-table">
                  <colgroup><col /><col className="st-c-ep" /><col className="st-c-reach" /></colgroup>
                  <thead>
                    <tr><th scope="col">能力</th><th scope="col">端点</th><th scope="col">本屏可达</th></tr>
                  </thead>
                  <tbody>
                    {DANGER_ITEMS.map(d => (
                      <tr className="st-row" key={d.ep}>
                        <td>
                          <span className="st-nm">{d.cap}</span>
                          <span className="st-sub">{d.note}</span>
                        </td>
                        <td className="st-ep">{d.ep}</td>
                        <td><span className="st-chip bad"><i aria-hidden="true" />否</span></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <p className="st-fnote">
                  审计口径：后端 174 条状态变更路由中 167 条零凭证, 且 <code className="st-code">HOTSPOT_HOST=0.0.0.0</code> 时整个局域网可达。
                  这是「设置屏不做破坏性 UI」的直接原因, 不是假设。
                </p>
              </section>
            )}
          </div>

          {/* ===== 右栏 ===== */}
          <aside className="st-rail" aria-label="设置辅助面板">
            <PipeCard />

            <div className="st-card">
              <h3>
                <svg width="13" height="13" viewBox="0 0 13 13" fill="none" aria-hidden="true"><path d="M6.5 1.5l4.5 1.6v3.1c0 2.6-1.8 4.6-4.5 5.3C3.8 10.8 2 8.8 2 6.2V3.1L6.5 1.5z" stroke="currentColor" strokeWidth="1.5" stroke-linejoin="round" /></svg>
                安全姿态
              </h3>
              <div className="st-secrow">
                <span className={`st-secdot${keyReady ? ' ok' : ' warn'}`} aria-hidden="true" />
                <span>
                  <span className="st-secname">主密钥{keyReady ? '已派生（Fernet）' : '尚未初始化'}</span>
                  <span className="st-secsub">{keyReady ? 'KEY READY' : 'KEY NOT SETUP'}</span>
                </span>
              </div>
              <div className="st-secrow">
                <span className={`st-secdot${proxyRouted ? ' ok' : ' warn'}`} aria-hidden="true" />
                <span>
                  <span className="st-secname">出网代理{proxyMode ? `当前 ${proxyMode}` : '状态未知'}</span>
                  <span className="st-secsub">{proxyRouted ? 'VIA PROXY' : 'DIRECT CONNECT'}</span>
                </span>
              </div>
              <div className="st-secrow">
                <span className="st-secdot warn" aria-hidden="true" />
                <span>
                  <span className="st-secname">服务暴露面需自查</span>
                  <span className="st-secsub">CHECK BIND HOST</span>
                </span>
              </div>
              <p className="st-railnote">后端鉴权当前 fail-open, 请确认 <code className="st-code">.env</code> 的 HOST 取值后再判断是否可放在共享网络。</p>
            </div>

            <div className="st-card">
              <h3>
                <svg width="13" height="13" viewBox="0 0 13 13" fill="none" aria-hidden="true"><circle cx="6.5" cy="6.5" r="5" stroke="currentColor" strokeWidth="1.5" /><path d="M6.5 4v3l2 1.2" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" /></svg>
                本机与版本
              </h3>
              <div className="st-abouthead">
                <span className="st-ver mono">v{health?.version ?? '--'}</span>
                <span className="st-localpill"><i aria-hidden="true" />本地运行 · 无云端依赖</span>
              </div>
              <ul className="st-facts">
                <li><span>后端状态</span><span className="mono">{health?.status ?? '--'}</span></li>
                <li><span>DB 完整</span><span className="mono">{health?.components?.db?.ok == null ? '--' : health.components.db.ok ? 'yes' : 'no'}</span></li>
                <li><span>采集器在线</span><span className="mono">{health?.components?.collectors?.ok == null ? '--' : health.components.collectors.ok ? 'yes' : 'no'}</span></li>
                <li><span>采集间隔</span><span className="mono">{schedCell(intervalSec)}</span></li>
                <li><span>本页写请求</span><span className="mono mint">0</span></li>
              </ul>
            </div>
          </aside>
        </div>

        <footer className="endnote">
          <span>SECNEWS SENTINEL TERMINAL · 设置</span>
          <span>只读视图 · 零写请求 · 零本地缓存</span>
          <span>破坏性操作请在本地终端完成</span>
        </footer>
      </section>
    </SentinelShell>
  );
}
