/* ============================================================
 * Hotspot 全站重构 demo — 视图层（富视图 + 通用档案视图 + 覆盖地图）
 * 依赖：registry.js (window.HS) / data.js (window.HD) / app.js 提供 window.App
 * 所有视图输出 HTML 字符串；交互经 App.* 全局函数（事件内联绑定）。
 * ============================================================ */
window.HV = (function () {
  'use strict';
  var HS = window.HS, HD = window.HD;

  /* ---------- 基础 helper ---------- */
  function esc(s) {
    return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }
  var CAP_MAP = {};
  HS.CAPS.forEach(function (c) { CAP_MAP[c.id] = c; });

  function badge(s) {
    if (s === 'ok') return '<span class="badge b-ok">✅ 已上线</span>';
    if (s === 'partial') return '<span class="badge b-part">◐ 部分就绪</span>';
    if (s === 'none') return '<span class="badge b-none">○ 未实现</span>';
    if (s === 'disc') return '<span class="badge b-disc">◈ 纪律生效</span>';
    if (s === 'redirect') return '<span class="badge b-disc">↷ 重定向兼容</span>';
    return '';
  }
  function capBadge(id) {
    var c = CAP_MAP[id]; if (!c) return '';
    return '<span class="badge b-id" title="' + esc(c.d) + '｜' + esc(c.prd) + '">' + id + '</span>';
  }
  /* 未实现/部分 印章：按 CAPS id 或自定义 */
  function stamp(id) {
    var c = CAP_MAP[id]; if (!c) return '';
    var cls = c.s === 'none' ? 'stamp' : 'stamp st-part';
    var mark = c.s === 'none' ? '○' : '◐';
    var t = c.s === 'none' ? '未实现 · ' + id : '部分就绪 · ' + id;
    return '<div class="' + cls + '"><div class="st-mark">' + mark + '</div><div class="st-body">' +
      '<div class="st-t">' + t + ' — <span class="sans">' + esc(c.d) + '</span></div>' +
      (c.s !== 'none' ? '<div class="st-d">' + esc(c.ui) + '</div>' : '') +
      '<div class="st-e">依据：' + esc(c.prd) + ' ｜ demo 落点：' + esc(c.ui) + '</div></div></div>';
  }
  function stampRaw(mark, cls, title, desc, ev) {
    return '<div class="stamp ' + cls + '"><div class="st-mark">' + mark + '</div><div class="st-body">' +
      '<div class="st-t">' + mark + ' ' + title + '</div><div class="st-d">' + desc + '</div>' +
      '<div class="st-e">依据：' + ev + '</div></div></div>';
  }
  function pageHead(o) {
    return '<div class="pg-head"><span class="pg-no">' + o.no + '</span>' +
      '<h1 class="pg-title">' + o.title + '</h1>' +
      '<div style="padding-bottom:4px">' + (o.badges || '') + '</div>' +
      '<div class="pg-meta num">' + (o.meta || '') + '</div></div>' +
      (o.sub ? '<p class="pg-sub">' + o.sub + '</p>' : '');
  }
  function cardH(t, extra) {
    return '<div class="card-h"><span class="ct">' + t + '</span>' + (extra || '') + '</div>';
  }
  function tbl(heads, rows, cls) {
    var h = heads.map(function (x) { return '<th' + (x.r ? ' class="r"' : '') + '>' + x.t + '</th>'; }).join('');
    var b = rows.map(function (r) {
      return '<tr>' + r.map(function (c) { return '<td' + (c && c.r ? ' class="r"' : '') + '>' + (c && c.h != null ? c.h : esc(c)) + '</td>'; }).join('') + '</tr>';
    }).join('');
    return '<table class="tbl ' + (cls || '') + '"><thead><tr>' + h + '</tr></thead><tbody>' + b + '</tbody></table>';
  }
  function kv(pairs) {
    return '<dl class="kv">' + pairs.map(function (p) { return '<dt>' + p.k + '</dt><dd>' + p.v + '</dd>'; }).join('') + '</dl>';
  }
  function demoPath(p) {
    return p.replace(':caseId', 'case-0117').replace(':skillId', 'SK-01')
      .replace(':type/:id', 'hotspot/hs-1001').replace(':id', 'k-503').replace(':cat', 'security');
  }
  var CLS_VAR = { 'st-ok': 'mint', 'st-warn': 'amber', 'st-bad': 'red' };
  function statTile(k, v, u, cls) {
    var cv = cls && CLS_VAR[cls] ? 'color:var(--' + CLS_VAR[cls] + ')' : '';
    return '<div class="card"><div class="pipe-k">' + k + '</div><div class="num" style="font-size:22px;font-weight:700;margin:4px 0 2px;' + cv + '">' + v + '</div><div class="faint" style="font-size:10.5px">' + u + '</div></div>';
  }

  /* ---------- §01 首页（情报流） ---------- */
  function feedList(mode) {
    var items = HD.FEED.slice();
    if (mode === 'pick') items = HD.FEED.slice().sort(function (a, b) { return b.pick - a.pick; }).slice(0, 4);
    if (mode === 'deep') items = items.filter(function (x) { return x.deep; });
    if (mode === 'alert') items = items.filter(function (x) { return x.mode === 'alert'; });
    var st = window.App ? window.App.S : {};
    return '<div class="feed">' + items.map(function (x) {
      var like = st.likes && st.likes[x.id], dis = st.dislikes && st.dislikes[x.id], fav = st.favs && st.favs[x.id] != null ? st.favs[x.id] : x.fav;
      return '<div class="feed-card"><div class="sev ' + esc(x.sev) + '"></div><div class="fc-body">' +
        '<div class="fc-meta"><span class="tag cat-general">' + esc(x.src) + '</span><span class="num">' + esc(x.time) + '</span>' +
        '<span class="badge b-id">pick ' + x.pick.toFixed(1) + '</span>' +
        (x.mode === 'alert' && x.hint ? '<span class="hint-chip">' + esc(x.hint) + '</span>' : '') +
        (x.mode === 'deep' ? '<span class="badge b-part">深度候选</span>' : '') + '</div>' +
        '<div class="fc-title sans" onclick="App.go(\'/deep/hotspot/' + x.id + '\')">' + esc(x.title) + '</div>' +
        '<div class="fc-sum">' + esc(x.sum) + '</div>' +
        '<div class="fc-foot">' +
        '<button class="react ' + (like ? 'on-like' : '') + '" onclick="App.react(\'' + x.id + '\',\'like\')">▲ <span class="num">' + x.likes + '</span></button>' +
        '<button class="react ' + (dis ? 'on-dis' : '') + '" onclick="App.react(\'' + x.id + '\',\'dis\')">▼ <span class="num">' + x.dislikes + '</span></button>' +
        '<button class="react ' + (fav ? 'on-like' : '') + '" onclick="App.fav(\'' + x.id + '\')">★ 收藏</button>' +
        '<button class="react" onclick="App.toast(\'演示：建案 = 类型识别 → AI 预填 → 用户确认（人主律），本 demo 不落库\', \'t-warn\')">→ 建案（用户确认）</button>' +
        '<span style="margin-left:auto" class="row">' + x.tags.map(function (t) { return '<span class="tag">' + esc(t) + '</span>'; }).join('') + '</span>' +
        '</div></div></div>';
    }).join('') + '</div>';
  }

  var VIEWS = {};

  VIEWS.home = function () {
    var mode = window.App ? window.App.S.mode : 'all';
    var alertN = HD.FEED.filter(function (x) { return x.mode === 'alert'; }).length;
    var sigs = HD.SIGNALS.map(function (s) {
      return '<div class="stage-item"><div class="si-t">' + esc(s.t) + '</div><div class="si-m">' + esc(s.k) + ' · 置信 <span class="num">' + s.conf.toFixed(2) + '</span> · ← ' + esc(s.from) + '</div>' +
        '<div class="si-actions">' + (s.case ? '<button class="btn btn-sm" onclick="App.go(\'/cases/' + s.case + '\')">案件 ' + s.case + '</button>' : '<button class="btn btn-sm btn-w" onclick="App.toast(\'演示：建项须经用户确认（人主律），本 demo 不落库\',\'t-warn\')">+ 立案</button>') + '</div></div>';
    }).join('');
    return pageHead({ no: '§01 · 资讯', title: '情报流首页', badges: badge('ok') + capBadge('DATA-2') + capBadge('DATA-5'),
      sub: '四阅读模式各有后端语义：全量 = 当轮收录全部资讯；精选 = pick_score Top-30；深度 = 精读候选 + 收藏自选；告警 = 需读者执行动作（pi 复核 action_hint）。', meta: 'SentinelHomePage<br>/api/hotspots · /api/alerts/v2' }) +
      '<div class="row between mt2"><div class="mode-tabs">' +
      [['all', '全量'], ['pick', '精选'], ['deep', '深度'], ['alert', '告警']].map(function (m) {
        return '<button class="' + (mode === m[0] ? 'on' : '') + '" onclick="App.setMode(\'' + m[0] + '\')">' + m[1] + (m[0] === 'alert' ? ' <span class="num">' + alertN + '</span>' : '') + '</button>';
      }).join('') + '</div><div class="mode-tabs"><button class="' + (mode === 'fav' ? 'on' : '') + '" onclick="App.setMode(\'fav\')">★ 收藏自选</button></div></div>' +
      '<div class="grid2 mt3" style="grid-template-columns:1.6fr 1fr"><div>' +
      (mode === 'fav'
        ? '<div class="card">' + cardH('收藏自选（深度模式并集）') + feedList('deep') + '</div>'
        : '<div class="card pad0">' + cardH(mode === 'alert' ? '告警 · 需读者执行动作' : mode === 'pick' ? '精选 · pick_score Top-30' : mode === 'deep' ? '深度 · 精读候选' : '全量 · 当轮收录') + '<span class="cx num">演示样例 · 非真实数据</span><div style="border-top:1px solid var(--line)">' + feedList(mode) + '</div></div>') +
      '</div><div class="stack">' +
      '<div class="card digest">' + cardH('每日优先情报摘要 <span class="cx">SK-01 · PriorityDigestCard</span>') +
        '<div class="dg-mode st-warn">响应 mode：<b>live</b>（本 demo 假设为 live；真实实现未展示 mode/降级原因）</div>' +
        '<div class="mt1" style="font-size:12px;color:var(--ink-2)">今日 Top-3：① OpenSSL CVE-2026-44127（patch）② PyPI 供应链投毒（investigate）③ 浏览器 0-day（respond）</div>' +
        stampRaw('◐', 'st-part', '部分就绪 · SK-01 摘要', '摘要缺原文链接与事项承接动作；降级原因展示缺口。', '主PRD §2.4 / §3.4（DATA-9 / DATA-10）') + '</div>' +
      '<div class="card">' + cardH('受管信号 <span class="badge b-id">v1 SignalPanel · 只读</span>') + sigs + '</div>' +
      '<div class="card">' + cardH('门禁速览') + kv([{ k: '24h 通过', v: '<span class="num">' + HD.KPI.gates24h.pass + '</span>' },
      { k: '24h 拒绝', v: '<span class="num st-warn">' + HD.KPI.gates24h.reject + '</span> → <a href="#/settings?cat=ops" style="color:var(--info);border-bottom:1px dotted">拒收日志</a>' },
      { k: 'gate_error', v: '<span class="num st-ok">' + HD.KPI.gates24h.gateError + '</span>（失败必可见，DEV-0286）' }]) + '</div>' +
      '</div></div>' +
      stamp('DATA-8');
  };

  /* ---------- §02 知识库 ---------- */
  VIEWS.knowledge = function () {
    var kn = HD.KNOWLEDGE.map(function (k) {
      return '<tr><td class="mono">' + k.id + '</td><td><a href="#/reader/' + k.id + '" style="color:var(--info)">' + esc(k.t) + '</a></td><td>' + esc(k.kind) + '</td><td>' + badge(k.status === 'published' ? 'ok' : 'partial').replace('已上线', k.status === 'published' ? 'published' : 'draft') + '</td><td class="r num">' + esc(k.review) + '</td><td class="r num">' + k.adoptions + '</td></tr>';
    }).join('');
    return pageHead({ no: '§02 · 知识', title: '知识库', badges: badge('ok') + capBadge('KNOW-1') + capBadge('KNOW-2'),
      sub: 'wiki-first：Markdown 真源 + FTS 检索（7,734 条）。v1 知识对象支持发布 / 复查 / 采用；复盘回流由 case 关闭事件直连（SK-04，演练⑥ PASS）。', meta: 'KnowledgePage（嵌套壳）<br>默认子路由 → /knowledge/import' }) +
      '<div class="row mt2">' + ['前厅 /knowledge/khub', '编目室 /knowledge/library', '图谱 /knowledge/graph', '复习 /reviews', '能力包 /skill-store', '导入 /knowledge/import', '编译 /knowledge/compile', '复利 /knowledge/compound'].map(function (x) {
        var p = x.split(' ')[1], t = x.split(' ')[0];
        return '<button class="chip" onclick="App.go(\'' + p + '\')">' + t + '</button>';
      }).join('') + '</div>' +
      '<div class="grid2 mt3"><div class="card pad0">' + cardH('v1 知识目录 <span class="cx">/knowledge/v1</span>') +
        tbl([{ t: 'ID' }, { t: '标题' }, { t: 'kind' }, { t: '状态' }, { t: '复查 at', r: 1 }, { t: '采用', r: 1 }], []) .replace('<tbody></tbody>', '<tbody>' + kn + '</tbody>') + '</div>' +
      '<div class="stack"><div class="card">' + cardH('SK-04 复盘回流 <span class="badge b-ok">演练⑥ PASS</span>') +
        '<div style="font-size:12px;color:var(--ink-2)">case 关闭 → <span class="mono">v1_case_closed</span> → 复盘提案（人主律，仅起草）→ 人批准 → knowledge <b>draft</b>（playbook，review_at=+90d）→ publish（CAS + wiki-first）→ 同类召回。</div>' +
        '<div class="row mt2"><button class="btn btn-sm" onclick="App.go(\'/cases/case-0121\')">看演练① case</button><button class="btn btn-sm" onclick="App.toast(\'演示：回流链已闭合（DEV-0388），延迟 0.008–0.015s\',\'\')">链路演示</button></div></div>' +
        stamp('KNOW-6') + stamp('KNOW-13') + '</div></div>';
  };

  VIEWS.khub = function () {
    return pageHead({ no: '§02.1 · 知识', title: '资料库前厅', badges: badge('ok') + capBadge('KNOW-7'),
      sub: '六源聚合统计，逐源容错（单源失败置 …，前端不展示伪造数据）。', meta: 'KnowledgeHubPage<br>/api/knowledge/hub-stats' }) +
      '<div class="grid3 mt3">' + HD.HUB.map(function (h) { return statTile(h.t, h.v, h.u); }).join('') + '</div>' +
      '<div class="card mt3">' + cardH('口径说明') + '<div style="font-size:12px;color:var(--ink-2)">不落缓存（DD-6）：全只读聚合、单请求直算。hub-stats 曾是全仓最后一个后端缺口（DEV-0185 登记），C3/DEV-0191 闭环。</div></div>';
  };

  VIEWS.graph = function () {
    var g = HD.GRAPH;
    return pageHead({ no: '§02.2 · 知识', title: '知识图谱', badges: badge('ok') + capBadge('KNOW-9'),
      sub: 'SVG 直排为默认降级；画布模式沿用共享 InfiniteCanvas（拖拽平移 / 光标锚定缩放 / 双击重置 / 点阵网格）。', meta: 'SentinelGraphPage<br>graph 域（/api 根前缀）' }) +
      '<div class="row mt2"><span class="faint" style="font-size:11px">MP-1 已点火：</span><span class="tag">attack_techniques <span class="num">' + g.techniques + '</span></span><span class="tag">attack_cwe_map <span class="num">' + g.cweMap + '</span></span><span class="tag">security_edges <span class="num">' + g.edges.toLocaleString() + '</span></span></div>' +
      '<div class="graph-wrap mt3"><button class="btn btn-sm canvas-toggle" onclick="App.openCanvas()">▦ 打开无限画布</button>' +
      '<svg class="graph-svg" viewBox="0 0 900 420">' +
      '<line class="ge" x1="140" y1="210" x2="320" y2="120"/><line class="ge" x1="140" y1="210" x2="320" y2="210"/><line class="ge hot" x1="320" y1="210" x2="500" y2="210"/><line class="ge" x1="500" y1="210" x2="680" y2="140"/><line class="ge" x1="500" y1="210" x2="680" y2="280"/><line class="ge" x1="680" y1="280" x2="810" y2="210"/>' +
      [['资讯 14,503', 60, 185, 120], ['信号 / Case', 300, 95, 130], ['研判 · 行动', 480, 185, 130], ['ATT&CK 244', 660, 115, 130], ['Artifact ×3', 660, 255, 130], ['知识 7,734', 770, 185, 110]].map(function (n) {
        return '<g class="gn"><rect x="' + n[1] + '" y="' + n[2] + '" rx="6" width="' + n[3] + '" height="44"></rect><text x="' + (n[1] + 12) + '" y="' + (n[2] + 27) + '">' + esc(n[0]) + '</text></g>';
      }).join('') + '</svg></div>' +
      '<div class="grid2 mt3"><div>' + stampRaw('○', '', '未实现 · MP-3 L1 漏洞绑 CVE', 'NVD 接入 + CVE→technique 标注 + 资讯继承标签，未启动。', '主PRD §2.5 ❌ / §5.3') + '</div><div>' +
      stampRaw('○', '', '未实现 · MP-4 L3 响应 + 双向关联', 'knowledge_technique_ref 表未建；get_knowledge_for_techniques() 返回空列表（Stub）。', '主PRD §2.5 ⚠️ / §5.3') + '</div></div>' +
      '<div class="card mt3">' + cardH('MP-2 事件类型 <span class="badge b-part">候选池人审进行中</span>') +
      kv([{ k: '词表', v: '<span class="num">11 类</span>（migration 135 补种 B/C/D/E）' },
      { k: '候选池', v: 'pending <span class="num">' + g.pending + '</span> · 已审定 <span class="num">' + g.approved + '</span>' },
      { k: '审定入口', v: '<a href="#/action/events" style="color:var(--info)">/action/events 通稿审核</a>（七端点全接，DEV-0328 四段断裂修复）' }]) + '</div>';
  };

  /* ---------- §03 行动 ---------- */
  function consoleStages() {
    var runs = window.App.S.runs;
    function runItem(r) {
      var acts = '';
      if (r.status === 'queued') acts = '<button class="btn btn-sm" onclick="App.runAct(\'' + r.id + '\',\'claim\')">claim</button>';
      else if (r.status === 'claimed') acts = '<button class="btn btn-sm btn-p" onclick="App.runAct(\'' + r.id + '\',\'start\')">start</button><button class="btn btn-sm" onclick="App.runAct(\'' + r.id + '\',\'cancel\')">cancel</button>';
      else if (r.status === 'running') acts = '<button class="btn btn-sm btn-p" onclick="App.runAct(\'' + r.id + '\',\'finish\')">finish·done</button><button class="btn btn-sm btn-d" onclick="App.runAct(\'' + r.id + '\',\'fail\')">finish·failed</button><button class="btn btn-sm" onclick="App.runAct(\'' + r.id + '\',\'cancel\')">cancel</button>';
      else acts = '<span class="badge b-ok">outcome=' + esc(r.outcome) + '</span> <button class="btn btn-sm" onclick="App.runAct(\'' + r.id + '\',\'redo409\')">重复 finish → 409 演示</button>';
      return '<div class="stage-item"><div class="si-t">' + r.id + ' <span class="badge b-id">' + esc(r.protocol) + '</span></div>' +
        '<div class="si-m">' + esc(r.case) + ' · ' + esc(r.by) + ' · <span class="num">' + esc(r.ts) + '</span></div>' +
        '<div class="si-actions">' + acts + '</div></div>';
    }
    return '<div class="console">' +
      '<div class="stage"><div class="stage-h"><span class="no">①</span><span class="tt">信号 · 立案</span><span class="cnt num">' + HD.SIGNALS.length + '</span></div>' +
      HD.SIGNALS.slice(0, 3).map(function (s) { return '<div class="stage-item"><div class="si-t">' + esc(s.t) + '</div><div class="si-m">置信 <span class="num">' + s.conf.toFixed(2) + '</span>' + (s.case ? ' · ' + s.case : '') + '</div></div>'; }).join('') +
      '<div class="stage-link">→ 受管信号只读（Signal 无写端点）；建案必须用户确认</div></div>' +
      '<div class="stage"><div class="stage-h"><span class="no">②</span><span class="tt">案件 · 研判</span><span class="cnt num">' + HD.CASES.length + '</span></div>' +
      HD.CASES.slice(0, 3).map(function (c) { return '<div class="stage-item"><div class="si-t">' + esc(c.t) + '</div><div class="si-m">' + c.id + ' · ' + esc(c.kind) + '型 · ' + esc(c.status) + '</div><div class="si-actions"><button class="btn btn-sm" onclick="App.go(\'/cases/' + c.id + '\')">工作区</button></div></div>'; }).join('') + '</div>' +
      '<div class="stage"><div class="stage-h"><span class="no">③</span><span class="tt">Run · 人工回执</span><span class="cnt num">' + runs.length + '</span></div>' +
      runs.slice(0, 3).map(runItem).join('') +
      '<div class="stage-link">CAS 状态迁移 · 人登记=人担保 · 重复终态 409</div></div>' +
      '<div class="stage"><div class="stage-h"><span class="no">④</span><span class="tt">产物 · 沉淀</span><span class="cnt num">' + HD.ARTIFACTS.length + '+' + HD.KNOWLEDGE.length + '</span></div>' +
      HD.ARTIFACTS.map(function (a) { return '<div class="stage-item"><div class="si-t">' + esc(a.kind) + '</div><div class="si-m">' + a.id + ' · sha256 ' + a.sha + ' · <span class="st-ok">已验证</span></div></div>'; }).join('') +
      '<div class="stage-link">Artifact 自动登记（body_hash）→ 知识回流</div></div></div>';
  }
  function approvalInbox() {
    return HD.PROPOSALS.map(function (p) {
      var st = window.App.S.props[p.id] || {};
      var act;
      if (st.state === 'approved') act = '<span class="badge b-ok">已批准（演示 · 未落库）</span>';
      else if (st.state === 'rejected') act = '<span class="badge b-none">已驳回：' + esc(st.reason || '') + '</span>';
      else if (st.state === 'confirm') act = '<span class="confirm-inline">确认批准 ' + esc(p.type) + '？<button class="btn btn-sm btn-w" onclick="App.propApprove(\'' + p.id + '\',2)">确认</button><button class="btn btn-sm" onclick="App.propApprove(\'' + p.id + '\',0)">取消</button></span>';
      else if (st.state === 'rejecting') act = '<span class="confirm-inline">驳回原因必填（≤200）：<input id="rej-' + p.id + '" style="width:180px;border:1px solid var(--line-strong);border-radius:4px;padding:2px 6px" maxlength="200"><button class="btn btn-sm btn-d" onclick="App.propReject(\'' + p.id + '\')">提交驳回</button></span>';
      else act = '<button class="btn btn-sm btn-w" onclick="App.propApprove(\'' + p.id + '\',1)">批准（两步）</button><button class="btn btn-sm btn-d" onclick="App.propApprove(\'' + p.id + '\',\'r\')">驳回</button>';
      return '<div class="prop"><div class="pr-head"><span class="pr-type">' + esc(p.type) + '</span><span class="badge b-id">' + p.id + '</span>' +
        '<span class="pr-meta">发起 ' + esc(p.actor) + ' · 案件 ' + esc(p.case) + ' · 证据 <span class="num">' + p.ev + '</span> 条 · <span class="num">' + esc(p.ts) + '</span></span></div>' +
        '<div class="pr-preview">' + esc(p.preview) + '</div>' +
        '<div class="pr-actions">' + act + '<span class="faint" style="font-size:10.5px">写操作橙标 · 批准两步内联确认 · 驳回原因必填</span></div></div>';
    }).join('');
  }
  VIEWS.action = function () {
    var k = HD.KPI;
    var queue = HD.CASES.map(function (c) {
      return '<tr><td class="mono">' + c.id + '</td><td><a href="#/cases/' + c.id + '" style="color:var(--info)">' + esc(c.t) + '</a></td><td>' + esc(c.kind) + '</td><td>' + (c.status === 'closed' ? '<span class="badge b-ok">closed</span>' : '<span class="badge b-part">' + esc(c.status) + '</span>') + '</td><td class="r num">' + c.runs + '</td><td class="r num">' + c.arts + '</td></tr>';
    }).join('');
    return pageHead({ no: '§03 · 行动', title: '今日行动', badges: badge('ok') + capBadge('ACT-5') + capBadge('ACT-6'),
      sub: '四段执行指挥台（信号立案 → 案件研判 → Run 人工回执 → 产物沉淀）+ 审批收件箱（人主律）+ 副驾四卡。写操作全部走提案通道，未经人审批不得成为事实。', meta: 'SentinelActionPage<br>/api/v1/* · /api/kl/planning-actions' }) +
      '<div class="grid4 mt2">' +
      statTile('分诊时延 P50', k.triageP50, 'signal→case（KPI 主指标）') +
      statTile('分诊时延 P90', k.triageP90, '观测窗 ' + k.window.t0 + ' → ' + k.window.t1) +
      statTile('artifact 产出率', k.yieldRatio, 'done 且有产物 / done', 'st-ok') +
      statTile('Run / Artifact', k.runs + ' / ' + k.artifacts, '30 天目标 ≥10 / ≥5 · G1 观测中', 'st-warn') + '</div>' +
      '<div class="sec-title"><span class="no">SEC·1</span>四段执行指挥台（R-15）</div>' + consoleStages() +
      '<div class="sec-title"><span class="no">SEC·2</span>审批收件箱 <span class="badge b-id">ApprovalInbox</span></div><div class="card">' + approvalInbox() + '</div>' +
      '<div class="sec-title"><span class="no">SEC·3</span>AI 副驾四卡 <span class="badge b-id">CopilotCards · 全走提案通道</span></div>' +
      '<div class="copilot"><div class="cp"><b>研判建议</b>judgment-draft@v1 · HEAVY 档</div><div class="cp"><b>知识摘要</b>条件化经验浮出</div><div class="cp"><b>证据召回</b>SK-05 auto_recall</div><div class="cp"><b>SK-04 复盘</b>case 关闭事件直连</div></div>' +
      '<div class="sec-title"><span class="no">SEC·4</span>事项队列 <span class="badge b-id">CaseQueuePanel</span></div>' +
      '<div class="card pad0">' + tbl([{ t: 'ID' }, { t: '标题' }, { t: '类型' }, { t: '状态' }, { t: 'Run', r: 1 }, { t: '产物', r: 1 }], []) .replace('<tbody></tbody>', '<tbody>' + queue + '</tbody>') + '</div>' +
      stamp('ACT-17') +
      '<div class="sec-title"><span class="no">SEC·5</span>间隔复习 <span class="badge b-id">SM-2</span></div>' +
      '<div class="card row between"><span>今日到期 <b class="num">46</b> 条 · 复习承接行动页（planning-actions）</span><button class="btn" onclick="App.go(\'/reviews\')">开始复习</button></div>' +
      stamp('ACT-13') + stamp('ACT-14');
  };

  /* ---------- §03.1 案件工作区 ---------- */
  VIEWS.case = function (params) {
    var id = params[0] || 'case-0117';
    var c = HD.CASES.filter(function (x) { return x.id === id; })[0] || HD.CASES[0];
    var tab = window.App.S.caseTab || 'overview';
    var tabs = ['overview', 'evidence', 'judgments', 'actions', 'artifacts', 'review'];
    var body = '';
    if (tab === 'overview') body = '<div class="grid2"><div class="card">' + cardH('聚合（/aggregate）') +
      kv([{ k: '类型', v: esc(c.kind) + '型事项' }, { k: '状态', v: esc(c.status) }, { k: '创建', v: '<span class="num">' + c.created + '</span>' },
      { k: '链路计数', v: '信号 <span class="num">' + c.sigs + '</span> · 材料 <span class="num">' + c.mats + '</span> · 判断 <span class="num">' + c.judg + '</span> · 行动 <span class="num">' + c.acts + '</span> · Run <span class="num">' + c.runs + '</span> · 产物 <span class="num">' + c.arts + '</span> · 知识 <span class="num">' + c.kn + '</span>' }]) + '</div>' +
      '<div class="card">' + cardH('关闭守卫') + '<div class="guard-box mt1"><b>' + esc(c.guard) + '</b><br>四守卫（演练⑤ N1~N4 全拦）：① published judgment（研究型旁路）② 无活跃 Run ③ Artifact 终态验收 ④ 知识回流提案状态。守卫不改语义只供弹药（D6）。</div>' +
      '<div class="row mt2"><button class="btn btn-w" onclick="App.toast(\'演示：关闭 = 真实 mutation，本 demo 不落库；守卫已反证演练（N1~N4）\',\'t-warn\')">关闭案件</button><button class="btn" onclick="App.toast(\'演示：关闭事件 v1_case_closed → 复盘提案已由事件直连（演练⑥）\',\'\')">查看回流</button></div></div></div>';
    if (tab === 'evidence') body = '<div class="card pad0">' + tbl([{ t: '材料' }, { t: '来源' }, { t: '证据回执' }, { t: '提交' }], [
      ['mat-011 · OpenSSL 公告原文', { h: 'NVD' }, { h: '<span class="evidence-ref">rcpt ev_91 幂等提交</span>' }, '11-14'],
      ['mat-012 · PyPI 包行为分析', { h: 'GitHub Advisory' }, { h: '<span class="evidence-ref">rcpt ev_92 幂等提交</span>' }, '11-15'],
      ['mat-013 · 应急 SOP 引用', { h: 'wiki' }, { h: '<span class="evidence-ref">rcpt ev_93 幂等提交</span>' }, '11-14']]) + '</div>' +
      '<div class="faint mt1" style="font-size:11px">evidence_receipts 为三类 receipt 之一：幂等提交；重复提交不产生第二行。</div>';
    if (tab === 'judgments') body = '<div class="card">' + cardH('Judgment <span class="badge b-id">同一 claim_type 同时只 1 个 published</span>') +
      '<div class="row mt1"><span class="badge b-ok">published</span><b class="sans">Citrix 路径遍历需 48h 内修补</b><span class="faint" style="font-size:11px">双签：AI 起草 + 人批准</span></div>' +
      '<div class="row mt2">' + [['ev_91', 'NVD 公告'], ['ev_92', 'KEV 条目'], ['ev_93', 'SOP 条款']].map(function (e) { return '<span class="evidence-ref">⛓ ' + e[0] + ' · ' + e[1] + '</span>'; }).join('') + '</div>' +
      '<div class="row mt3"><button class="btn" onclick="App.toast(\'演示：AI 起草 → proposal 落库（judgment-draft@v1）→ 审批收件箱\',\'\')">AI 起草研判</button><button class="btn btn-g" onclick="App.toast(\'演示：补证 = 关联 evidence receipt，不直写结论\',\'\')">补证</button></div></div>' +
      stamp('ACT-3');
    if (tab === 'actions') body = '<div class="card">' + cardH('Action') +
      kv([{ k: 'act-071', v: '生成排查清单（执行型）· <span class="badge b-part">running</span>' },
      { k: '收口', v: '<span class="mono">POST /api/v1/actions/{id}/finish</span>：running→succeeded/failed，校验关联 run 终态（ACT-7）' }]) +
      '<div class="row mt2"><button class="btn btn-w" onclick="App.toast(\'演示：收口校验 run-302=done → succeeded；本 demo 不落库\',\'t-warn\')">finish（收口）</button></div></div>';
    if (tab === 'artifacts') body = '<div class="stack">' + (function () { var mine = HD.ARTIFACTS.filter(function (a) { return a.case === c.id; }); return mine.length ? mine : HD.ARTIFACTS; })().map(function (a) {
      return '<div class="card row between"><span><b class="sans">' + esc(a.kind) + '</b> <span class="badge b-id">' + a.id + '</span> · sha256 <span class="mono num">' + a.sha + '</span></span><span class="row"><span class="badge b-ok">已验证（body_hash）</span><button class="btn btn-sm" onclick="App.toast(\'演示：验收 = Artifact 状态 CAS（revision+old_status）\',\'\')">验收</button></span></div>';
    }).join('') + '</div>' + '<div class="faint mt1" style="font-size:11px">Run→Artifact 自动登记（body_hash 落盘 sha256 == content_hash，演练②）；revision+old_status 原子比较（R09）。</div>';
    if (tab === 'review') body = '<div class="card">' + cardH('知识召回 <span class="badge b-id">SK-05 · auto_recall_for_case</span>') +
      '<div class="stage-item mt1"><div class="si-t">0-day 应急 playbook（k-503）</div><div class="si-m">published · 适用条件：浏览器类 0-day · 历史 2 次采用</div><div class="si-actions"><button class="btn btn-sm btn-w" onclick="App.toast(\'演示：采用 = 真实 adoption 回执（不以召回次数冒充复用）\',\'t-warn\')">采用并记录</button><button class="btn btn-sm" onclick="App.toast(\'演示：拒绝需记录原因\',\'\')">不适用</button></div></div>' +
      '<div class="faint mt1" style="font-size:11px">第二个同类 Case 自动浮现知识 + 1 条真实采用回执（G4）；适用条件与跨案验证仍在推进（KNOW-6）。</div></div>' +
      '<div class="card mt3">' + cardH('复盘提案 <span class="badge b-id">SK-04 事件直连</span>') +
      '<div style="font-size:12px;color:var(--ink-2)">关闭后 <span class="mono">v1_case_closed</span> → retrospective_service 幂等起草（exists_for_case）→ 人批准 → knowledge draft。</div></div>';
    return pageHead({ no: '§03.1 · 行动', title: '案件工作区 · ' + c.id, badges: badge('ok') + '<span class="badge b-id">' + esc(c.kind) + '型</span>',
      sub: esc(c.t) + '——九对象账本在此贯通：Signal→Case→Judgment/Action→Run→Artifact→Knowledge，全部写路径 CAS + receipt。', meta: 'CaseDetailPage（壳 layer=action）<br>?section= 深链定位' }) +
      '<div class="case-tabs">' + tabs.map(function (t) { return '<button class="' + (tab === t ? 'on' : '') + '" onclick="App.caseSection(\'' + t + '\')">' + t + '</button>'; }).join('') + '</div>' + body;
  };

  /* ---------- §04 设置 ---------- */
  function gatesCard() {
    var g = window.App.S.gates;
    return HS.GATES.map(function (x) {
      var on = g[x.k];
      return '<div class="gate-row"><span class="switch ' + (on ? 'on' : '') + '" onclick="App.toggleGate(\'' + x.k + '\')"></span>' +
        '<span class="gk">' + x.k + '</span>' + (on ? '<span class="badge b-ok">开</span>' : '<span class="badge b-none">关</span>') +
        (x.note ? '<span class="faint" style="font-size:10.5px">' + esc(x.note) + '</span>' : '') + '</div>';
    }).join('');
  }
  VIEWS.settings = function (params, q) {
    var cat = (q && q.cat) || window.App.S.cat || 'overview';
    window.App.S.cat = cat;
    var cats = [['overview', '总览', '系统'], ['general', '通用', '系统'], ['models', '模型', '配置'], ['collection', '采集与管线', '配置'], ['network', '代理', '配置'], ['connectivity', '同步 · MCP', '连接'], ['ops', '运维', '维护']];
    var side = cats.map(function (c) {
      return (c[0] === 'overview' || c[0] === 'models' || c[0] === 'connectivity' || c[0] === 'ops' ? '<div class="ss-group">' + c[2] + '</div>' : '') +
        '<button class="ss-item ' + (cat === c[0] ? 'on' : '') + '" onclick="App.go(\'/settings?cat=' + c[0] + '\')">' + c[1] + '</button>';
    }).join('');
    var body = '';
    if (cat === 'overview') body = '<div class="grid4">' +
      statTile('架构数字', HD.META.routers + ' routers', 'jobs ' + HD.META.jobs + ' · collectors ' + HD.META.collectors + ' · services ' + HD.META.services) +
      statTile('Feature Gates', '16', '开 15 · 关 1（mcp）') +
      statTile('前端路由', HD.META.routes, '页面 44 + 重定向 16 · 全 lazy') +
      statTile('观测窗', 'D' + Math.max(1, Math.ceil((Date.now() - new Date('2026-11-14T00:00:00+08:00').getTime()) / 86400000)) + '/30', 't0 2026-11-14 → 2026-12-14', 'st-warn') + '</div>' +
      '<div class="card mt3">' + cardH('后端就绪 · 前端未接 <span class="badge b-part">4 个 API 域</span>') +
      tbl([{ t: 'API' }, { t: '后端文件' }, { t: '说明' }], HS.UNCONSUMED.map(function (u) { return [{ h: '<span class="mono">' + u.api + '</span>' }, { h: '<span class="mono">' + u.file + '</span>' }, u.note]; })) + '</div>' +
      '<div class="card mt3">' + cardH('demo 辅助') + '<div class="row"><button class="btn" onclick="App.go(\'/coverage\')">🗺 覆盖地图（demo 辅助页）</button><button class="btn" onclick="App.openCanvas()">▦ 无限画布</button></div></div>';
    if (cat === 'general') body = '<div class="grid2"><div class="card">' + cardH('主题（三态）') +
      '<div class="row">' + [['light', 'Light 冷白'], ['dark', 'Dark 深海军'], ['paper', 'Paper 暖米黄']].map(function (t) {
        return '<button class="btn ' + (window.App.S.theme === t[0] ? 'btn-p' : '') + '" onclick="App.setTheme(\'' + t[0] + '\')">' + t[1] + '</button>';
      }).join('') + '</div><div class="faint mt1" style="font-size:11px">paper：暖米黄纸底 + 衬线标题（T8 三主题人工走查未闭项）。</div></div>' +
      '<div class="card">' + cardH('内容偏好 <span class="badge b-id">DATA-7 三层</span>') +
      kv([{ k: '自动层', v: '近 30d 赞/踩/浏览/收藏按类目聚合净分 · 零配置默认生效（5min TTL）' },
      { k: 'LLM 建议', v: '采纳才写入手动层（人主律）' },
      { k: '手动层', v: '三级：加强 / 默认 / 减弱 · 只升降不删' }]) + '</div></div>' +
      '<div class="sec-title"><span class="no">GATES</span>能力开关 · 16 gate 单源（SET-2）</div>' +
      '<div class="card pad0" style="padding:var(--space-2) var(--space-4)">' + gatesCard() + '</div>' +
      '<div class="faint mt1" style="font-size:11px">TOML 写入 + audit；HOTSPOT_FEATURE_GATES env 覆盖优先（409）。demo 中切换即时生效：bandnav chips / 路由可见性随之变化。</div>';
    if (cat === 'models') body = '<div class="card">' + cardH('Provider 链 <span class="badge b-ok">pi 主力（2026-09-27）</span>') +
      kv([{ k: 'default_provider', v: '<span class="mono">pi</span>（实弹 score 首链 provider=pi ok=1）' },
      { k: 'fallback_order', v: '<span class="mono">pi → ollama → sensenova → qwen → openai</span>（兜底不删除）' },
      { k: '档位路由', v: 'task_overrides 三档锚点（light 任务按 tier 分流）' },
      { k: '管线 LLM', v: '语义门禁 / 智能分类 / NER 三 gate · 单出口走 gateway（ai_hub 红线）' }]) + '</div>' +
      '<div class="card mt3">' + cardH('模型池 · 内置国产 9 平台') + '<div class="row">' + ['ollama', 'sensenova', 'qwen', 'openai', 'pi(claude-sonnet-4-5)', '…'].map(function (p) { return '<span class="tag">' + p + '</span>'; }).join('') + '</div><div class="faint mt1" style="font-size:11px">密钥保险箱（/secrets）+ /models 探测；pi models 留空 = 用 pi 默认上游。</div></div>';
    if (cat === 'collection') body = '<div class="card">' + cardH('自动入管（DEV-0231）') +
      kv([{ k: '今日已入管', v: '<span class="num">41</span> 条（漏斗：128 收录 → 96 准入 → 41 信号）' },
      { k: '采集 job', v: 'collect 错过补跑一次（misfire_grace ≥ 900s + max_instances=1）' }]) + '</div>' +
      '<div class="card mt3">' + cardH('管线 LLM 三 gate') +
      '<div class="gate-row"><span class="switch on"></span><span class="gk">semantic_filter</span><span class="badge b-ok">开</span><span class="faint" style="font-size:10.5px">post-ingest 化：热路径零 LLM，tick 尾补偿判别；失败 fail-open</span></div>' +
      '<div class="gate-row"><span class="switch on"></span><span class="gk">ai_classify</span><span class="badge b-ok">开</span><span class="faint" style="font-size:10.5px">规则 miss 才补 domain；批级预算 20</span></div>' +
      '<div class="gate-row"><span class="switch on"></span><span class="gk">pipeline_ner</span><span class="badge b-ok">开</span><span class="faint" style="font-size:10.5px">t1 打分成功后实体落 knowledge_items.entities</span></div></div>';
    if (cat === 'network') body = '<div class="card">' + cardH('代理') + '<div class="fld mt1"><label>HTTP(S) 代理</label><input value="http://127.0.0.1:7890（演示样例）"></div>' +
      '<div class="guard-box">出站边界提示：配置外部模型或 WebDAV 时，相关内容可离开本机——本地运行 ≠ 数据不出域（XF-25）。</div>' + stamp('XF-25') + '</div>';
    if (cat === 'connectivity') body = '<div class="grid2"><div class="card">' + cardH('WebDAV 同步（SET-5）') +
      kv([{ k: 'bundle', v: '仅打包 config namespace（settings_sync_allowed 白名单）' },
      { k: 'secret', v: 'webhook.secret 加密存储，不入明文 KV' },
      { k: '事务', v: 'apply_bundle 原子注入 / 中途失败整体回滚（XF-18）' }]) +
      '<div class="row mt2"><button class="btn" onclick="App.go(\'/sync\')">打开同步页</button></div></div>' +
      '<div class="card">' + cardH('MCP <span class="badge b-none">gate 关</span>') +
      kv([{ k: '工具', v: '<span class="num">23</span>（16 读 + 7 写，v0.8.7 只读导出 ×4）' },
      { k: '双开关', v: 'extension gate 管 /api/mcp/* 调试路由；server 本体 is_mcp_enabled() 读 config' },
      { k: '外部消费', v: '供外部 AI Agent 只读观测；无前端消费为设计意图' }]) + '</div></div>' +
      stamp('SET-9');
    if (cat === 'ops') body = '<div class="card pad0">' + cardH('失败面板 <span class="cx">过去 24h · 按严重度排序</span>') +
      tbl([{ t: '时间' }, { t: '对象' }, { t: '严重度' }, { t: '原因' }, { t: '' }], HD.OPS.failures.map(function (f) {
        return [f.ts, '<span class="mono">' + esc(f.obj) + '</span>', { h: f.sev === 'critical' ? '<span class="badge b-red">critical</span>' : '<span class="badge b-part">warn</span>' }, esc(f.why), { h: f.retry ? '<button class="btn btn-sm" onclick="App.toast(\'演示：重试 = 新 run record，不伪造成功\',\'\')">重试</button>' : '<span class="faint">—</span>' }];
      })) + '</div>' +
      '<div class="grid2 mt3"><div class="card">' + cardH('拒收日志 <span class="badge b-id">DATA-11 人话化</span>') +
      tbl([{ t: '机器 flag' }, { t: '人话解释' }, { t: '原文' }], HD.QUALITY.samples.map(function (s) {
        return ['<span class="mono">' + esc(s.flag) + '</span>', s.say, { h: s.raw ? '<button class="btn btn-sm" onclick="App.toast(\'演示：JOIN raw_items 回放；缺失则诚实「未留存」\',\'\')">回放</button>' : '<span class="faint">未留存</span>' }];
      })) + '</div>' +
      '<div class="card">' + cardH('dsh · 受管子进程（SET-14）') +
      kv([{ k: '降级链', v: '<span class="mono">' + HD.OPS.dsh.state + '</span>' }, { k: '端口', v: HD.OPS.dsh.port }, { k: 'vendor', v: '二进制不在树内（死路已裁决）→ 全链降 ai_hub' }]) + '</div></div>' +
      '<div class="sec-title"><span class="no">OBS</span>观测收口（ACT-18/19）</div>' +
      '<div class="card">' + kv([{ k: 'artifact_yield', v: '<span class="num st-ok">1.0</span>（口径修复：分母 outcome=\'done\'，D7）' },
      { k: 'M-9 / M-10', v: '七段 p95 / 埋点开销——<span class="badge b-part">观测中，t0=2026-11-14 → 2026-12-14 满窗判定</span>' },
      { k: 'G1 主干流量', v: 'runs <span class="num">' + HD.KPI.runs + '</span> / artifacts <span class="num">' + HD.KPI.artifacts + '</span>（目标 ≥10 / ≥5）——<b>不宣称达标</b>' },
      { k: 'tag v0.8.9', v: '留待 owner 授权（观测窗未满 + G1 未达）' }]) + '</div>' +
      stamp('ACT-18');
    return pageHead({ no: '§04 · 设置', title: '设置', badges: badge('ok') + capBadge('SET-1'),
      sub: '纯配置心智：只读监控 / 数据浏览 / 一次性动作不混入。7 cat / 5 组（修订注⑤）。', meta: 'SettingsPage<br>?cat=' + esc(cat) }) +
      '<div class="set-wrap mt2"><div class="set-side">' + side + '</div><div>' + body + '</div></div>';
  };

  /* ---------- §05 校对室 ---------- */
  VIEWS.quality = function () {
    var g = HD.KPI.gates24h, r = HD.QUALITY.rules;
    return pageHead({ no: '§05 · 资讯', title: '校对室', badges: badge('ok') + capBadge('XF-6'),
      sub: '门禁结果可解释：误收、误拒均可追踪。质量规则两层模型：11 内置 gate + 专家规则（零 LLM）+ AI 语义规则（fail-open 可见）。', meta: 'QualityDashboardPage<br>/api/quality/summary · /api/info-filter/rules' }) +
      '<div class="grid4 mt2">' + statTile('24h 通过', g.pass, '门禁放行') + statTile('24h 拒绝', g.reject, '可回放（observability）') +
      statTile('24h flag', g.flag, '标记不放行', 'st-warn') + statTile('gate_error', g.gateError, '失败必可见', 'st-ok') + '</div>' +
      '<div class="grid2 mt3"><div class="card pad0">' + cardH('规则表 <span class="cx">内置 ' + r.builtin + ' · 专家 ' + r.expert + ' · AI 语义 ' + r.ai + '</span>') +
      tbl([{ t: '规则' }, { t: '层' }, { t: '动作' }], [
        ['标题过短 / 正文过短', '内置', 'reject'],
        ['content_hash 去重', '内置', 'reject'],
        ['来源 30d 不可达', '内置', 'flag'],
        ['专家：YARA 相关性', '专家（5 matcher）', 'reject / flag'],
        ['AI：语义相关性 NL 判别', 'AI 语义（fail-open）', 'reject（隐藏+flag 可回溯）']]) + '</div>' +
      '<div class="card pad0">' + cardH('拒绝样本（人话解释优先）') + tbl([{ t: 'flag' }, { t: '解释' }, { t: '' }], HD.QUALITY.samples.map(function (s) {
        return ['<span class="mono">' + esc(s.flag) + '</span>', s.say, { h: s.raw ? '<button class="btn btn-sm" onclick="App.toast(\'演示：回放原文\',\'\')">回放</button>' : '<span class="faint">未留存</span>' }];
      })) + '</div></div>' +
      '<div class="sec-title"><span class="no">EMPTY</span>空状态四态（组件契约）</div>' +
      '<div class="empty4"><div class="e4"><b>loading</b>骨架屏占位（形状匹配布局）</div><div class="e4"><b>empty</b>真空态：明确「暂无数据」</div><div class="e4"><b>stale</b>数据陈旧：显示最后成功时间 + 刷新</div><div class="e4"><b>error</b>加载失败：显式错误 + 重试，不吞错</div></div>';
  };

  /* ---------- §06 管线观测 ---------- */
  VIEWS.pipeline = function () {
    var f = HD.PIPE.funnel, max = f.collected;
    function bar(label, v) {
      return '<div class="fn"><span class="faint">' + label + '</span><div class="bar"><i style="width:' + (v / max * 100) + '%"></i></div><span class="r num">' + v + '</span></div>';
    }
    return pageHead({ no: '§06 · 资讯', title: '管线观测', badges: badge('ok') + capBadge('DATA-1'),
      sub: '采集 → 质量门禁 → 内容门禁 → 规则筛选 → 准入 → 受管信号；失败三形态显式 outcome，gate_error 不冒充通过。', meta: 'PipelineView<br>/api/secnews/* · /api/kl/pipeline/stats' }) +
      '<div class="grid2 mt2"><div class="card">' + cardH('生命周期漏斗（今日）') +
      '<div class="funnel mt1">' + bar('collected', f.collected) + bar('admitted', f.admitted) + bar('signal', f.signal) + bar('case', f.case) + '</div>' +
      '<div class="faint mt2" style="font-size:11px">队列：pending <span class="num">' + HD.PIPE.queue.pending + '</span> · running <span class="num">' + HD.PIPE.queue.running + '</span> · error <span class="num">' + HD.PIPE.queue.error + '</span></div></div>' +
      '<div class="card">' + cardH('管线 LLM 能力（三 gate）') +
      '<div class="stage-item"><div class="si-t">语义门禁 semantic_filter</div><div class="si-m">规则 neutral → LLM verdict-only；失败 fail-open 保留；post-ingest 化（DEV-0289-F）</div></div>' +
      '<div class="stage-item"><div class="si-t">智能分类 ai_classify</div><div class="si-m">纯规则 miss → LLM 补 domain；词表严格校验；批级预算 20</div></div>' +
      '<div class="stage-item"><div class="si-t">NER 实体抽取 pipeline_ner</div><div class="si-m">t1 打分成功后实体落 knowledge_items.entities（迁移 119）</div></div></div></div>' +
      '<div class="sec-title"><span class="no">SRC</span>来源矩阵（16 灯 · DEV-0194）</div>' +
      '<div class="src-matrix">' + HD.PIPE.sources.map(function (s) {
        return '<div class="src-cell"><span class="src-dot ' + s.s + '"></span>' + esc(s.n) + '<span class="faint" style="margin-left:auto;font-size:10px">' + (s.s === 'ok' ? '在线' : s.s === 'retry' ? '重试' : '离线') + '</span></div>';
      }).join('') + '</div>' +
      stamp('DATA-19');
  };

  /* ---------- §07 维护 ---------- */
  VIEWS.maint = function () {
    var m = HD.MAINT;
    return pageHead({ no: '§07 · 设置', title: '维护诊断', badges: badge('ok') + capBadge('SET-8'),
      sub: '四卡全部按后端权威契约呈现（fail-loud 纪律）；「想象契约」四处已修正（DEV-0317~0324）。', meta: 'MaintPage<br>/api/maintenance/*（复用已注册端点）' }) +
      '<div class="grid2 mt2"><div class="card">' + cardH('健康卡') +
      kv([{ k: '数据库大小', v: '<span class="num">' + m.health.sizeMb + '</span> MB（热冷分层后 794→111）' },
      { k: '空闲页', v: '<span class="num">' + m.health.freelist + '</span> freelist_pages' },
      { k: '碎片率', v: '<span class="num">' + m.health.frag + '</span> %' },
      { k: '可清理行', v: '<span class="num st-ok">0</span>（超窗口档恒等，闭环归零）' }]) + '</div>' +
      '<div class="card">' + cardH('清理卡 · 三档滚动（台账 21 天）') +
      tbl([{ t: '档' }, { t: '行数', r: 1 }, { t: '估算', r: 1 }], m.tiers.map(function (t) { return ['近 <span class="num">' + t.d + '</span> 天', '<span class="num">' + t.rows.toLocaleString() + '</span>', t.est]; })) +
      '<div class="row mt2"><button class="btn btn-sm btn-w" onclick="App.toast(\'演示：归档至 COLD 表（可追溯 90 天），不删除历史\',\'t-warn\')">按档宽归档</button></div></div>' +
      '<div class="card">' + cardH('索引卡') +
      kv([{ k: '用户索引', v: '<span class="num">' + m.index.user + '</span>' }, { k: '自动索引', v: '<span class="num">' + m.index.auto + '</span>' },
      { k: 'integrity_check', v: '<span class="st-ok">' + m.index.integrity + '</span>（full 深度检查）' },
      { k: 'vacuum', v: '后自动复检，重建前后闭环' }]) + '</div>' +
      '<div class="card">' + cardH('备份卡 <span class="badge b-id">' + m.backups.note + '</span>') +
      kv([{ k: '链', v: '全量 <span class="num">' + m.backups.full + '</span> + 增量 <span class="num">' + m.backups.inc + '</span>' },
      { k: '最近', v: '<span class="num">' + m.backups.last + '</span>' },
      { k: '语义', v: '备份链退役后改「可重建」；compact = 页级 last-write-wins roll-forward' }]) +
      '<div class="row mt2"><button class="btn btn-sm" onclick="App.toast(\'演示：POST /backups/compact 手动入口\',\'\')">compact</button></div></div></div>';
  };

  /* ---------- §08 能力包 ---------- */
  VIEWS.skillstore = function () {
    return pageHead({ no: '§08 · 知识', title: '能力包 <span style="font-size:13px;font-weight:400;color:var(--ink-2)">Skill Store</span>', badges: badge('ok'),
      sub: '26 项技能（SK-01~06 v1 技能 + 20 内置）。六项 v1 技能以对应业务动作出现，不作为前台 SK 编号选择器。', meta: 'SkillStore<br>/api/skill-registry（v1 + legacy）' }) +
      '<div class="skill-grid mt3">' + HD.SKILLS.map(function (s) {
        return '<button class="skill-cell" style="text-align:left" onclick="App.go(\'/skill-store/' + s.id + '\')"><div class="sk-id">' + s.id + '</div><div class="sk-t">' + esc(s.zh) + ' <span class="mono faint" style="font-weight:400;font-size:10.5px">' + esc(s.t) + '</span></div>' +
          '<div class="sk-n">' + esc(s.note) + '</div><div class="mt1">' + badge(s.st) + '</div></button>';
      }).join('') + '</div>' +
      '<div class="faint mt2" style="font-size:11px">gate：skill_registry / user_skills / trigger_gate；能力中心统一管理（Phase 41 配置在 /skills）。</div>';
  };

  /* ---------- §09 清样深读 ---------- */
  VIEWS.reader = function (params) {
    var id = params[0] || 'k-503';
    var k = HD.KNOWLEDGE.filter(function (x) { return x.id === id; })[0] || HD.KNOWLEDGE[2];
    return pageHead({ no: '§09 · 知识', title: '清样深读 · ' + k.id, badges: badge('ok') + capBadge('KNOW-10'),
      sub: esc(k.t) + '——wiki 条目阅读流 + B+ 锚点批注（quote=高亮原文 ≤500 字 + range 偏移；渲染端四步解析，永不静默错放）。', meta: 'DeepReaderPage<br>/api/wiki/read · /api/annotations' }) +
      '<div class="reader-wrap mt3"><div class="card"><div class="reader-body">' +
      '<h2>0-day 应急 playbook</h2>' +
      '<p>通报确认后 15 分钟内完成分诊：确认受影响面（版本 × 资产）、确定缓解动作、开案。<mark>禁用 JIT 为有效临时缓解，需记录解除条件</mark>。处置动作必须经审批后执行，产物登记 Artifact。</p>' +
      '<p>经验教训：通报→处置路径的时延主要消耗在「受影响面确认」；<mark>IOC 应在处置完成后回灌采集管线</mark>，形成下一轮感知。</p>' +
      '<div class="anno">批注 · an-12（located）：JIT 缓解对旧渲染器无效，需同时收紧文件下载。</div>' +
      '</div></div>' +
      '<div class="anno-side"><div class="card">' + cardH('批注（三态）') +
      '<div class="an-item"><div class="an-st located">● 已定位</div>an-12 · JIT 缓解补充</div>' +
      '<div class="an-item"><div class="an-st moved">◐ 已迁移</div>an-11 · 原文段落位移，窗口重锚命中</div>' +
      '<div class="an-item"><div class="an-st stale">○ 未定位</div>an-09 · 原文已改，quote 失配（stale）</div>' +
      '<div class="row mt2"><button class="btn btn-sm btn-w" onclick="App.toast(\'演示：选区批注 = quote 主锚 + offset hint；不写 wiki md\',\'t-warn\')">选区批注</button></div>' +
      '<div class="faint mt2" style="font-size:10.5px">migration 118 加 quote 列；annotations API 为 v1.7 Phase 2 既有全 CRUD。</div></div></div></div>';
  };

  /* ---------- 覆盖地图（demo 辅助页） ---------- */
  VIEWS.coverage = function () {
    var counts = { ok: 0, partial: 0, none: 0, disc: 0 };
    HS.CAPS.forEach(function (c) { counts[c.s]++; });
    var total = HS.CAPS.length;
    function bar() {
      return '<div class="cov-bar"><i class="c-ok" style="width:' + (counts.ok / total * 100) + '%"></i><i class="c-part" style="width:' + (counts.partial / total * 100) + '%"></i><i class="c-none" style="width:' + (counts.none / total * 100) + '%"></i><i class="c-disc" style="width:' + (counts.disc / total * 100) + '%"></i></div>';
    }
    var domains = [['资讯 data', 'DATA'], ['知识 knowledge', 'KNOW'], ['行动 action', 'ACT'], ['设置 settings', 'SET'], ['跨切面', 'XF']];
    var domHtml = domains.map(function (d) {
      var rows = HS.CAPS.filter(function (c) { return c.id.indexOf(d[1]) === 0; }).map(function (c) {
        return '<tr><td class="mono">' + c.id + '</td><td>' + esc(c.d) + '</td><td>' + badge(c.s) + '</td><td class="mono faint" style="font-size:11px">' + esc(c.ui) + '</td><td class="faint" style="font-size:10.5px">' + esc(c.prd) + '</td></tr>';
      }).join('');
      return '<div class="sec-title"><span class="no">' + d[1] + '</span>' + d[0] + '（<span class="num">' + HS.CAPS.filter(function (c) { return c.id.indexOf(d[1]) === 0; }).length + '</span> 条）</div>' +
        '<div class="card pad0">' + tbl([{ t: 'ID' }, { t: '需求' }, { t: '状态' }, { t: 'demo 落点' }, { t: 'PRD 依据' }], []) .replace('<tbody></tbody>', '<tbody>' + rows + '</tbody>') + '</div>';
    }).join('');
    var routeRows = HS.ROUTES.map(function (r) {
      return '<tr><td class="mono"><a href="#' + demoPath(r.p) + '" style="color:var(--info)">' + esc(r.p) + '</a></td><td>' + esc(r.t) + '</td><td class="faint" style="font-size:11px">' + esc(r.c) + '</td><td>' + (r.m ? '<span class="badge b-id">' + r.m + '</span>' : '<span class="badge b-disc">无菜单</span>') + '</td><td>' + badge('ok') + '</td><td class="faint" style="font-size:10.5px">' + esc(r.api.join(' ')) + '</td></tr>';
    }).join('');
    var redRows = HS.REDIRECTS.map(function (r) {
      return '<tr><td class="mono">' + esc(r.p) + '</td><td class="mono">→ ' + esc(r.to) + '</td><td>' + esc(r.note) + '</td></tr>';
    }).join('');
    return pageHead({ no: '§AUX', title: '覆盖地图', badges: '<span class="badge b-part">demo 辅助页 · 非产品路由</span>',
      sub: '本页核对三件事：① 44 条页面路由 + 16 条重定向零遗漏零死链；② PRD 92 条能力 → demo 落点 → 状态；③ 4 个后端就绪前端未接的 API 域。数据源：frontend/src/routes/index.tsx 实测 + design/_research/*（2026-11-17）。', meta: 'routes 60 · caps ' + total }) +
      '<div class="grid4 mt2">' + statTile('能力 · 已上线', counts.ok, '/' + total) + statTile('能力 · 部分就绪', counts.partial, '部分/观测中', 'st-warn') +
      statTile('能力 · 未实现', counts.none, '页内以 ○ 印章标记', 'st-bad') + statTile('能力 · 纪律生效', counts.disc, '明确不做/持续有效') + '</div>' +
      '<div class="card mt3">' + bar() + '<div class="legend mt1"><span class="badge b-ok">✅ 已上线</span><span class="badge b-part">◐ 部分/后端就绪/观测中</span><span class="badge b-none">○ 未实现·规划</span><span class="badge b-disc">◈ 纪律生效（含 ↷ 重定向）</span></div></div>' +
      '<div class="sec-title"><span class="no">R</span>页面路由（44 · 全部 ✅ 组件实测存在）</div><div class="card pad0">' +
      tbl([{ t: '路径' }, { t: '页面' }, { t: '组件' }, { t: '菜单' }, { t: '状态' }, { t: '主要 API' }], []) .replace('<tbody></tbody>', '<tbody>' + routeRows + '</tbody>') + '</div>' +
      '<div class="sec-title"><span class="no">RD</span>重定向兼容（16 · 零死链）</div><div class="card pad0">' +
      tbl([{ t: '路径' }, { t: '去向' }, { t: '说明' }], []) .replace('<tbody></tbody>', '<tbody>' + redRows + '</tbody>') + '</div>' + domHtml +
      '<div class="foot">本 demo 为重构蓝本，非生产代码；实现落地须按 DESIGN.md 路线分批接入 frontend/src 并通过 CI 门禁。</div>';
  };

  /* ---------- 通用档案视图 ---------- */
  function wireframe(l) {
    var zones = {
      list: ['<b>工具栏</b>：筛选 / 搜索 / 刷新', '<b>列表</b>：44px 行 · 状态徽章 · 数字右对齐<div class="wf-rows"><i></i><i></i><i></i><i></i></div>', '<b>分页</b>：50/页 · hasNext 以本页条数判定'],
      table: ['<b>工具栏</b>：四维筛选（域/主题/类型/难度）', '<b>粘性表头 + 行 hover 仅背景色</b><div class="wf-rows"><i></i><i></i><i></i></div>', '<b>页脚</b>：total 口径如实标注'],
      detail: ['<b>页头</b>：对象身份 + 面包屑', '<b>主栏</b>：正文 / 属性 kv<div class="wf-rows"><i></i><i></i></div>', '<b>侧栏</b>：关联对象 + 动作'],
      board: ['<b>看板列</b>：状态泳道<div class="wf-rows"><i></i><i></i><i></i></div>', '<b>卡片</b>：标题 + 计数 + 徽章'],
      form: ['<b>表单</b>：32px 输入框 · label 关联<div class="wf-rows"><i></i></div>', '<b>预览 / 校验</b>：validate 端点先行', '<b>提交</b>：明确动词按钮'],
      stats: ['<b>指标瓦片</b>：tabular-nums<div class="wf-rows"><i></i><i></i></div>', '<b>图表</b>：severity 七档色板'],
      feed: ['<b>流卡片</b>：sev 色条 + 来源 + 时间', '<b>互动</b>：赞/踩/收藏（状态型）'],
      panel: ['<b>状态面板</b>：连接/冲突/历史', '<b>动作</b>：明确动词按钮'],
      status: ['<b>全屏状态页</b>：结果 + 返回入口', '<b>回调安全</b>：一次性令牌消费']
    }[l] || ['<b>内容区</b>'];
    return '<div class="wireframe"><div class="wf-bar"><i></i><i></i><i></i><span style="margin-left:8px">目标形态 · ' + l + '</span></div>' +
      zones.map(function (z) { return '<div class="wf-zone' + (z.indexOf('<b>') === 0 ? '' : ' dim') + '">' + z + '</div>'; }).join('') + '</div>';
  }
  function archive(r) {
    var sib = HS.ROUTES.filter(function (x) { return x.m === r.m && x.p !== r.p; }).slice(0, 6);
    return pageHead({ no: '§' + r.p, title: r.t, badges: badge('ok') + (r.g ? '<span class="badge b-id">gate ' + r.g + '</span>' : ''),
      sub: esc(r.d), meta: esc(r.c) + '<br>' + esc(r.api.join(' · ')) }) +
      '<div class="arch mt2"><div class="stack">' +
      '<div class="card">' + cardH('实现状态 <span class="cx">routes-status 实测</span>') +
      kv([{ k: '组件', v: '<span class="mono">' + esc(r.c) + '</span>（lazy，实测存在）' },
      { k: '归属', v: r.m ? esc(r.m) + ' 菜单（menuOf 自动归属）' : '无菜单（全屏）' },
      { k: '主要 API', v: r.api.map(function (a) { return '<span class="tag mono" style="font-size:10px">' + esc(a) + '</span>'; }).join(' ') },
      { k: '判定依据', v: '<span style="font-size:11.5px">' + esc(r.e) + '</span>' }]) + '</div>' +
      (r.caps || []).map(stamp).join('') +
      (r.g ? '<div class="guard-box">gate 依赖：<b>' + r.g + '</b> —— 关闭时路由 404（扩展 router 按 is_extension_enabled() 条件注册），旧深链落 * 兜底不白屏。可在 <a href="#/settings?cat=general" style="color:var(--info)">设置 · 通用</a> 切换体验。</div>' : '') +
      '</div><div>' + wireframe(r.l || 'list') +
      (sib.length ? '<div class="card mt3">' + cardH('同域页面') + '<div class="row">' + sib.map(function (s) { return '<button class="chip" onclick="App.go(\'' + demoPath(s.p) + '\')">' + esc(s.t) + '</button>'; }).join('') + '</div></div>' : '') +
      '</div></div>';
  }

  return { esc: esc, badge: badge, capBadge: capBadge, stamp: stamp, stampRaw: stampRaw, pageHead: pageHead, cardH: cardH, tbl: tbl, kv: kv, statTile: statTile, VIEWS: VIEWS, archive: archive };
})();
