/* ============================================================
 * Hotspot 全站重构 demo — 壳层 + 路由 + 交互（app.js）
 * 职责：hash 路由（60 条注册 + 兜底）、哨兵壳三段渲染、三态主题、
 *       gate 状态、命令栏、心跳条、toast、运行时状态（演示内存态）。
 * 治理纪律：本 demo 不落库；一切写操作仅给演示反馈，不伪造成功。
 * ============================================================ */
(function () {
  'use strict';
  var HS = window.HS, HD = window.HD, HV = window.HV;
  var esc = HV.esc; /* 重定向等分支需要 HTML 转义（实现在 views.js） */

  /* ---------- 运行时状态（内存演示态） ---------- */
  var S = {
    theme: localStorage.getItem('hs-theme') || 'light',
    mode: 'all', cat: 'overview', caseTab: 'overview',
    likes: {}, dislikes: {}, favs: {},
    props: {}, runs: JSON.parse(JSON.stringify(HD.RUNS)),
    gates: (function () {
      var saved = {}; try { saved = JSON.parse(localStorage.getItem('hs-gates') || '{}'); } catch (e) { }
      var g = {}; HS.GATES.forEach(function (x) { g[x.k] = saved[x.k] != null ? saved[x.k] : x.on; }); return g;
    })(),
    cmdLog: []
  };
  function gateOn(k) { return !!S.gates[k]; }

  /* ---------- toast ---------- */
  var toastBox = null;
  function toast(msg, kind) {
    if (!toastBox) toastBox = document.getElementById('toast');
    var el = document.createElement('div');
    el.className = 'toast ' + (kind || '');
    el.innerHTML = msg;
    toastBox.appendChild(el);
    setTimeout(function () { el.style.opacity = '0'; el.style.transition = 'opacity 200ms'; }, 2600);
    setTimeout(function () { if (el.parentNode) el.parentNode.removeChild(el); }, 3000);
  }

  /* ---------- 主题 ---------- */
  function applyTheme() {
    document.documentElement.setAttribute('data-theme', S.theme);
    localStorage.setItem('hs-theme', S.theme);
  }
  function setTheme(t) { S.theme = t; applyTheme(); toast('主题 → ' + t + '（三态：light / dark / paper）'); render(); }
  function cycleTheme() {
    var order = ['light', 'dark', 'paper'];
    S.theme = order[(order.indexOf(S.theme) + 1) % 3];
    applyTheme(); render();
  }

  /* ---------- 路由解析 ---------- */
  function parseHash() {
    var h = location.hash.replace(/^#/, '') || '/';
    var qi = h.indexOf('?');
    var path = qi >= 0 ? h.slice(0, qi) : h;
    var q = {};
    if (qi >= 0) h.slice(qi + 1).split('&').forEach(function (kv) {
      var p = kv.split('='); if (p[0]) q[decodeURIComponent(p[0])] = decodeURIComponent(p[1] || '');
    });
    return { path: path, q: q };
  }
  function matchRoute(path) {
    var segs = path.split('/').filter(Boolean);
    for (var i = 0; i < HS.ROUTES.length; i++) {
      var r = HS.ROUTES[i];
      var ps = r.p.split('/').filter(Boolean);
      if (r.p === '/' && segs.length === 0) return { route: r, params: [] };
      if (ps.length !== segs.length) continue;
      var params = [], ok = true;
      for (var j = 0; j < ps.length; j++) {
        if (ps[j].charAt(0) === ':') params.push(decodeURIComponent(segs[j]));
        else if (ps[j] !== segs[j]) { ok = false; break; }
      }
      if (ok) return { route: r, params: params };
    }
    return null;
  }
  function matchRedirect(path) {
    for (var i = 0; i < HS.REDIRECTS.length; i++) {
      var r = HS.REDIRECTS[i];
      if (r.p === '*') continue;
      if (r.p === path) return r;
      var ps = r.p.split('/').filter(Boolean), ss = path.split('/').filter(Boolean);
      if (ps.length === ss.length && ps.every(function (seg, k) { return seg.charAt(0) === ':' || seg === ss[k]; })) return r;
    }
    return null; /* '*' 由调用方兜底 */
  }
  function go(path) { location.hash = '#' + path; }

  /* ---------- 壳渲染 ---------- */
  function renderNav(active) {
    return HS.LAYERS.map(function (l) {
      return '<a class="nv ' + (active === l.key ? 'on' : '') + '" href="#' + l.root + '">' + l.label + '<span class="nv-en">' + l.en + '</span></a>';
    }).join('');
  }
  function renderBand(active) {
    var chips = (HS.BANDS[active] || []).filter(function (c) { return !c.gate || gateOn(c.gate); });
    if (!chips.length) return '<span class="bd-label">' + active + '</span><span class="faint" style="font-size:11px">（该菜单暂无二级域）</span>';
    var cur = parseHash().path;
    return '<span class="bd-label">' + active + '</span>' + chips.map(function (c) {
      return '<a class="chip ' + (cur === c.p ? 'on' : '') + '" href="#' + c.p + '">' + c.t + '</a>';
    }).join('');
  }
  function renderPress() {
    var p = HD.PIPE, h = p.health === 'ok' ? 'st-ok' : 'st-warn';
    var funnel = [['收', p.funnel.collected, 100], ['准', p.funnel.admitted, Math.round(p.funnel.admitted / p.funnel.collected * 100)], ['信', p.funnel.signal, Math.round(p.funnel.signal / p.funnel.collected * 100)], ['案', p.funnel.case, Math.round(p.funnel.case / p.funnel.collected * 100)]];
    return '<section class="sn-press" aria-label="采集管道状态">' +
      '<div class="pipe-block"><div class="pipe-k">管道</div><div class="pipe-v ' + h + '">● 健康 · demo 静态</div></div>' +
      '<div class="pipe-block"><div class="pipe-k">源在线</div><div class="pipe-v num">' + p.active + '<span class="sep">/</span>' + p.total + '</div></div>' +
      '<div class="pipe-block"><div class="pipe-k">今日收录</div><div class="pipe-v num" id="pb-today">' + p.today + '</div></div>' +
      '<div class="pipe-block"><div class="pipe-k">管线漏斗</div><div class="pipe-funnel">' + funnel.map(function (f) {
        return '<span class="fseg" style="width:' + (26 + f[2] * 0.5) + 'px"><i style="width:' + f[2] + '%"></i></span><span class="flab">' + f[0] + ' <span class="num">' + f[1] + '</span></span>';
      }).join('') + '</div></div>' +
      '<div class="pipe-block"><div class="pipe-k">队列</div><div class="pipe-v num">' + p.queue.pending + '<span class="sep">·</span>' + p.queue.running + '<span class="sep">·</span><span class="' + (p.queue.error ? 'st-warn' : '') + '">' + p.queue.error + '</span></div></div>' +
      '<div class="pipe-live"><span class="pulse"></span><span class="lv-label">PIPELINE LIVE</span><span class="beat-lights">' +
      p.sources.map(function (s) { return '<span class="bl ' + (s.s === 'ok' ? '' : s.s) + '" title="' + s.n + '：' + s.s + '"></span>'; }).join('') + '</span></div></section>';
  }
  function renderFoot() {
    return '<div class="foot"><span>SecNews Knowledge Dashboard · 哨兵编辑部 × 安全终端 重构 demo</span>' +
      '<span>纯静态演示 · 本地计算 · 不连后端 · 数据为演示样例</span>' +
      '<a href="#/coverage">覆盖地图</a><a href="canvas.html" target="_blank">无限画布</a>' +
      '<span>落点：design/redesign-v1/（不触碰 frontend/src 生产代码）</span></div>' +
      '<div class="demo-flag">DEMO · 演示样例 · 非真实数据</div>';
  }

  /* ---------- 命令栏（XF-5：固定四类意图模板，不可识别显式列出） ---------- */
  var CMD_ITEMS = [
    { tag: '查询', label: '查询 漏洞 / 来源 / 案件…（带 Source url）', act: "App.go('/search')" },
    { tag: '建案', label: '从当前信号建案（生成 proposal，人确认）', act: "App.go('/action')" },
    { tag: '出报告', label: '出周报 / 月报（proposal 通道）', act: "App.go('/report')" },
    { tag: '执行', label: '执行类动作（诚实返回 unsupported）', act: "App.cmdUnsupported()" }
  ];
  function cmdPop(show) {
    var el = document.getElementById('cmd-pop'); if (!el) return;
    if (!show) { setTimeout(function () { if (el && !el.matches(':hover')) el.style.display = 'none'; }, 150); return; }
    el.innerHTML = '<div class="faint" style="font-size:10px;letter-spacing:0.12em;padding:4px 10px">固定四类意图（本地规则优先 · 不做通用 NLU）</div>' +
      CMD_ITEMS.map(function (c) { return '<button class="cmd-item" onmousedown="' + c.act + ';return false"><span class="cmd-tag">[' + c.tag + ']</span> ' + c.label + '</button>'; }).join('');
    el.style.display = 'block';
  }
  function cmdKey(e) {
    if (e.key !== 'Enter') return;
    var v = e.target.value.trim();
    S.cmdLog.push({ v: v, ts: new Date().toISOString() });
    if (!v) { toast('命令为空——可点击下列意图模板（不可识别时不猜，显式列出）', 't-warn'); cmdPop(1); return; }
    if (/查|找|search/i.test(v)) { go('/search'); }
    else if (/建|案|case/i.test(v)) { go('/action'); }
    else if (/报告|report|周报|月报/i.test(v)) { go('/report'); }
    else if (/执行|运行|run/i.test(v)) { toast('unsupported：执行类动作需 ExecutionPlan 审批 + 边界协议（默认拒绝）；命令已记录 command_log（演示）', 't-warn'); }
    else { toast('不可识别：可选动作——查询 / 建案 / 出报告 / 执行（不猜）；已记录 command_log（演示）', 't-warn'); }
    e.target.value = ''; cmdPop(0);
  }

  /* ---------- Run 状态机（CAS 演示：queued→claimed→running→终态） ---------- */
  var RUN_OK = { queued: ['claim'], claimed: ['start', 'cancel'], running: ['finish', 'fail', 'cancel'] };
  function runAct(id, act) {
    var r = S.runs.filter(function (x) { return x.id === id; })[0];
    if (!r) return;
    if (act === 'redo409') { toast('409 Conflict：重复终态提交被 CAS 拒绝（revision 不匹配）——幂等语义演示', 't-red'); return; }
    var allowed = RUN_OK[r.status] || [];
    if (allowed.indexOf(act) < 0) { toast('非法迁移：' + r.status + ' → ' + act + '（仅 queued/claimed 可操作；CAS 拒绝）', 't-red'); return; }
    if (act === 'claim') { r.status = 'claimed'; r.by = '已认领（人担保）'; toast('claim：run 进入 claimed（演示内存态，未落库）'); }
    if (act === 'start') { r.status = 'running'; r.by = '执行中'; toast('start：run 进入 running（演示）'); }
    if (act === 'cancel') { r.status = 'done'; r.outcome = 'cancelled'; r.by = '人工取消'; toast('cancel：终态 outcome=cancelled（显式，不伪造成功）'); }
    if (act === 'finish') { r.status = 'done'; r.outcome = 'done'; r.by = '人工回执（人担保 · audit_log 留痕）'; toast('finish·done：发 v1_run outbox 事件（演示）'); }
    if (act === 'fail') { r.status = 'done'; r.outcome = 'failed'; r.by = '失败显式 outcome + error 原因码'; toast('finish·failed：失败必可见（零静默）', 't-warn'); }
    render();
  }

  /* ---------- 提案（两步批准 / 驳回必填 ≤200） ---------- */
  function propApprove(id, step) {
    var p = S.props[id] || (S.props[id] = {});
    if (step === 1) { p.state = 'confirm'; render(); return; }
    if (step === 0) { p.state = ''; render(); return; }
    p.state = 'approved';
    toast('批准（演示内存态）：真实实现将写 audit + 触发双签 Run；未经人审批不得成为事实（人主律）');
    render();
  }
  function propReject(id) {
    var inp = document.getElementById('rej-' + id);
    var reason = inp ? inp.value.trim() : '';
    if (!reason) { toast('驳回原因必填（≤200 字）', 't-warn'); return; }
    S.props[id] = { state: 'rejected', reason: reason };
    render();
  }

  /* ---------- 资讯互动（状态型信号：互斥切换 + 可取消） ---------- */
  function react(id, kind) {
    if (kind === 'like') {
      if (S.likes[id]) delete S.likes[id]; else { S.likes[id] = 1; delete S.dislikes[id]; toast('reaction 已记录（演示内存态；真实实现落 interest_signals，不回滚乐观态）'); }
    } else {
      if (S.dislikes[id]) delete S.dislikes[id]; else { S.dislikes[id] = 1; delete S.likes[id]; }
    }
    render();
  }
  function fav(id) {
    S.favs[id] = S.favs[id] != null ? !S.favs[id] : !HD.FEED.filter(function (x) { return x.id === id; })[0].fav;
    toast('收藏已切换（行为信号 view/favorite 埋点演示）');
    render();
  }

  /* ---------- gate ---------- */
  function toggleGate(k) {
    S.gates[k] = !S.gates[k];
    localStorage.setItem('hs-gates', JSON.stringify(S.gates));
    toast('gate ' + k + ' → ' + (S.gates[k] ? '开' : '关') + '（演示：真实实现走 GET/PUT /api/settings/feature-gates，TOML 写入 + audit）');
    render();
  }

  /* ---------- 视图渲染主流程 ---------- */
  function render() {
    var parsed = parseHash();
    var path = parsed.path, q = parsed.q;
    var main = document.getElementById('main');
    var html = '', active = 'data';

    var m = matchRoute(path);
    if (m && m.route.p === '/coverage') { /* 不可能：coverage 不在 ROUTES */ }
    if (path === '/coverage') {
      active = 'settings';
      html = HV.VIEWS.coverage();
    } else if (m) {
      var r = m.route;
      active = r.m || 'data';
      if (r.g && !gateOn(r.g)) {
        html = HV.pageHead({ no: '§GATE', title: r.t, badges: '<span class="badge b-none">gate 关闭</span>',
          sub: 'feature gate「' + r.g + '」当前关闭：扩展 router 按 is_extension_enabled() 条件注册（关闭时 404）。', meta: 'demo gate 演示' }) +
          '<div class="card mt3">可在 <a href="#/settings?cat=general" style="color:var(--info)">设置 · 通用 · 能力开关</a> 重新开启体验。</div>';
      } else if (r.v && HV.VIEWS[r.v]) {
        html = HV.VIEWS[r.v](m.params, q);
      } else {
        html = HV.archive(r);
      }
    } else {
      var rd = matchRedirect(path);
      var target = rd ? rd.to : '/';
      var note = rd ? rd.note : '兜底重定向（* → /）：扩展关闭时旧深链不白屏';
      active = HS.menuOf(target) || 'data';
      html = '<div class="redirect"><div class="rd-arrow">↷</div><h2 style="font-family:var(--font-sans)">重定向兼容</h2>' +
        '<p class="muted" style="font-size:12.5px"><span class="mono">' + esc(path) + '</span> → <span class="mono">' + esc(target) + '</span><br>' + esc(note) + '</p>' +
        '<div class="legend" style="justify-content:center">' + HV.badge('redirect') + '<button class="btn btn-sm" onclick="App.go(\'' + target + '\')">立即前往</button></div></div>';
      setTimeout(function () { if (location.hash === '#' + path) go(target); }, 1400);
    }

    main.innerHTML = html + renderFoot();
    document.querySelector('.sn-nav').innerHTML = renderNav(active);
    document.getElementById('band').innerHTML = renderBand(active);
    document.getElementById('presswrap').innerHTML = renderPress();
    window.scrollTo(0, 0);
  }

  /* ---------- 心跳与时钟（timer 不可用时优雅降级：静态已完整） ---------- */
  function pressTick() {
    HD.PIPE.today += Math.floor(Math.random() * 2);
    var el = document.getElementById('pb-today'); if (el) el.textContent = HD.PIPE.today;
  }
  function clockTick() {
    var el = document.getElementById('clock'); if (!el) return;
    var d = new Date();
    el.textContent = ('0' + d.getHours()).slice(-2) + ':' + ('0' + d.getMinutes()).slice(-2) + ':' + ('0' + d.getSeconds()).slice(-2);
  }

  /* ---------- 导出 App ---------- */
  window.App = {
    S: S,
    go: go, toast: toast,
    setTheme: setTheme, cycleTheme: cycleTheme,
    setMode: function (m) { S.mode = m; render(); },
    caseSection: function (t) { S.caseTab = t; render(); },
    react: react, fav: fav,
    runAct: runAct, propApprove: propApprove, propReject: propReject,
    toggleGate: toggleGate,
    cmdPop: cmdPop, cmdKey: cmdKey,
    cmdUnsupported: function () { toast('unsupported：执行类需 ExecutionPlan 审批 + 边界协议（默认拒绝）；已记录 command_log（演示）', 't-warn'); },
    openCanvas: function () { window.open('canvas.html', '_blank'); },
    gateOn: gateOn
  };

  /* ---------- 启动 ---------- */
  function boot() {
    applyTheme();
    window.addEventListener('hashchange', render);
    render();
    clockTick(); setInterval(clockTick, 1000);
    setInterval(pressTick, 5000);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot); else boot();
})();
