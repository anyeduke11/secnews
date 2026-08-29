/**
 * SentinelGardenPage — 哨兵终端 · 行动层 CodeGarden 项目园 (V2 设计稿 codegarden 屏 / GARDEN)
 *
 * 信息架构: 行动层第三屏 — 「把读完的东西，种成能跑的项目」。
 *  - 项目泳道看板: 四条泳道 = 生命周期阶段组 (孵化 / 构建 / 联调 / 服役)
 *  - 运行状态带: 服务网格 (cg_services) + 近期事件 (cg_events)
 *  - 服务注册矩阵: /services/topology 节点占用图 (非真实布局, 见下方 caveat)
 *
 * 数据源 (全部只读 GET, 无任何写操作):
 *  - GET /api/codegarden/projects           gate `codegarden` (默认 true)
 *  - GET /api/codegarden/services           gate `codegarden_phase2b`
 *  - GET /api/codegarden/services/topology  gate `codegarden_phase2b`
 *  - GET /api/codegarden/events             gate `codegarden_phase2b`
 *  - GET /api/codegarden/dependencies       gate `codegarden_phase2b`
 *  - GET /api/settings/features             (useFeatureFlags, 用于如实呈现门控)
 *  - GET /api/hotspots?time_range=24h       心跳条「今日收录」口径
 *
 * 只读契约 (硬性):
 *  - codegarden_ops.py 的 POST /services/{id}/restart、DELETE /services/{id}、
 *    POST /projects (立项)、POST /services/scan、POST /playbooks/{name}/run 均不在本屏出现,
 *    且这些路由挂在默认关闭的 `codegarden_phase2b` 门上 (feature_gates.toml), 默认 404。
 *    本屏只做观测, 不放任何重启/删除/立项按钮。
 *
 * 数据面缺陷如实呈现 (不粉饰):
 *  - cg_services 实测 49 条 project_id 全为 null (自动发现后未做项目归属绑定) →
 *    列表逐行标 "未归属"，并在服务带给出 `已归属 0 / 未归属 N` 汇总。
 *  - cg_dependencies / cg_events 实测 0 行 → 走真实空态, 不造假事件与依赖边。
 *
 * 后端 status_color / runtime_color 处理:
 *  - 二者是 codegarden_service_service.get_topology() 内硬编码的十六进制字面值
 *    (#10b981 / #ef4444 / #fbbf24 / #2496ed …), 与本屏「零霓虹 + 语义三色锁」冲突。
 *  - 本屏把它们当**原始数据**看待: 不参与任何着色, 只按 node.data.status / .runtime
 *    用哨兵令牌重映射为 ok/warn/idle 三档 (红色留给漏洞告警语境, 服务停止/异常不上红)。
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useSSE } from '../../hooks/useSSE';
import { useFeatureFlags } from '../../hooks/useFeatureFlags';
import { SentinelShell, usePipeReloadOnSse } from './SentinelShell';
import './sentinel.css';
import './sentinel-garden.css';

/* ===================== 后端响应类型 (对齐只读端点实测字段) ===================== */

interface CgProject {
  id: string;
  name: string;
  display_name: string | null;
  description: string | null;
  type: string;
  source_type: string;
  lifecycle_stage: string;
  health_score: number | null;
  local_path: string | null;
  repo_url: string | null;
  upstream_url: string | null;
  tech_stack: string[] | null;
  tags: string[] | null;
  last_activity_at: string | null;
  archived_at: string | null;
}

interface CgService {
  id: string;
  project_id: string | null;
  name: string;
  namespace: string | null;
  type: string;
  runtime: string;
  status: string;
  endpoint_host: string | null;
  endpoint_port: number | null;
  endpoint_domain: string | null;
  health_check_type: string | null;
  health_check_path: string | null;
  health_check_interval: number | null;
  cpu_limit: string | null;
  memory_limit: string | null;
  created_at: string | null;
  last_checked_at: string | null;
}

/** /services/topology 节点 — runtime_color / status_color 故意不纳入本屏着色 (见文件头说明) */
interface CgTopoNode {
  id: string;
  type: string;
  position: { x: number; y: number };
  data: {
    label: string;
    service_id: string;
    runtime: string;
    status: string;
    endpoint_port: number | null;
    runtime_color?: string;
    status_color?: string;
  };
}

