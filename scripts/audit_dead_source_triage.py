"""audit_dead_source_triage — 离线源四层现场诊断 + 死因/可修性/处置分类 (只读).

用法::

    .venv/bin/python scripts/audit_dead_source_triage.py            # 全部 dead+grace 启用源
    .venv/bin/python scripts/audit_dead_source_triage.py --status dead
    .venv/bin/python scripts/audit_dead_source_triage.py --no-live  # 只用历史, 不出网
    .venv/bin/python scripts/audit_dead_source_triage.py --limit 5 --concurrency 3

产出 (默认 reports/, gitignored):
    reports/dead_source_triage.json   — 逐源完整证据 + 分类 + retire_candidates 列表
    reports/dead_source_triage.md     — 人读汇总 (死因×数量×可修性×建议动作)

只读契约 (scripts/AGENTS.md audit_* 规则): 主库 / warm 库均以 ``mode=ro`` URI 打开,
全程 SELECT; 出网探测复用 ``backend.utils.url_safety.validate_url`` 的 SSRF 门
(私网/环回/字面 IP 一律不连, 记为 ssrf_policy)。

四层探测 (每源独立超时, 线程池并发):
    L1 DNS       getaddrinfo → nxdomain / temp-fail / ok
    L2 TCP+TLS   connect → 严格 TLS 握手; 失败再用宽松 ctx (legacy renegotiation /
                 不校验证书 / SECLEVEL=0) 复试 → 区分 "可用宽松 TLS 修" vs "彻底握不上"
    L3 HTTP      GET (浏览器 UA, 跟随重定向, 读前 300KB) → 状态码 / 终态 URL / 类型
    L4 内容      rss → feedparser entries/bozo; html → 文本量/链接数/WAF 特征

分类输出 cause / fixable(yes|maybe|no) / action(fix|hold|retire) / hint。
结合 crawler_sources.last_* + warm.crawler_runs 7d/全量历史判 "从未成功 vs 曾成功"。
"""
from __future__ import annotations

import argparse
import json
import re
import socket
import sqlite3
import ssl
import sys
import time
import urllib.error
import urllib.request
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

# 宽松 TLS ctx 故意降到 TLSv1 探测古旧政企站, 该 DeprecationWarning 是预期噪声
warnings.filterwarnings("ignore", category=DeprecationWarning, module="ssl")
warnings.filterwarnings("ignore", message=r"ssl\.TLSVersion\.TLSv1 is deprecated")

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from backend.config import config  # noqa: E402
from backend.utils.url_safety import UrlSafetyError, validate_url  # noqa: E402

BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)
MAX_BODY = 300_000
WAF_MARKERS = re.compile(
    r"(captcha|验证码|安全验证|滑动验证|访问被拒绝|Access Denied|Just a moment|"
    r"Cloudflare|请开启 ?JavaScript|jsl_clearance|__jsluid|acw_sc__v2|"
    r"WAF|Request Rejected|人机验证|拦截|Forbidden)",
    re.IGNORECASE,
)
WAF_CODES = {401, 403, 406, 412, 418, 429, 451, 503}


# ---------------------------------------------------------------------------
# DB (只读)
# ---------------------------------------------------------------------------
def _open_ro() -> sqlite3.Connection:
    main_uri = f"file:{config.db_path}?mode=ro"
    conn = sqlite3.connect(main_uri, uri=True, timeout=5)
    conn.row_factory = sqlite3.Row
    warm = Path(config.warm_db_path)
    if warm.exists():
        conn.execute("ATTACH DATABASE ? AS warm", (f"file:{warm}?mode=ro",))
    return conn


def _has_warm_runs(conn: sqlite3.Connection) -> bool:
    try:
        row = conn.execute(
            "SELECT 1 FROM warm.sqlite_master WHERE type='table' AND name='crawler_runs'"
        ).fetchone()
        return row is not None
    except sqlite3.Error:
        return False


def load_offline_sources(conn: sqlite3.Connection, statuses: list[str]) -> list[dict]:
    out: list[dict] = []
    for st in statuses:
        rows = conn.execute(
            "SELECT id, category, name, kind, url, feed_url, api_url, status, enabled, priority, cadence_seconds, verify_ssl, consecutive_failures, health_score, last_error, last_fetch_at, last_success_at, last_yield_at, cooldown_until, grace_rounds FROM crawler_sources WHERE enabled = 1 AND status = ? ORDER BY category, priority DESC, name",  # noqa: E501
            (st,),
        ).fetchall()
        out.extend(dict(r) for r in rows)
    return out


