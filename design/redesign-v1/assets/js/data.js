/* ============================================================
 * Hotspot 全站重构 demo — 演示数据集（演示样例 · 非真实数据）
 * 真实底数取自 PRD/审计文档公开口径（架构数字、v0.8.9 活体计数等）；
 * 条目级内容（资讯/案件/提案等）为编写的演示样例。
 * ============================================================ */
window.HD = (function () {
  'use strict';

  /* ---------- 心跳条：管道 + 16 采集源灯（DEV-0194 口径） ---------- */
  var PIPE = {
    health: 'ok', active: 15, total: 16, today: 128,
    funnel: { collected: 128, admitted: 96, signal: 41, case: 6 },
    queue: { pending: 12, running: 3, error: 1 },
    sources: [
      { n: 'CISA KEV', s: 'ok' }, { n: 'NVD', s: 'ok' }, { n: 'GitHub Advisory', s: 'ok' },
      { n: 'OSV', s: 'ok' }, { n: 'RustSec', s: 'retry' }, { n: 'PyPI Advisory', s: 'ok' },
      { n: 'MSRC', s: 'ok' }, { n: 'FreeBuf', s: 'ok' }, { n: '安全客', s: 'ok' },
      { n: '先知社区', s: 'ok' }, { n: '玄武实验室', s: 'ok' }, { n: '奇安信', s: 'ok' },
      { n: '绿盟', s: 'ok' }, { n: '安天', s: 'ok' }, { n: 'Mandiant', s: 'ok' },
      { n: 'Unit42', s: 'off' }
    ]
  };

  /* ---------- 架构数字（generate_meta.py 口径，2026-11-17） ---------- */
  var META = { jobs: 56, collectors: 19, routers: 99, services: 155, migrations: 133, gates: 16, wikiFts: 7734, hotspots: 14503, routes: 60, pages: 44, redirects: 16, components: 215 };

  /* ---------- 资讯流（演示样例） ---------- */
  var FEED = [
    { id: 'hs-1001', src: 'NVD', time: '09:12', sev: 'crit', mode: 'alert', hint: 'patch',
      title: 'OpenSSL 3.5 修复 CVE-2026-44127 内存越界写（CVSS 9.1）',
      sum: '影响 3.5.0–3.5.3 服务端场景，建议 48h 内完成补丁。附件含受影响版本判定脚本与回滚预案。',
      tags: ['漏洞', 'OpenSSL'], likes: 12, dislikes: 1, fav: true, pick: 96.4, deep: true },
    { id: 'hs-1002', src: 'CISA KEV', time: '08:47', sev: 'high', mode: 'alert', hint: 'patch',
      title: 'KEV 新增 Citrix Session Recording 路径遍历（CVE-2025-6543）',
      sum: '联邦机构限期 3 周修复；在野利用确认。联邦限期 3 周修复；在野利用确认。',
      tags: ['KEV', 'Citrix'], likes: 9, dislikes: 0, fav: false, pick: 91.2, deep: false },
    { id: 'hs-1003', src: 'GitHub Advisory', time: '08:15', sev: 'high', mode: 'alert', hint: 'investigate',
      title: 'PyPI 包 pdf-math-tools 疑似窃取 CI 凭据（供应链投毒）',
      sum: '下载量 4.1 万/周，行为特征：读取 GITHUB_TOKEN 后外联。附 IOC 与排查 SQL。',
      tags: ['供应链', 'PyPI'], likes: 21, dislikes: 2, fav: true, pick: 89.7, deep: true },
    { id: 'hs-1004', src: 'Unit42', time: '07:58', sev: 'high', mode: 'deep', hint: 'monitor',
      title: '勒索家族转向 ESXi：瞄准虚拟化层的数据存储',
      sum: 'TTP 变化：vSphere API 枚举 + 快照删除。附 MITRE 映射 T1499/T1486。',
      tags: ['勒索', 'ESXi'], likes: 14, dislikes: 1, fav: false, pick: 84.3, deep: true },
    { id: 'hs-1005', src: 'RustSec', time: '07:30', sev: 'med', mode: 'all', hint: null,
      title: 'RUSTSEC-2026-0031：axum-server TLS 握手拒绝服务',
      sum: '升级至 0.7.2 可修复；无已知在野利用。',
      tags: ['Rust', 'DoS'], likes: 5, dislikes: 0, fav: false, pick: 62.1, deep: false },
    { id: 'hs-1006', src: '安全客', time: '07:02', sev: 'med', mode: 'deep', hint: null,
      title: '云对象存储误配置泄露 2.3 亿条记录复盘',
      sum: '根因：匿名读策略 + 目录列举未关闭。附检查清单 12 条。',
      tags: ['云安全', '复盘'], likes: 8, dislikes: 0, fav: false, pick: 71.8, deep: true },
    { id: 'hs-1007', src: 'MITRE', time: '06:40', sev: 'info', mode: 'all', hint: null,
      title: 'ATT&CK v17 更新：云域新增 6 项技术、修订 11 项',
      sum: '涉及 T1583/T1587 收编与 Cloud Instance Metadata 相关改写。',
      tags: ['ATT&CK'], likes: 6, dislikes: 0, fav: false, pick: 55.0, deep: false },
    { id: 'hs-1008', src: 'FreeBuf', time: '06:11', sev: 'info', mode: 'all', hint: null,
      title: '信通院《AI 安全治理框架》征求意见稿发布',
      sum: '面向模型供应链、提示注入、代理权限三大域给出控制基线。',
      tags: ['合规', 'AI 安全'], likes: 3, dislikes: 1, fav: false, pick: 48.6, deep: false },
    { id: 'hs-1009', src: '奇安信', time: '05:52', sev: 'crit', mode: 'alert', hint: 'respond',
      title: '浏览器 0-day 在野利用通报（EPSS 0.88）',
      sum: '渲染进程 RCE，临时缓解：禁用 JIT。应急 SOP 已挂案件 case-0121。',
      tags: ['0-day', '浏览器'], likes: 31, dislikes: 0, fav: true, pick: 97.9, deep: true },
    { id: 'hs-1010', src: '先知社区', time: '05:20', sev: 'low', mode: 'all', hint: null,
      title: '某办公系统模板注入到权限提升的完整链分析',
      sum: '作者给出三条检测规则与一版 YARA。',
      tags: ['Web 安全'], likes: 4, dislikes: 0, fav: false, pick: 51.3, deep: false }
  ];

  /* ---------- v1 受管信号（SignalPanel，演示样例） ---------- */
  var SIGNALS = [
    { id: 'sig-1', from: 'hs-1001', t: 'OpenSSL CVE-2026-44127', k: '漏洞', conf: 0.94, case: 'case-0117' },
    { id: 'sig-2', from: 'hs-1002', t: 'Citrix KEV 入库', k: '漏洞', conf: 0.92, case: 'case-0117' },
    { id: 'sig-3', from: 'hs-1003', t: 'PyPI 供应链投毒', k: '供应链', conf: 0.88, case: 'case-0118' },
    { id: 'sig-4', from: 'hs-1004', t: 'ESXi 勒索 TTP 变化', k: '情报', conf: 0.81, case: null },
    { id: 'sig-5', from: 'hs-1009', t: '浏览器 0-day 应急', k: '事件', conf: 0.96, case: 'case-0121' }
  ];

  /* ---------- v1 案件（活体口径：6 案 1 闭，演示样例） ---------- */
  var CASES = [
    { id: 'case-0117', t: 'OpenSSL / Citrix 漏洞批量处置', kind: '运营', status: 'open',
      created: '2026-11-14', sigs: 2, mats: 2, judg: 1, acts: 1, runs: 2, arts: 1, kn: 0,
      guard: '执行型：需 run 终态 + artifact' },
    { id: 'case-0118', t: 'PyPI 供应链投毒排查', kind: '研究', status: 'in_progress',
      created: '2026-11-15', sigs: 1, mats: 1, judg: 0, acts: 0, runs: 1, arts: 0, kn: 0,
      guard: '研究型：published judgment 可旁路关闭' },
    { id: 'case-0119', t: 'ESXi 勒索情报跟踪', kind: '运营', status: 'open',
      created: '2026-11-15', sigs: 1, mats: 0, judg: 0, acts: 0, runs: 0, arts: 0, kn: 0,
      guard: '执行型' },
    { id: 'case-0120', t: '开源依赖 SBOM 缺口评估', kind: '合规', status: 'open',
      created: '2026-11-16', sigs: 0, mats: 1, judg: 0, acts: 1, runs: 1, arts: 1, kn: 0,
      guard: '执行型：需产物验收' },
    { id: 'case-0121', t: '浏览器 0-day 应急响应', kind: '运营', status: 'closed',
      created: '2026-11-14', sigs: 1, mats: 1, judg: 1, acts: 1, runs: 1, arts: 1, kn: 1,
      guard: '演练①：首个 closed case（四守卫全过）' },
    { id: 'case-0122', t: 'ATT&CK v17 标签映射研究', kind: '研究', status: 'open',
      created: '2026-11-16', sigs: 0, mats: 0, judg: 0, acts: 0, runs: 0, arts: 0, kn: 0,
      guard: '研究型' }
  ];

  /* ---------- 审批收件箱提案（演示样例） ---------- */
  var PROPOSALS = [
    { id: 'prop-201', type: 'judgment-draft@v1', actor: 'ai_hub（HEAVY）', case: 'case-0118',
      ev: 3, preview: '初判：pdf-math-tools 行为链为窃取型（读取 CI 凭据 → 外联 185.x）。建议判定「确认」并附 3 条证据…',
      write: true, ts: '10:02' },
    { id: 'prop-202', type: 'sk04-retro@v1', actor: 'retrospective_service', case: 'case-0121',
      ev: 4, preview: '复盘提案：0-day 应急时延 P50 4.2h，经验教训 3 条（禁用 JIT 缓解有效性、通报→处置路径、IOC 回灌）…',
      write: true, ts: '09:41' },
    { id: 'prop-203', type: 'execution-plan@v1', actor: 'ai_hub 起草 + 人工可改', case: 'case-0117',
      ev: 2, preview: 'ExecutionPlan v1：commands ×2（openssl version / cvsradar scan）· writable ./out · network 全禁 · timeout 300s · 产出 artifact',
      write: true, ts: '08:55' }
  ];

  /* ---------- Run / Artifact（活体口径 runs=4 artifacts=3） ---------- */
  var RUNS = [
    { id: 'run-301', case: 'case-0121', protocol: 'direct', status: 'done', outcome: 'done', by: '人工回执（人担保）', ts: '11-14 15:20' },
    { id: 'run-302', case: 'case-0117', protocol: 'argv（pi 执行体）', status: 'done', outcome: 'done', by: '边界内：sandbox-exec + ulimit', ts: '11-16 10:05' },
    { id: 'run-303', case: 'case-0118', protocol: 'direct', status: 'claimed', outcome: null, by: '已认领待 start', ts: '11-17 09:30' },
    { id: 'run-304', case: 'case-0117', protocol: 'argv', status: 'queued', outcome: null, by: 'plan 审批后可 claim', ts: '11-17 08:55' }
  ];
  var ARTIFACTS = [
    { id: 'art-401', case: 'case-0121', kind: 'md 判读报告', sha: '9f2c…a7', verified: true, ts: '11-14' },
    { id: 'art-402', case: 'case-0117', kind: '处置清单 md', sha: 'c41d…2e', verified: true, ts: '11-16' },
    { id: 'art-403', case: 'case-0120', kind: 'SBOM 缺口清单', sha: '77aa…0b', verified: true, ts: '11-16' }
  ];

  /* ---------- v1 知识（演示样例） ---------- */
  var KNOWLEDGE = [
    { id: 'k-501', t: 'ESXi 勒索处置清单', kind: 'playbook', status: 'published', review: '2027-02-15', adoptions: 1, src: 'case-0119 前案沉淀' },
    { id: 'k-502', t: '供应链事件复盘：窃取型依赖识别', kind: 'postmortem', status: 'draft', review: '+90d', adoptions: 0, src: 'case-0121 复盘提案（待批准）' },
    { id: 'k-503', t: '0-day 应急 playbook', kind: 'playbook', status: 'published', review: '2027-01-20', adoptions: 2, src: 'case-0121' }
  ];

  /* ---------- 能力包（SK-01~06 + 内置 20） ---------- */
  var SKILLS = [
    { id: 'SK-01', t: 'daily-priority-intel', zh: '每日优先情报', st: 'partial', note: '已接线；摘要缺原文/事项动作与 mode 展示' },
    { id: 'SK-02', t: 'cve-impact-brief', zh: 'CVE 影响简报', st: 'ok', note: 'generate→draft→publish' },
    { id: 'SK-03', t: 'inspection-materials', zh: '排查材料生成', st: 'ok', note: '执行体由 v0.8.9 落地' },
    { id: 'SK-04', t: 'action-retrospective', zh: '行动复盘', st: 'ok', note: '提案化 + 事件直连（演练⑥ PASS）' },
    { id: 'SK-05', t: 'reuse-experience', zh: '经验复用召回', st: 'ok', note: 'auto_recall_for_case + adoption 回执' },
    { id: 'SK-06', t: 'knowledge-review-due', zh: '知识复查到期', st: 'ok', note: 'job 55 · case blocker' },
    { id: 'BUILTIN', t: '内置技能 ×20', zh: '8 ops / 6 compliance / 4 analysis / 2 report', st: 'ok', note: 'builtin.py 单例' }
  ];

  /* ---------- KPI / 观测（口径：XF-22/ACT-18/19） ---------- */
  var KPI = {
    triageP50: '4.2h', triageP90: '11.8h', yieldRatio: '1.0',
    runs: 4, artifacts: 3, casesOpen: 5, casesClosed: 1,
    window: { t0: '2026-11-14', t1: '2026-12-14', state: '观测中' },
    gates24h: { pass: 96, reject: 32, flag: 12, gateError: 0 }
  };

  /* ---------- 校对室 / 门禁（演示样例） ---------- */
  var QUALITY = {
    rules: { builtin: 11, expert: 5, ai: 2 },
    samples: [
      { flag: 'content_hash_duplicate', say: '与已有条目正文完全重复（哈希一致）', raw: true },
      { flag: 'title_too_short', say: '标题过短（<8 字），信息量不足', raw: true },
      { flag: 'source_offline_30d', say: '来源近 30 天不可达，内容可信度存疑', raw: false }
    ]
  };

  /* ---------- /maint 四卡（权威契约口径） ---------- */
  var MAINT = {
    health: { sizeMb: '111.2', freelist: 1480, frag: '2.1%', qclOlder: 0 },
    tiers: [{ d: 7, rows: 2143, est: '18.4MB' }, { d: 14, rows: 1980, est: '17.1MB' }, { d: 21, rows: 1832, est: '15.8MB' }],
    index: { user: 412, auto: 296, integrity: 'ok' },
    backups: { full: 1, inc: 2, last: '2026-11-17 04:00', note: '滚动保留：1 全量 + ≤3 增量' }
  };

  /* ---------- 设置运维区：失败面板 + 告警（演示样例） ---------- */
  var OPS = {
    failures: [
      { ts: '09:12', obj: 'job telemetry_window', sev: 'warn', why: 'skip：warm.db 未建（单库起步合法态）', retry: false },
      { ts: '07:58', obj: 'run-302 argv cmd#2', sev: 'critical', why: 'executor.boundary_violation：写越界 spawn 前拦截（演练④）', retry: false },
      { ts: '07:31', obj: 'collector RustSec', sev: 'warn', why: 'HTTP 503，重试 1/3', retry: true }
    ],
    dsh: { state: 'not_configured→mock→ai_hub', port: '3210（受管子进程）' },
    mcp: { tools: 23, read: 16, write: 7, gate: false }
  };

  /* ---------- 前厅 hub-stats 六源 ---------- */
  var HUB = [
    { t: '编目', v: '7,734', u: 'wiki 条目' }, { t: 'Chunks', v: '31,206', u: '检索切片' },
    { t: '复习', v: '46', u: '今日到期' }, { t: '漏斗', v: '96/128', u: '准入/收录' },
    { t: '队列', v: '12+3+1', u: '待处理/运行/错误' }, { t: '门禁', v: '32 拒 / 24h', u: '误拒可回放' }
  ];

  /* ---------- MP / 图谱 ---------- */
  var GRAPH = { techniques: 244, cweMap: 714, edges: 17616, eventTypes: 11, pending: 23, approved: 148 };

  return { PIPE: PIPE, META: META, FEED: FEED, SIGNALS: SIGNALS, CASES: CASES, PROPOSALS: PROPOSALS, RUNS: RUNS, ARTIFACTS: ARTIFACTS, KNOWLEDGE: KNOWLEDGE, SKILLS: SKILLS, KPI: KPI, QUALITY: QUALITY, MAINT: MAINT, OPS: OPS, HUB: HUB, GRAPH: GRAPH };
})();