interface CgEvent {
  id: string;
  event_type: string;
  source_type: string;
  source_id: string;
  status: string;
  created_at: string | null;
  error_message: string | null;
}

interface CgDependency {
  id: string;
  source_type: string;
  source_id: string;
  target_type: string;
  target_id: string;
  dep_type: string;
}

type Panel<T> =
  | { state: 'loading' }
  | { state: 'absent'; status: number }
  | { state: 'failed' }
  | { state: 'ready'; data: T };

/* ===================== 常量词表 (来自后端枚举, 不自造) ===================== */

/** 四条泳道 = VALID_LIFECYCLE_STAGES 的阶段分组 (8 → 4) */
const LANES: { key: string; ph: string; label: string; stages: string[] }[] = [
  { key: 'incubate', ph: 'PH.01', label: '孵化', stages: ['ideation', 'prototype'] },
  { key: 'build', ph: 'PH.02', label: '构建', stages: ['development'] },
  { key: 'integrate', ph: 'PH.03', label: '联调', stages: ['testing'] },
  { key: 'serve', ph: 'PH.04', label: '服役', stages: ['running', 'maintenance'] },
];

/** VALID_LIFECYCLE_STAGES 全量中文标签 — 卡面 chip 用真实阶段, 不用泳道名冒充 */
const STAGE_LABELS: Record<string, string> = {
  ideation: '构想', prototype: '原型', development: '开发', testing: '测试',
  running: '运行', maintenance: '维护', archived: '归档', deprecated: '退役',
};

/** VALID_PROJECT_TYPES */
const TYPE_LABELS: Record<string, string> = {
  web_application: 'Web 应用', api_service: 'API 服务', cli: 'CLI',
  crawler: '采集器', library: '库', experiment: '实验',
};

/** VALID_SOURCE_TYPES */
const SOURCE_LABELS: Record<string, string> = {
  vibe: 'Vibe', fork: 'Fork', imported: '导入', reference: '引用',
};

/** VALID_SERVICE_STATUSES — 注意: 无一档使用红色 (红色专属漏洞告警语境) */
const STATUS_LABELS: Record<string, string> = {
  running: '运行中', stopped: '已停止', error: '异常', unknown: '未检测',
};

/** VALID_RUNTIMES */
const RUNTIME_LABELS: Record<string, string> = {
  docker: 'docker', pm2: 'pm2', system: 'system', bare: 'bare',
};

/** cg_events.event_type 词表 (codegarden_orchestration_repo VALID_EVENT_TYPES 注释口径) */
const EVENT_LABELS: Record<string, string> = {
  code_push: '代码推送', service_error: '服务异常', port_conflict: '端口冲突',
  dep_update: '依赖变更', project_archive: '项目归档',
};

const SERVICE_LIMIT = 12;

/* ===================== 纯函数 helpers ===================== */

/** 服务状态 → 哨兵语义三档; stopped 归 idle (灰), 不算红色告警 */
function statusTone(status: string): 'ok' | 'warn' | 'idle' {
  if (status === 'running') return 'ok';
  if (status === 'stopped') return 'idle';
  return 'warn'; // error / unknown → 需注意
}

function statusClass(status: string): string {
  return statusTone(status) === 'ok' ? 'ok' : statusTone(status) === 'idle' ? 'idle' : 'warn';
}

/** 项目阶段 → 泳道 key; 未命中 (archived / deprecated / 未知) 返回 null 交给溢出条 */
function laneKeyOf(stage: string): string | null {
  for (const lane of LANES) if (lane.stages.includes(stage)) return lane.key;
  return null;
}

/** API 来源 href 白名单: 只允许 http(s); local_path 等文件系统路径永不成为链接 */
function safeHref(url: string | null | undefined): string | null {
  if (typeof url !== 'string') return null;
  return /^https?:\/\/\S+$/i.test(url.trim()) ? url.trim() : null;
}