def load_history(conn: sqlite3.Connection, src: dict, has_runs: bool) -> dict:
    """warm.crawler_runs 7d + 全量: 同时按 id 与 name 匹配 (两条写入路径口径不同)."""
    hist = {
        "runs_7d": 0, "success_7d": 0, "failed_7d": 0, "partial_7d": 0,
        "top_errors_7d": [], "ever_yield_runs": 0, "last_yield_run_at": None,
    }
    if not has_runs:
        return hist
    sid, name = src["id"], src["name"]
    row = conn.execute(
        "SELECT COUNT(*) AS n, COALESCE(SUM(status='success'),0) AS s, COALESCE(SUM(status='failed'),0) AS f, COALESCE(SUM(status='partial'),0) AS p FROM warm.crawler_runs WHERE (source_id = ? OR source_id = ?) AND started_at >= datetime('now', '-7 days')",  # noqa: E501
        (sid, name),
    ).fetchone()
    hist.update(runs_7d=row["n"], success_7d=row["s"], failed_7d=row["f"], partial_7d=row["p"])
    errs = conn.execute(
        "SELECT substr(COALESCE(error_msg,''),1,90) AS e, COUNT(*) AS c FROM warm.crawler_runs WHERE (source_id = ? OR source_id = ?) AND started_at >= datetime('now', '-7 days') AND COALESCE(error_msg,'') != '' GROUP BY e ORDER BY c DESC LIMIT 3",  # noqa: E501
        (sid, name),
    ).fetchall()
    hist["top_errors_7d"] = [{"error": r["e"], "count": r["c"]} for r in errs]
    y = conn.execute(
        "SELECT COUNT(*) AS n, MAX(started_at) AS last FROM warm.crawler_runs WHERE (source_id = ? OR source_id = ?) AND fetched_count > 0",  # noqa: E501
        (sid, name),
    ).fetchone()
    hist["ever_yield_runs"] = y["n"]
    hist["last_yield_run_at"] = y["last"]
    return hist


def load_source_stats(conn: sqlite3.Connection, src: dict) -> dict | None:
    """Phase 9 口径 (前端 18/69 用的那张表)."""
    try:
        row = conn.execute(
            "SELECT status, total_runs, total_items, zero_yield_runs, last_seen_at, last_checked_at, last_error FROM source_stats WHERE category = ? AND source_name = ?",  # noqa: E501
            (src["category"], src["name"]),
        ).fetchone()
    except sqlite3.Error:
        return None
    return dict(row) if row else None


# ---------------------------------------------------------------------------
# 四层探测
# ---------------------------------------------------------------------------
def pick_url(src: dict) -> str:
    return (src.get("feed_url") or src.get("url") or src.get("api_url") or "").strip()


def _make_ctx(mode: str) -> ssl.SSLContext:
    """三档 TLS ctx: strict (默认) / legacy (只放行 legacy renegotiation, 生产可接受) /
    relaxed (不校验证书 + TLSv1 + SECLEVEL=0, 仅诊断用)."""
    ctx = ssl.create_default_context()
    if mode in ("legacy", "relaxed"):
        ctx.options |= getattr(ssl, "OP_LEGACY_SERVER_CONNECT", 0x4)
    if mode == "relaxed":
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        try:
            ctx.minimum_version = ssl.TLSVersion.TLSv1
        except (ValueError, AttributeError):
            pass
        try:
            ctx.set_ciphers("DEFAULT:@SECLEVEL=0")
        except ssl.SSLError:
            pass
    return ctx


def _tls_handshake(host: str, port: int, timeout: float, mode: str) -> str | None:
    ctx = _make_ctx(mode)
    try:
        with socket.create_connection((host, port), timeout=timeout) as s, \
                ctx.wrap_socket(s, server_hostname=host) as ss:
            ss.getpeercert(binary_form=True)
        return None
    except ssl.SSLError as e:
        return (e.reason or str(e))[:120]
    except (OSError, TimeoutError) as e:
        return f"io:{str(e)[:100]}"


def _http_get(url: str, timeout: float, ctx_mode: str) -> dict:
    res: dict = {"http_code": 0, "final_url": None, "content_type": None, "body": b"", "http_error": None}
    handlers = []
    if ctx_mode != "strict":
        handlers.append(urllib.request.HTTPSHandler(context=_make_ctx(ctx_mode)))
    opener = urllib.request.build_opener(*handlers)
    req = urllib.request.Request(url, headers={
        "User-Agent": BROWSER_UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    })
    try:
        with opener.open(req, timeout=timeout) as resp:
            res["http_code"] = resp.status
            res["final_url"] = resp.geturl()
            res["content_type"] = resp.headers.get("Content-Type", "")
            res["body"] = resp.read(MAX_BODY)
    except urllib.error.HTTPError as e:
        res["http_code"] = e.code
        res["final_url"] = e.geturl()
        res["content_type"] = e.headers.get("Content-Type", "") if e.headers else ""
        try:
            res["body"] = e.read(MAX_BODY)
        except Exception:
            pass
    except urllib.error.URLError as e:
        res["http_error"] = f"urlerror:{str(e.reason)[:120]}"
    except (TimeoutError, socket.timeout):
        res["http_error"] = "timeout"
    except Exception as e:
        res["http_error"] = f"{type(e).__name__}:{str(e)[:100]}"
    return res


def _decode(body: bytes) -> str:
    for enc in ("utf-8", "gb18030", "gbk"):
        try:
            return body.decode(enc)
        except UnicodeDecodeError:
            continue
    return body.decode("utf-8", errors="ignore")


def _analyze_content(src: dict, http: dict) -> dict:
    body = http.get("body") or b""
    ct = (http.get("content_type") or "").lower()
    out: dict = {"content_kind": None, "rss_entries": None, "rss_bozo": None,
                 "html_text_len": None, "html_links": None, "waf_marker": None}
    is_rss = src.get("kind") == "rss" or "xml" in ct or "rss" in ct or "atom" in ct
    if is_rss:
        import feedparser  # backend 依赖

        fp = feedparser.parse(body)
        out["content_kind"] = "rss"
        out["rss_entries"] = len(fp.entries)
        out["rss_bozo"] = bool(fp.bozo)
        if fp.bozo and getattr(fp, "bozo_exception", None):
            out["rss_bozo_exc"] = str(fp.bozo_exception)[:120]
        if not fp.entries:
            text = _decode(body)
            m = WAF_MARKERS.search(text)
            out["waf_marker"] = m.group(0) if m else None
        return out
    text = _decode(body)
    out["content_kind"] = "html"
    out["html_links"] = len(re.findall(r"<a\s[^>]*href=", text, re.IGNORECASE))
    stripped = re.sub(r"<script.*?</script>|<style.*?</style>", " ", text, flags=re.S | re.I)
    stripped = re.sub(r"<[^>]+>", " ", stripped)
    out["html_text_len"] = len(re.sub(r"\s+", " ", stripped).strip())
    m = WAF_MARKERS.search(text[:20000])
    out["waf_marker"] = m.group(0) if m else None
    return out


def probe_live(src: dict, timeout: float) -> dict:
    url = pick_url(src)
    res: dict = {"probe_url": url, "dns": None, "ip": None, "ssrf": None, "tcp": None,
                 "tls_strict": None, "tls_legacy": None, "tls_relaxed": None, "tls_mode": None,
                 "http": None, "content": None}
    if not url:
        res["dns"] = "no_url"
        return res
    p = urlparse(url)
    host = p.hostname or ""
    https = p.scheme == "https"
    port = p.port or (443 if https else 80)
    res["host"] = host
    # L1 DNS
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
        res["dns"] = "ok"
        res["ip"] = infos[0][4][0]
    except socket.gaierror as e:
        res["dns"] = "nxdomain" if e.errno in (8, -2, -5) else f"fail:{e.errno}"
        res["dns_error"] = str(e)[:120]
        return res
    except Exception as e:
        res["dns"] = f"fail:{type(e).__name__}"
        res["dns_error"] = str(e)[:120]
        return res
    # SSRF 策略门 (私网/环回/保留段一律不连)
    try:
        validate_url(url)
    except UrlSafetyError as e:
        res["ssrf"] = str(e)[:160]
        return res
    # L2 TCP
    try:
        with socket.create_connection((host, port), timeout=timeout):
            res["tcp"] = "ok"
    except (TimeoutError, socket.timeout):
        res["tcp"] = "timeout"
        return res
    except OSError as e:
        res["tcp"] = f"refused:{e.errno}"
        return res
    # L2b TLS: strict → legacy(仅 renegotiation) → relaxed(全宽松, 仅诊断)
    tls_mode = "strict"
    if https:
        err = _tls_handshake(host, port, timeout, "strict")
        if err is not None and err.startswith("io:"):
            err = _tls_handshake(host, port, timeout, "strict")  # io 抖动重试一次
        if err is None:
            res["tls_strict"] = "ok"
        else:
            res["tls_strict"] = err
            err_l = _tls_handshake(host, port, timeout, "legacy")
            res["tls_legacy"] = "ok" if err_l is None else err_l
            if err_l is None:
                tls_mode = "legacy"
            else:
                err_r = _tls_handshake(host, port, timeout, "relaxed")
                res["tls_relaxed"] = "ok" if err_r is None else err_r
                if err_r is not None:
                    return res
                tls_mode = "relaxed"
    res["tls_mode"] = tls_mode
    # L3 HTTP
    http = _http_get(url, timeout, tls_mode)
    res["http"] = {k: v for k, v in http.items() if k != "body"}
    res["http"]["body_bytes"] = len(http.get("body") or b"")
    if http.get("http_error") or not http.get("http_code"):
        return res
    # L4 内容
    res["content"] = _analyze_content(src, http)
    return res