function relTime(iso?: string | null): string {
  if (!iso) return '--';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '--';
  const m = Math.floor((Date.now() - d.getTime()) / 60000);
  if (m < 1) return '刚刚';
  if (m < 60) return `${m} 分钟前`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h} 小时前`;
  const day = Math.floor(h / 24);
  if (day === 1) return '昨天';
  if (day < 30) return `${day} 天前`;
  return d.toLocaleDateString('zh-CN');
}

function hhmm(iso?: string | null): string {
  if (!iso) return '--:--';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '--:--';
  const p = (n: number) => String(n).padStart(2, '0');
  return `${p(d.getHours())}:${p(d.getMinutes())}`;
}

async function getPanel<T>(url: string): Promise<Panel<T>> {
  try {
    const r = await fetch(url, { headers: { Accept: 'application/json' } });
    // 扩展门控关闭时路由不注册 → FastAPI 404; 如实呈现为「端点未注册」而非 0 条
    if (r.status === 404 || r.status === 405) return { state: 'absent', status: r.status };
    if (!r.ok) return { state: 'failed' };
    return { state: 'ready', data: (await r.json()) as T };
  } catch {
    return { state: 'failed' };
  }
}

/* ===================== 子视图 ===================== */

/** 项目卡: 只渲染真实字段; health_score 为 0/空时显示「未评分」而不是 0% 进度条 */
function ProjectCard({ project, index }: { project: CgProject; index: number }) {
  const href = safeHref(project.repo_url) ?? safeHref(project.upstream_url);
  const name = project.display_name || project.name;
  const score = typeof project.health_score === 'number' ? project.health_score : 0;
  const techs = (project.tech_stack ?? []).slice(0, 3);
  const aria = `项目 ${name}，阶段 ${STAGE_LABELS[project.lifecycle_stage] ?? project.lifecycle_stage}`;

  return (
    <article className="cg-card" aria-label={aria}>
      <div className="cg-top">
        <span className="cg-id num">{`P${String(index + 1).padStart(2, '0')}·${project.id.slice(0, 6)}`}</span>
        <span className="cg-chip">{STAGE_LABELS[project.lifecycle_stage] ?? project.lifecycle_stage}</span>
      </div>
      {href ? (
        <h3 className="cg-n"><a href={href} target="_blank" rel="noopener noreferrer">{name}</a></h3>
      ) : (
        <h3 className="cg-n">{name}</h3>
      )}
      <p className="cg-s">{project.description || `${TYPE_LABELS[project.type] ?? project.type} · ${SOURCE_LABELS[project.source_type] ?? project.source_type} 来源，无描述`}</p>
      {score > 0 ? (
        <div className="cg-brow">
          <div className="cg-bar" role="progressbar" aria-valuenow={score} aria-valuemin={0} aria-valuemax={100} aria-label={`健康度 ${score}`}>
            <span className="cg-fill" style={{ width: `${Math.min(100, score)}%` }} />
          </div>
          <span className="cg-pct num">{score}</span>
        </div>
      ) : (
        <div className="cg-brow"><span className="cg-pct num">健康度 未评分</span></div>
      )}
      <div className="cg-m">
        <b>{TYPE_LABELS[project.type] ?? project.type}</b>
        <span className="sep" aria-hidden="true" />
        {techs.length > 0 ? <span className="cg-tech">{techs.join(' / ')}</span> : <span>无技术栈记录</span>}
        <span className="sep" aria-hidden="true" />
        <span className="num">最近活动 {relTime(project.last_activity_at)}</span>
      </div>
    </article>
  );
}

/** 服务注册矩阵 — topology 节点的占用图 (后端 position 为线性占位, 故不称为拓扑布局) */
function TopoMatrix({ nodes }: { nodes: CgTopoNode[] }) {
  const cols = 24;
  const rows = Math.max(1, Math.ceil(nodes.length / cols));
  const cell = 9;
  return (
    <div className="cg-matrix">
      <svg
        width="100%"
        height={rows * (cell + 3)}
        viewBox={`0 0 ${cols * (cell + 3)} ${rows * (cell + 3)}`}
        role="img"
        aria-label={`服务注册矩阵，共 ${nodes.length} 个节点`}
      >
        {nodes.map((n, i) => (
          <rect
            key={n.id}
            className={`cg-node cg-${statusTone(n.data.status)}`}
            x={(i % cols) * (cell + 3)}
            y={Math.floor(i / cols) * (cell + 3)}
            width={cell}
            height={cell}
            rx={1.5}
          >
            <title>{`${n.data.label} · ${STATUS_LABELS[n.data.status] ?? n.data.status} · ${RUNTIME_LABELS[n.data.runtime] ?? n.data.runtime}${n.data.endpoint_port ? ` :${n.data.endpoint_port}` : ''}`}</title>
          </rect>
        ))}
      </svg>
    </div>
  );
}

/* ===================== 页面 ===================== */

export function SentinelGardenPage() {
  const navigate = useNavigate();
  const flags = useFeatureFlags();
  const reloadPipe = usePipeReloadOnSse();

  const [projects, setProjects] = useState<Panel<{ total?: number; items?: CgProject[] }>>({ state: 'loading' });
  const [services, setServices] = useState<Panel<{ total?: number; items?: CgService[] }>>({ state: 'loading' });
  const [topology, setTopology] = useState<Panel<{ nodes?: CgTopoNode[]; edges?: { id: string }[] }>>({ state: 'loading' });
  const [events, setEvents] = useState<Panel<{ total?: number; items?: CgEvent[] }>>({ state: 'loading' });
  const [deps, setDeps] = useState<Panel<{ total?: number; items?: CgDependency[] }>>({ state: 'loading' });
  const [ingested, setIngested] = useState<number | null>(null);

  const load = useCallback(async () => {
    const [pr, sv, tp, ev, dp, hs] = await Promise.all([
      getPanel<{ total?: number; items?: CgProject[] }>('/api/codegarden/projects?limit=200'),
      getPanel<{ total?: number; items?: CgService[] }>('/api/codegarden/services?limit=200'),
      getPanel<{ nodes?: CgTopoNode[]; edges?: { id: string }[] }>('/api/codegarden/services/topology'),
      getPanel<{ total?: number; items?: CgEvent[] }>('/api/codegarden/events?limit=20'),
      getPanel<{ total?: number; items?: CgDependency[] }>('/api/codegarden/dependencies?limit=200'),
      fetch('/api/hotspots?category=all&time_range=24h&limit=1', { headers: { Accept: 'application/json' } })
        .then(r => (r.ok ? r.json() : null))
        .catch(() => null),
    ]);
    setProjects(pr);
    setServices(sv);
    setTopology(tp);
    setEvents(ev);
    setDeps(dp);
    if (hs && typeof hs.total === 'number') setIngested(hs.total);
  }, []);

  useEffect(() => { load(); }, [load]);

  // SSE: cg_event_process job 每 60s 消费事件总线 → 15s 节流刷新 (只读刷新, 不触发任何运维端点)
  const gateRef = useRef(0);
  useSSE({
    onEvent: () => {
      const now = Date.now();
      if (now - gateRef.current < 15000) return;
      gateRef.current = now;
      reloadPipe();
      load();
    },
  });

  /* ---- 泳道分组 ---- */
  const projRows = projects.state === 'ready' ? (projects.data.items ?? []) : [];
  const board = useMemo(() => {
    const buckets = new Map<string, CgProject[]>();
    for (const lane of LANES) buckets.set(lane.key, []);
    const rest: CgProject[] = [];
    for (const p of projRows) {
      const key = laneKeyOf(p.lifecycle_stage);
      if (key) buckets.get(key)!.push(p);
      else rest.push(p);
    }
    const byActivity = (a: CgProject, b: CgProject) =>
      String(b.last_activity_at ?? '').localeCompare(String(a.last_activity_at ?? ''));
    for (const list of buckets.values()) list.sort(byActivity);
    rest.sort(byActivity);
    return { buckets, rest };
  }, [projRows]);

  /* ---- 服务统计 ---- */
  const svcRows = services.state === 'ready' ? (services.data.items ?? []) : [];
  const svcStats = useMemo(() => {
    const count = (fn: (s: CgService) => boolean) => svcRows.filter(fn).length;
    const names = new Set(svcRows.map(s => s.name));
    return {
      total: svcRows.length,
      running: count(s => s.status === 'running'),
      stopped: count(s => s.status === 'stopped'),
      warn: count(s => s.status === 'error' || s.status === 'unknown'),
      claimed: count(s => !!s.project_id),
      unclaimed: count(s => !s.project_id),
      withPort: count(s => s.endpoint_port != null),
      distinctNames: names.size,
    };
  }, [svcRows]);

  const svcList = useMemo(
    () => [...svcRows].sort((a, b) => String(b.last_checked_at ?? '').localeCompare(String(a.last_checked_at ?? ''))),
    [svcRows],
  );

  const topoNodes = topology.state === 'ready' ? (topology.data.nodes ?? []) : [];
  const topoEdges = topology.state === 'ready' ? (topology.data.edges ?? []) : [];
  const eventRows = events.state === 'ready' ? (events.data.items ?? []) : [];
  const depRows = deps.state === 'ready' ? (deps.data.items ?? []) : [];
  const projectTotal = projects.state === 'ready' ? (projects.data.total ?? projRows.length) : 0;

  /** 面板不可用时的三种如实空态 */
  const absentNote = (p: Panel<unknown>, what: string) => (
    <p className="cg-note cg-note-warn">
      {p.state === 'absent'
        ? `${what}端点未注册（${p.status}）：所属扩展 codegarden_phase2b 在 feature_gates.toml 中默认关闭。`
        : p.state === 'failed'
          ? `${what}端点请求失败：请确认后端运行在 127.0.0.1:8000。`
          : `${what}加载中…`}
    </p>
  );

  return (
    <SentinelShell layer="action" ingested={ingested}>
      <section className="cg-scr" aria-label="行动层 · CodeGarden 项目园">
        {/* ===== 屏标题 ===== */}
        <header className="cg-head">
          <div>
            <h2 className="cg-h1">CODE<span>GARDEN</span></h2>
            <p className="cg-sub">
              把读完的东西，种成能跑的项目 · 在园 <span className="num">{projectTotal || '…'}</span> 个
              {svcStats.total > 0 && <> · 注册服务 <span className="num">{svcStats.total}</span> 个</>}
            </p>
          </div>
          <a className="cg-back" href="/" onClick={e => { e.preventDefault(); navigate('/'); }}>
            <svg width="13" height="13" viewBox="0 0 13 13" fill="none" aria-hidden="true"><path d="M10.5 6.5H3M6.5 3L3 6.5l3.5 3.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" /></svg>
            返回资料层
          </a>
        </header>

        {/* ===== 项目泳道 ===== */}
        <section className="cg-board" aria-labelledby="cg-kanh">
          <div className="cg-kanbar">
            <h3 className="cg-kanh" id="cg-kanh">项目泳道</h3>
            <span className="cg-kanct num">{projectTotal} PROJECTS</span>
            <span className="cg-readonly">只读观测 · 立项与生命周期变更不在本屏</span>
          </div>

          {projects.state === 'loading' && (
            <div className="cg-loading" aria-busy="true">
              <div className="skel-line w1" /><div className="skel-line w2" /><div className="skel-line w3" />
            </div>
          )}
          {(projects.state === 'absent' || projects.state === 'failed') && absentNote(projects, '项目列表')}
          {projects.state === 'ready' && projRows.length === 0 && (
            <div className="cg-empty-strip">园区尚空 —— 没有 cg_projects 记录。</div>
          )}

          {projects.state === 'ready' && projRows.length > 0 && (
            <>
              <div className="cg-lanes">
                {LANES.map(lane => {
                  const list = board.buckets.get(lane.key) ?? [];
                  return (
                    <div className="cg-lane" key={lane.key} data-phase={lane.ph}>
                      <header className="cg-laneh">
                        <span className="cg-ph">{lane.ph}</span>
                        <span className="cg-ln">{lane.label}</span>
                        <span className="cg-lc num">{list.length}</span>
                      </header>
                      <div className="cg-laneb">
                        {list.length === 0 ? (
                          <p className="cg-lane-empty">暂无项目</p>
                        ) : (
                          list.map((p, i) => <ProjectCard key={p.id} project={p} index={i} />)
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>

              {/* 溢出阶段如实呈现, 保证四条泳道 + 溢出 = 总数可对账 */}
              {board.rest.length > 0 && (
                <p className="cg-rest">
                  另有 <span className="num">{board.rest.length}</span> 个项目处于泳道外阶段：
                  {board.rest.map(p => ` ${STAGE_LABELS[p.lifecycle_stage] ?? p.lifecycle_stage}`).join(' / ')}
                </p>
              )}
            </>
          )}
        </section>

        {/* ===== 运行状态带 ===== */}
        <section className="cg-meta" aria-label="运行状态与近期事件">
          <div className="cg-blk">
            <h3 className="cg-blkh">
              <svg width="13" height="13" viewBox="0 0 13 13" fill="none" aria-hidden="true"><path d="M1.5 6.5H4l1.5-3.5 2.5 7 1.5-3.5h2" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" /></svg>
              服务网格
              <span className="cg-blkn num">{svcStats.total} SERVICES</span>
            </h3>

            {services.state === 'loading' && (
              <div aria-busy="true"><div className="skel-line w2" /><div className="skel-line w3" /></div>
            )}
            {(services.state === 'absent' || services.state === 'failed') && absentNote(services, '服务网格')}

            {services.state === 'ready' && svcStats.total === 0 && (
              <p className="cg-empty-strip">cg_services 表 0 行 —— 自动发现尚未写入任何服务。</p>
            )}

            {services.state === 'ready' && svcStats.total > 0 && (
              <>
                <ul className="cg-sumrow">
                  <li><span className="k">运行中</span><span className={`v cg-${statusTone('running')}`}>{svcStats.running}</span></li>
                  <li><span className="k">已停止</span><span className="v">{svcStats.stopped}</span></li>
                  <li><span className="k">异常/未检测</span><span className={`v ${svcStats.warn > 0 ? 'cg-warn' : ''}`}>{svcStats.warn}</span></li>
                  <li><span className="k">有端口</span><span className="v">{svcStats.withPort}</span></li>
                </ul>

                {/* 已登记数据面缺陷: 自动发现的服务全部未绑定项目 */}
                <p className={`cg-note ${svcStats.unclaimed > 0 ? 'cg-note-warn' : ''}`}>
                  项目归属：已归属 <span className="num">{svcStats.claimed}</span> / 未归属 <span className="num">{svcStats.unclaimed}</span>
                  {svcStats.unclaimed > 0 && '（自动发现后未做 project 绑定 —— 已知数据面缺陷）'}
                </p>
                {svcStats.distinctNames < svcStats.total && (
                  <p className="cg-note">
                    <span className="num">{svcStats.total}</span> 条注册记录仅对应
                    <span className="num"> {svcStats.distinctNames}</span> 个服务名（同名多次注册）。
                  </p>
                )}

                <ul className="cg-svc">
                  {svcList.slice(0, SERVICE_LIMIT).map(s => (
                    <li className="cg-svcrow" key={s.id}>
                      <span className={`cg-dot cg-${statusClass(s.status)}`} aria-hidden="true" />
                      <span className="cg-svcn">{s.name}</span>
                      <span className={`cg-svcst cg-${statusClass(s.status)}`}>{STATUS_LABELS[s.status] ?? s.status}</span>
                      <span className="cg-svcmeta num">
                        {RUNTIME_LABELS[s.runtime] ?? s.runtime}
                        {s.endpoint_port != null ? ` · :${s.endpoint_port}` : ' · 无端口'}
                        {` · ${s.health_check_interval ?? '--'}s`}
                      </span>
                      <span className={`cg-owner${s.project_id ? '' : ' cg-owner-none'}`}>
                        {s.project_id ? '已归属' : '未归属'}
                      </span>
                    </li>
                  ))}
                </ul>
                {svcList.length > SERVICE_LIMIT && (
                  <p className="cg-note">
                    按最近检测时间排序，仅列出前 <span className="num">{SERVICE_LIMIT}</span> 条，
                    其余 <span className="num">{svcList.length - SERVICE_LIMIT}</span> 条未展示。
                  </p>
                )}

                {/* 拓扑占用图 */}
                {topology.state === 'ready' && topoNodes.length > 0 && (
                  <div className="cg-topo">
                    <div className="cg-topoh">
                      <span>服务注册矩阵</span>
                      <span className="cg-blkn num">{topoNodes.length} NODES · {topoEdges.length} EDGES</span>
                    </div>
                    <TopoMatrix nodes={topoNodes} />
                    <p className="cg-note">
                      后端 position 为线性占位（i×200），
                      {topoEdges.length === 0 ? '且 cg_dependencies 当前 0 行 —— 无依赖边可画，故此图为占用矩阵而非拓扑布局。' : `依赖边 ${topoEdges.length} 条。`}
                    </p>
                    <p className="cg-note">
                      节点配色由 status 经哨兵令牌重映射，后端 topology 响应内的
                      status_color / runtime_color 十六进制值不参与着色（零霓虹纪律）。
                    </p>
                  </div>
                )}
                {topology.state !== 'ready' && topology.state !== 'loading' && absentNote(topology, '服务拓扑')}
              </>
            )}
          </div>

          {/* 近期事件 */}
          <div className="cg-blk">
            <h3 className="cg-blkh">
              <svg width="13" height="13" viewBox="0 0 13 13" fill="none" aria-hidden="true"><circle cx="6.5" cy="6.5" r="4.8" stroke="currentColor" strokeWidth="1.5" /><path d="M6.5 4.2V6.5l1.6 1.4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" /></svg>
              近期事件
              <span className="cg-blkn num">
                {events.state === 'ready' ? `TODAY ${eventRows.length}` : events.state === 'loading' ? '…' : 'N/A'}
              </span>
            </h3>

            {events.state === 'loading' && <div aria-busy="true"><div className="skel-line w3" /></div>}
            {(events.state === 'absent' || events.state === 'failed') && absentNote(events, '事件总线')}

            {events.state === 'ready' && eventRows.length === 0 && (
              <div className="cg-empty-block">
                <div className="cg-empty-ring" aria-hidden="true">
                  <svg width="18" height="18" viewBox="0 0 18 18" fill="none"><circle cx="9" cy="9" r="6.5" stroke="currentColor" strokeWidth="1.5" /></svg>
                </div>
                <p>cg_events 表当前 <span className="num">0</span> 行 —— 联动引擎未发布任何事件。</p>
              </div>
            )}

            {eventRows.length > 0 && (
              <ul className="cg-ev">
                {eventRows.map(e => (
                  <li className="cg-evrow" key={e.id}>
                    <span className="cg-ev-t num">{hhmm(e.created_at)}</span>
                    <span>
                      {EVENT_LABELS[e.event_type] ?? e.event_type}
                      {' · '}{e.source_type}
                      {e.status !== 'processed' ? ` · ${e.status}` : ''}
                    </span>
                  </li>
                ))}
              </ul>
            )}

            {/* 依赖关系 (cg_dependencies 实测 0 行) */}
            <div className="cg-dep">
              <h4 className="cg-deph">
                依赖关系
                <span className="cg-blkn num">
                  {deps.state === 'ready' ? `${deps.data.total ?? depRows.length} DEPS` : deps.state === 'loading' ? '…' : 'N/A'}
                </span>
              </h4>
              {deps.state === 'ready' && depRows.length === 0 && (
                <p className="cg-note">cg_dependencies 表 <span className="num">0</span> 行 —— 影响分析（BFS 反向追溯）当前无输入。</p>
              )}
              {deps.state === 'ready' && depRows.length > 0 && (
                <ul className="cg-ev">
                  {depRows.slice(0, 8).map(d => (
                    <li className="cg-evrow" key={d.id}>
                      <span className="cg-ev-t num">{d.dep_type}</span>
                      <span>{d.source_type}:{d.source_id.slice(0, 6)} → {d.target_type}:{d.target_id.slice(0, 6)}</span>
                    </li>
                  ))}
                </ul>
              )}
              {(deps.state === 'absent' || deps.state === 'failed') && absentNote(deps, '依赖列表')}
            </div>
          </div>
        </section>

        {/* ===== 门控与只读声明 ===== */}
        <p className="cg-gate">
          运维门控 <span className="mono">codegarden_phase2b</span> =
          {' '}{flags.codegardenPhase2b ? '开启' : '关闭'}（backend/config/feature_gates.toml）。
          本屏为只读观测台：不提供重启 / 删除 / 扫描 / Playbook 执行等写操作入口。
        </p>
      </section>

      <footer className="endnote">
        <span>SECNEWS SENTINEL TERMINAL · 行动层 CODEGARDEN</span>
        <span>{projectTotal} PROJECTS · {svcStats.total} SERVICES</span>
        <span>SQLite WAL · 本地运行 · 只读</span>
      </footer>
    </SentinelShell>
  );
}