# ---------------------------------------------------------------------------
# 分类
# ---------------------------------------------------------------------------
def classify(src: dict, live: dict | None, hist: dict, stats: dict | None,
             crawl4ai_on: bool) -> dict:
    never = (src.get("last_yield_at") in (None, "")) and hist.get("ever_yield_runs", 0) == 0 \
        and not (stats and (stats.get("total_items") or 0) > 0)
    base = {"ever_succeeded": not never}

    def out(cause, fixable, action, hint):
        return {**base, "cause": cause, "fixable": fixable, "action": action, "hint": hint}

    if live is None:  # --no-live: 只能按历史 last_error 粗分
        le = (src.get("last_error") or "").lower()
        if "errno 8" in le or "nodename nor servname" in le or "name or service not known" in le:
            return out("dns_nxdomain(hist)", "no", "retire", "历史 DNS 失败; 需 --live 复核")
        if "404" in le:
            return out("http_gone(hist)", "no", "retire", "历史 404; 需 --live 复核")
        if "ssl" in le or "renegotiation" in le or "handshake" in le:
            return out("tls(hist)", "maybe", "hold", "历史 TLS 失败; 需 --live 判宽松是否可用")
        if "403" in le or "412" in le or "429" in le or "anti-bot" in le:
            return out("waf(hist)", "maybe", "hold", "历史反爬; 需 --live 复核")
        return out("unknown(hist)", "maybe", "hold", "历史无明确错误; 需 --live")

    if live.get("dns") == "no_url":
        return out("no_url", "no", "retire", "三 URL 全空 (Layer 3 兜底本就跳过)")
    if live.get("dns") == "nxdomain":
        return out("dns_nxdomain", "no", "retire", "域名不解析 (NXDOMAIN); 站点已消失")
    if live.get("dns") and live["dns"].startswith("fail"):
        return out("dns_tempfail", "maybe", "hold", f"DNS 临时失败 {live.get('dns_error')}; 复测")
    if live.get("ssrf"):
        return out("ssrf_policy", "no", "retire", f"SSRF 策略拒连: {live['ssrf'][:80]}")
    if live.get("tcp") == "timeout":
        return out("tcp_timeout", "no" if never else "maybe", "retire" if never else "hold",
                   "TCP 连不上 (被墙/防火墙/本网络路径); 从未成功者退役")
    if live.get("tcp") and live["tcp"].startswith("refused"):
        return out("tcp_refused", "no" if never else "maybe", "retire" if never else "hold",
                   "端口拒绝; 从未成功者退役")
    tls_mode = live.get("tls_mode")
    strict_failed = live.get("tls_strict") not in (None, "ok")
    if strict_failed and tls_mode is None:
        return out("tls_unrecoverable", "no", "retire",
                   f"三档 TLS 均失败: strict={live.get('tls_strict')} / legacy={live.get('tls_legacy')} / relaxed={live.get('tls_relaxed')}")
    tls_fix = strict_failed and tls_mode in ("legacy", "relaxed")
    http = live.get("http") or {}
    content = live.get("content") or {}
    if http.get("http_error") == "timeout":
        return out("http_timeout", "no" if never else "maybe", "retire" if never else "hold",
                   "TCP 通但 HTTP 超时 (WAF 挂起/慢站)")
    if http.get("http_error"):
        return out("http_error", "maybe", "hold", http["http_error"])
    code = http.get("http_code") or 0
    tls_note = f"; TLS 需 {tls_mode} ctx (strict: {live.get('tls_strict')})" if tls_fix else ""
    if code in (404, 410):
        return out("http_gone", "no", "retire", f"HTTP {code}: URL 已下线; 如有替代地址手工换" + tls_note)
    waf = content.get("waf_marker") if content else None
    if code in WAF_CODES or (code == 200 and waf and (content.get("html_text_len") or 0) < 3000):
        fixable = "maybe"
        action = "fix" if crawl4ai_on else ("retire" if never else "hold")
        return out("waf_blocked", fixable, action,
                   f"HTTP {code} / 特征 {waf!r}: 反爬; 可试 crawl4ai 渲染+浏览器 UA+6h 降频"
                   + ("" if crawl4ai_on else " (crawl4ai 未开, 从未成功者退役)") + tls_note)
    if 500 <= code < 600:
        return out("server_error", "maybe", "hold", f"HTTP {code} 站点侧故障; 复测" + tls_note)
    if code >= 300 and code < 400:
        return out("redirect_loop", "maybe", "hold", f"HTTP {code} 未收敛; 检查 final_url" + tls_note)
    if code != 200:
        return out(f"http_{code}", "maybe", "hold", f"HTTP {code}" + tls_note)
    # 200
    if content.get("content_kind") == "rss":
        n = content.get("rss_entries") or 0
        if n > 0:
            return out("rss_reachable_has_entries", "yes", "fix",
                       f"探测拿到 {n} 条 entries: 我方 fetcher 拿空 → UA/头/编码问题" + tls_note)
        if content.get("rss_bozo"):
            return out("rss_broken", "no" if never else "maybe", "retire" if never else "hold",
                       f"feed 解析失败 {content.get('rss_bozo_exc')}: 找替代 feed 或退役" + tls_note)
        return out("rss_empty", "maybe", "hold", "feed 可达但 0 条 (源停更?)" + tls_note)
    text_len = content.get("html_text_len") or 0
    links = content.get("html_links") or 0
    if tls_fix:
        if tls_mode == "legacy":
            return out("tls_legacy_fixable", "yes", "fix",
                       f"仅放行 legacy renegotiation 即 200 (text={text_len}, links={links}): "
                       f"per-host OP_LEGACY_SERVER_CONNECT (生产可接受)")
        return out("tls_cert_or_cipher_fixable", "maybe", "fix",
                   f"需不校验证书/旧 cipher 才 200 (text={text_len}, links={links}): "
                   f"verify_ssl=0 + 弱 TLS, 风险自担; strict={live.get('tls_strict')}")
    if text_len < 1500 or links < 5:
        action = "fix" if crawl4ai_on else ("retire" if never else "hold")
        return out("html_thin_needs_js", "maybe", action,
                   f"200 但正文薄 (text={text_len}, links={links}): SPA/JS 渲染, 需 crawl4ai"
                   + ("" if crawl4ai_on else " (未开, 从未成功者退役)"))
    return out("html_reachable_has_content", "yes", "fix",
               f"200 且有内容 (text={text_len}, links={links}): 解析器/选择器与站点结构漂移")


# ---------------------------------------------------------------------------
# 报告
# ---------------------------------------------------------------------------
def _fmt_md(results: list[dict], meta: dict) -> str:
    from collections import Counter

    by_action = Counter(r["triage"]["action"] for r in results)
    by_cause = Counter(r["triage"]["cause"] for r in results)
    by_cat = Counter((r["source"]["category"], r["triage"]["action"]) for r in results)
    never = sum(1 for r in results if not r["triage"]["ever_succeeded"])
    lines = [
        "# 离线源诊断 (audit_dead_source_triage)",
        "",
        f"- 生成时间: {meta['generated_at']}  | live={meta['live']}  | timeout={meta['timeout']}s",
        f"- 范围: enabled=1 且 status ∈ {meta['statuses']} → **{len(results)} 源**; 从未成功 {never} / 曾成功 {len(results) - never}",
        f"- crawl4ai 开关: {meta['crawl4ai_on']}",
        "",
        "## 处置分布",
        "",
        "| action | 数量 |", "|---|---|",
        *[f"| {a} | {n} |" for a, n in by_action.most_common()],
        "",
        "## 死因分布",
        "",
        "| cause | 数量 |", "|---|---|",
        *[f"| {c} | {n} |" for c, n in by_cause.most_common()],
        "",
        "## 分类 × 处置",
        "",
        "| category | action | 数量 |", "|---|---|---|",
        *[f"| {c} | {a} | {n} |" for (c, a), n in sorted(by_cat.items())],
        "",
        "## 逐源明细",
        "",
        "| id | status | cause | fixable | action | ever_ok | 7d s/f/p | http | hint |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    order = {"fix": 0, "hold": 1, "retire": 2}
    for r in sorted(results, key=lambda x: (order[x["triage"]["action"]], x["source"]["category"], x["source"]["id"])):
        s, t, h = r["source"], r["triage"], r["history"]
        http = (r.get("live") or {}).get("http") or {}
        code = http.get("http_code") or (r.get("live") or {}).get("tcp") or (r.get("live") or {}).get("dns") or "-"
        lines.append(
            f"| {s['id']} | {s['status']} | {t['cause']} | {t['fixable']} | **{t['action']}** | "
            f"{'✓' if t['ever_succeeded'] else '✗'} | {h['success_7d']}/{h['failed_7d']}/{h['partial_7d']} | "
            f"{code} | {t['hint'].replace('|', '/')} |"
        )
    retire = [r["source"]["id"] for r in results if r["triage"]["action"] == "retire"]
    lines += ["", f"## 退役候选 ({len(retire)})", "", "```", *retire, "```", ""]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--status", default="dead,grace", help="逗号分隔 (默认 dead,grace)")
    ap.add_argument("--timeout", type=float, default=10.0)
    ap.add_argument("--concurrency", type=int, default=6)
    ap.add_argument("--limit", type=int, default=0, help="调试: 只处理前 N 个")
    ap.add_argument("--no-live", action="store_true", help="不出网, 仅按历史 last_error 粗分")
    ap.add_argument("--out-dir", default=str(REPO_ROOT / "reports"))
    args = ap.parse_args()

    statuses = [s.strip() for s in args.status.split(",") if s.strip()]
    conn = _open_ro()
    has_runs = _has_warm_runs(conn)
    sources = load_offline_sources(conn, statuses)
    if args.limit:
        sources = sources[: args.limit]
    print(f"[triage] {len(sources)} offline sources (status={statuses}); warm.crawler_runs={'yes' if has_runs else 'NO'}")

    try:
        from backend.utils.crawl4ai_client import is_available as _c4
        crawl4ai_on = bool(_c4())
    except Exception:
        crawl4ai_on = False

    # 历史/stats 先查完再断 DB 读 (线程池里不共享 sqlite 连接)
    enriched: list[dict] = []
    for s in sources:
        enriched.append({
            "source": s,
            "history": load_history(conn, s, has_runs),
            "source_stats": load_source_stats(conn, s),
        })
    conn.close()

    t0 = time.time()
    live_map: dict[str, dict | None] = {}
    if not args.no_live:
        with ThreadPoolExecutor(max_workers=max(1, args.concurrency)) as ex:
            futs = {ex.submit(probe_live, e["source"], args.timeout): e["source"]["id"] for e in enriched}
            done = 0
            for fut in as_completed(futs):
                sid = futs[fut]
                try:
                    live_map[sid] = fut.result()
                except Exception as exc:  # 单源探测崩不拖垮整批
                    live_map[sid] = {"probe_url": None, "dns": f"fail:{type(exc).__name__}", "dns_error": str(exc)[:120]}
                done += 1
                if done % 10 == 0 or done == len(futs):
                    print(f"[triage] probed {done}/{len(futs)} ({time.time() - t0:.0f}s)")

    results: list[dict] = []
    for e in enriched:
        live = None if args.no_live else live_map.get(e["source"]["id"])
        e["live"] = live
        e["triage"] = classify(e["source"], live, e["history"], e["source_stats"], crawl4ai_on)
        results.append(e)

    meta = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "live": not args.no_live, "timeout": args.timeout, "statuses": statuses,
        "crawl4ai_on": crawl4ai_on, "db_path": str(config.db_path),
        "warm_runs_available": has_runs, "count": len(results),
    }
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    retire = [r["source"]["id"] for r in results if r["triage"]["action"] == "retire"]
    payload = {"meta": meta, "retire_candidates": retire, "results": results}
    (out_dir / "dead_source_triage.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    (out_dir / "dead_source_triage.md").write_text(_fmt_md(results, meta), encoding="utf-8")

    from collections import Counter

    print("[triage] action:", dict(Counter(r["triage"]["action"] for r in results)))
    print("[triage] cause :", dict(Counter(r["triage"]["cause"] for r in results).most_common()))
    print(f"[triage] wrote {out_dir / 'dead_source_triage.json'} and .md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
