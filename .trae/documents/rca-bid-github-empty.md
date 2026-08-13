# 招标资讯 & GitHub 数据空 — RCA 报告

**日期**: 2026-08-05
**严重度**: High
**影响**: bid / github 两个 category 在前端 dashboard 长期显示无数据

---

## TL;DR (30 秒摘要)

| 类别 | 现象 | 根因 (5-Whys) |
|------|------|---------------|
| **bid** | DB 7d 0 条 / 24h 0 条，35/64 源 dead，28 个 active 源跑不出数据 | `BaseCollector._parse_html` 用 `NOISE_URL_REGEX.match(href)` 严格匹配噪声，regex 包含 `^/` → 所有站内相对路径（`/news/...`、`/detail/...`）被误判为噪声；`_resolve_url` 在 noise check 之后才调用，无法挽救 |
| **github** | DB 实际 18 条/7d 入库，但前端显示 0（100% `url_check_status='mismatch'`） | `AuthorVerificationGate` 看到 `claimed="TopHub GitHub 热榜"` 和 `url=github.com/owner/repo` → `canonical="GitHub"`，两者不等 → mismatch → 改写 source 为 "GitHub" + 打 mismatch 标记 → `count_by_category` 和 `query()` 都有 `url_check_status NOT IN ('mismatch')` 过滤 → 全部"消失" |

**两者都是「数据已入库但被静默过滤」**，不是抓取失败。

---

## 1. 事实证据 (DB 直查)

### 1.1 hotspots 表 (28d 各 category)

| category | 24h | 3d | 7d | 14d | 28d | 28d last_seen |
|----------|----:|----:|----:|----:|----:---------------|
| ai       | 109 | 115 | 131 | 141 | 204 | 2026-08-05 |
| security |  52 |  75 | 129 | 132 | 303 | 2026-08-05 |
| finance  |  20 |  20 |  12 |  13 |  74 | 2026-08-05 |
| tech     |  60 |  60 |  60 |  60 |  60 | 2026-08-05 |
| startup  |  18 |  18 |  29 |  30 |  30 | 2026-08-05 |
| **github** |  17 |  18 |  18 |  21 |  21 | 2026-08-05 |
| **bid**   |   **0** |   **0** |   **0** |   **0** |   5 | 2026-07-08 |

### 1.2 collection_runs (最近一周 bid)

```
2026-08-05 07:27:10 success items=0  err=
2026-08-05 06:55:56 success items=0  err=
2026-08-05 05:53:20 failed  items=0  err=watchdog: timeout after 600s
2026-08-05 02:14:09 success items=0  err=
... (所有 runs 都 items=0, 只有 1 次 watchdog timeout)
```

- bid `last_yield_at = 2026-07-08T15:25:01`（一次）
- 之后**所有 run_once 跑出 0 items，但 status=success**（"假装成功"）

### 1.3 source_stats (bid 状态分布)

- `active = 28 / dead = 35 / stale = 1` (总 64 源)
- dead 源错误分布（部分）：
  - DNS 失败 (25 源): `ClientConnectorDNSError: Cannot connect to host`
  - HTTP 404 (5 源): 上交所/中央政府采购网/全国公共资源交易平台/采招网-金融/采招网-医疗
  - HTTP 5xx (4 源): 521 (招标网) / 504 (中船集团) / 502 (招标投标公共服务平台)
  - HTTP 412 (1 源): 国家开发银行
  - SSL 错误 (1 源): 中国移动 B2B
- 28 个 active 中 24 个 `last_seen=None` —— **从来没成功过**（Phase 16/19 补全的源 URL 在当时就抓不到，但 status 还保持 active）

### 1.4 crawler_runs / crawler_sources

- `crawler_runs` 各 category 计数: ai=2958, finance=3031, security=7617, tech=852, **github=927, bid=0**
- `crawler_sources` 表**完全空**（seed 流程没人触发）
- **结论**: bid 没迁移到 Crawler v2；新架构里没有 bid category

### 1.5 github url_check_status 分布

```
github 7d 全部 18 条:
  url_check_status='mismatch' = 18  (100%)

quality_flags 全部含:
  - author_mismatch
  - author_corrected_to=GitHub
  - title_summary_inconsistent
  - (部分) content_hash_duplicate
```

### 1.6 模拟 count_by_category (7d) — API 真实返回

```sql
SELECT category, COUNT(*)
FROM hotspots
WHERE ingested_at >= :ago_7d
  AND url_check_status NOT IN ('mismatch', 'unreachable')
  AND quality_flags NOT LIKE '%landing_page_unresolvable%'
GROUP BY category
```

| category | 不过滤 (真实) | API 返回 |
|----------|------------:|--------:|
| ai | 131 | 161 (合并 tech 后) |
| security | 129 | 56 (66 条被 mismatch 过滤) |
| finance | 12 | 8 (2 条 mismatch) |
| startup | 29 | 8 (?? 详情需查) |
| **github** | **18** | **0** (**100% 被 mismatch 过滤**) |
| bid | 0 | 0 (本身没数据) |

---

## 2. 5-Whys 根因分析

### 2.1 bid 5-Whys

**Why-1**: bid 7d/3d/24h 都是 0 条，API 永远返回空数组
**Why-2**: 64 源大部分在跑，但 collection_runs 全部 `item_count=0` —— 抓到了 0 条
**Why-3**: 实际跑一次 `BidCollector.collect()`，很多源 `bid direct OK`（HTTP 200），但 0 items 输出
**Why-4**: `BaseCollector._parse_html` 在解析阶段抽出 0 条
**Why-5 (根因)**: `BaseCollector._parse_html` 第 231 行使用 `NOISE_URL_REGEX.match(href)` 严格匹配噪声；该 regex 包含 `^/`，所有以 `/` 开头的**站内相对路径**（典型如 `/news/infor/2429.html`、`/detail/600632978b18ECC95ACt.html`）100% 被拒。`_resolve_url()` 在 NOISE_URL_REGEX 检查**之后**才被调用，无法挽救。

#### 关键代码 (`backend/collectors/base.py:231`)

```python
def _parse_html(self, html: str, source: dict) -> list[dict[str, Any]]:
    ...
    for m in re.findall(pat, html):
        ...
        if NOISE_URL_REGEX.match(href):  # ← 根因点: 在 resolve 前严格匹配
            continue
        _add_item(title or text, href)   # _add_item 内才调 _resolve_url
```

#### NOISE_URL_REGEX (`backend/quality/config.py:35-44`)

```python
NOISE_URL_PATTERNS = [
    r"^https?://beian\.miit\.gov\.cn",
    r"^javascript:",
    r"^void\(0\)",
    r"^tel:",
    r"^mailto:",
    r"^#",
    r"^/",          # ← 根因: 拦截所有相对路径
]
NOISE_URL_REGEX = re.compile("|".join(NOISE_URL_PATTERNS), re.IGNORECASE)
```

#### 实测验证 (知了标讯)

```python
test_urls = [
    '/news/infor/2429.html',                  # 相对路径
    '/detail/600632978b18ECC95ACt.html',     # 相对路径
    '/bidindustry/i1_k1.html',                # 相对路径
]
# 全部 noise=True (被误杀)
# BaseCollector._parse_html 收到 236 个 <a> 链接
# 234 个被 NOISE_URL_REGEX 过滤掉 (99.2%)
```

---

### 2.2 github 5-Whys

**Why-1**: 21 条 github 入库了，但前端 dashboard 显示 0
**Why-2**: `count_by_category` 和 `query()` 都有 `url_check_status NOT IN ('mismatch', 'unreachable')` 过滤
**Why-3**: 21 条 100% `url_check_status='mismatch'`
**Why-4**: `AuthorVerificationGate.check()` 调用 `resolve_publisher(url, item.source)` —— `item.source="TopHub GitHub 热榜"`，URL 域名 `github.com` → `canonical="GitHub"` → mismatch → 改写 `item.source="GitHub"` + 设 `url_check_status='mismatch'`
**Why-5 (根因)**: `AuthorVerificationGate` 的语义混淆了**「原始发布者」**（github.com = canonical GitHub）和**「数据来源」**（TopHub 聚合站）。聚合站抓的内容 URL 指向真实站点是正常行为，但 Gate 强行把 source 改成原始发布者，导致 mismatch 状态被 set → 全员被 API 过滤。

#### 关键代码 (`backend/quality/author_verification_gate.py:74-83`)

```python
elif canonical is not None:
    # mismatch：纠正 + 扣分
    score_deduction = PENALTY_MISMATCH
    flags.append("author_mismatch")
    flags.append(f"author_corrected_to={canonical}")
    reason_text = f"author_mismatch: {reason}"
    # 直接修改 item
    item.source = canonical            # ← 把 "TopHub GitHub 热榜" 改成 "GitHub"
    item.url_check_status = "mismatch" # ← 触发 API 过滤
```

#### publisher_registry (`backend/quality/publisher_registry.py:87, 174`)

```python
PUBLISHER_REGISTRY = [
    ...
    ("github.com", "GitHub"),           # github.com 任何 URL → canonical "GitHub"
    ...
    ("tophub.today", "TopHub GitHub 热榜"),  # tophub.today → canonical "TopHub..."
    ...
]
# ALIASES 缺: "TopHub GitHub 热榜" → "GitHub" 的豁免映射
```

#### 为什么 TopHub 抓的 URL 是 github.com

`GitHubCollector._parse_html`:
- 抓 `https://tophub.today/n/rYqoXQ8vOD` 页面
- 提取 `<a href="/TencentCloud/TencentDB-Agent-Memory">` 等
- `_resolve_url("/TencentCloud/...", source["url"]="https://tophub.today/...")` 解析为 `https://tophub.today/TencentCloud/...`
- `_is_repo_url()` 拒绝 tophub.today 域名，**只接受 `github.com / www.github.com`**
- 实际最后入库的 URL 形如 `https://github.com/TencentCloud/TencentDB-Agent-Memory`
- source 字段填 `source["name"]` = `"TopHub GitHub 热榜"`

---

## 3. 5-Whys 终结：根因对比

| 维度 | bid | github |
|------|-----|--------|
| 抓取阶段 | ✅ HTML 抓到 (HTTP 200) | ✅ HTML 抓到 (TopHub 聚合) |
| 解析阶段 | ❌ NOISE_URL_REGEX 误杀相对路径 | ✅ 解析出真实项目 |
| 入库阶段 | ❌ 0 items 入库 | ✅ 21 条入库 |
| 质量门禁 | — | ❌ AuthorVerificationGate 改 source + mismatch |
| API 过滤 | — | ❌ url_check_status='mismatch' 被 query/count 过滤 |
| 前端可见 | ❌ 0 条 | ❌ 0 条 (但 DB 有 18 条) |
| **根因类型** | **解析 bug** (NOISE_URL_REGEX 过严) | **业务语义 bug** (聚合站 vs 原始发布者混淆) |

---

## 4. 影响范围

### 4.1 bid (严重)

- 整个 bid category 在前端永久显示空
- 28 个 active 源全部失效（24 个 `last_seen=None` + 4 个 7/8 后无新数据）
- 35 个 dead 源（DNS/404/SSL 错误）从未修复
- watchdog 偶发 600s timeout 触发 category 失败
- 备份路径 Crawler v2 (crawler_sources + crawler_runs) 没迁移 bid

### 4.2 github (中)

- DB 18 条/7d 数据"入库即消失"
- TopHub GitHub 热榜 单一来源承担全部数据（GitHub Trending / Star History 都 dead）
- 21 条 100% mismatch → query/count 双重过滤

---

## 5. 修复建议 (按优先级)

### P0: bid — 修复 NOISE_URL_REGEX 检查顺序 (高 ROI, 小改动)

**位置**: `backend/collectors/base.py:230-231` (lxml cssselect 路径) + `:250-251` + `:267-268` (正则路径)

**方案 A (推荐)**: 先 `_resolve_url`，再走噪声检查
```python
# 修改前
if NOISE_URL_REGEX.match(href):
    continue
_add_item(title or text, href)

# 修改后
resolved_href = self._resolve_url(href, source["url"])
if _is_noise_url(resolved_href, source["url"]):  # 改用 _is_noise_url (更智能)
    continue
_add_item_with_resolved(title, resolved_href)
```

**方案 B (最小改动)**: NOISE_URL_REGEX 移除 `^/`，但保留其它噪声规则
```python
NOISE_URL_PATTERNS = [
    r"^https?://beian\.miit\.gov\.cn",
    r"^javascript:",
    r"^void\(0\)",
    r"^tel:",
    r"^mailto:",
    r"^#",
    # 删除 r"^/", — 改用 _is_noise_url 在 resolve 后检查
]
```

**验证**: 跑一次 `BidCollector.collect()`，预期至少 5-10 个 active 源 (知了标讯、招标采购导航网等) 能产出 items

**风险**: 移除 `^/` 后，根路径链接可能漏出；但 `_is_noise_url` 已能覆盖常见噪声。需补 unit test。

### P0: github — 修复 AuthorVerificationGate 对聚合站的处理 (高 ROI, 小改动)

**位置**: `backend/quality/author_verification_gate.py:74-83`

**方案 A (推荐)**: 区分「数据来源」和「原始发布者」
```python
# 加聚合站白名单
_AGGREGATOR_SOURCES = {
    "TopHub GitHub 热榜",  # 抓 github.com 但源是 TopHub
    # 未来扩展: 36氪 / 虎嗅 / 投资界 等聚合源
}

elif canonical is not None:
    # mismatch 判定
    if item.source in _AGGREGATOR_SOURCES:
        # 聚合源: claimed="TopHub..." (数据来源) != canonical="GitHub" (原始发布者)
        # 是正常行为,只扣分不改 source
        score_deduction = PENALTY_MISMATCH  # 仍扣分
        flags.append("author_via_aggregator")
        flags.append(f"original_publisher={canonical}")
        # 不改 item.source, 不设 mismatch
    else:
        # 原逻辑: mismatch 时改 source + mismatch
        score_deduction = PENALTY_MISMATCH
        flags.append("author_mismatch")
        flags.append(f"author_corrected_to={canonical}")
        item.source = canonical
        item.url_check_status = "mismatch"
```

**方案 B (最小改动)**: publisher_registry 加 alias 映射
```python
ALIASES = {
    ...
    "tophub github 热榜": "GitHub",  # 把 TopHub 也当作 GitHub 的别名
    # 但这会与现有 "tophub github 热榜": "TopHub GitHub 热榜" 冲突
}
```
→ 此方案有冲突，**不推荐**

**验证**: 跑 `python -c "from backend.collectors.github_collector import GitHubCollector; ..."`，看 21 条是否都还入库但不再 mismatch；前端应能显示 18+ 条 github

**风险**: 聚合源豁免后，`item.source` 不再被强制改写，前端会显示 "TopHub GitHub 热榜" 而非 "GitHub"，需前端接受这种 display 形式

### P1: bid — 修复 source_stats health 状态更新

35 dead 源 + 24 last_seen=None 的 active 源从未触发 status 修正。检查 `SourceHealthMachine.apply_run_result()` 是否被 `BidCollector` 触发。

### P1: bid — 迁移到 Crawler v2

`crawler_sources` 表是空的 (seed 流程未触发)，而 `crawler_runs` 也没 bid 记录。整个项目已迁移到 Crawler v2，但 bid 留在了老的 `BidCollector` + `source_stats` 路径。

### P2: bid — 修复 watchdog timeout

偶发 `watchdog: timeout after 600s` 表明 collector 跑得慢（大量 dead 源串行重试）。可以：
- 并发抓取改为 batched
- 失败源快速失败（DNS/SSL 错误直接跳过，不重试）
- 单独调度每个源

### P2: github — 修复 GitHub Trending / Star History

两个源都 dead，依赖单一 TopHub。建议修复：
- `github.com/trending`: 直连 429 限流，需走代理或降低频率
- `star-history`: 是 SPA，需 Playwright 渲染

---

## 6. 验收标准

- [ ] 跑 `python -c "from backend.collectors.bid_collector import BidCollector; ..."`，`items count > 0`
- [ ] DB: `SELECT COUNT(*) FROM hotspots WHERE category='bid' AND ingested_at >= :ago_24h` > 0
- [ ] DB: `SELECT COUNT(*) FROM hotspots WHERE category='github' AND ingested_at >= :ago_24h AND url_check_status='mismatch'` = 0 (或接近 0)
- [ ] API `/api/hotspots?category=github&time_range=24h` 返回 `items.length > 0`
- [ ] API `/api/hotspots?category=bid&time_range=24h` 返回 `items.length > 0`
- [ ] 前端 dashboard 在 "招标资讯" / "GitHub 项目" tab 下显示真实数据

---

## 7. 不要做的事 (避免引入新 bug)

- **不要** 移除整个 NOISE_URL_REGEX (里面 beian.miit.gov.cn / javascript: / mailto: 等黑名单是有用的)
- **不要** 把整个 url_check_status 过滤去掉 (它是抓 anti-bot 假站的核心防护)
- **不要** 直接改写 21 条已有数据的 url_check_status='mismatch' → 静默修数据会污染审计 trail
- **不要** 在 fix 时一并改 bid 关键词体系 (113 个安全词 + 59 个非安全词) — 关键词不是问题

---

## 8. 相关文件

| 文件 | 角色 |
|------|------|
| `backend/collectors/base.py:230-231` | NOISE_URL_REGEX 误杀点 (bid 根因) |
| `backend/quality/config.py:35-44` | NOISE_URL_PATTERNS 定义 (含 `^/`) |
| `backend/quality/author_verification_gate.py:74-83` | mismatch 改写 source (github 根因) |
| `backend/quality/publisher_registry.py:87, 174` | 缺聚合站 alias 映射 |
| `backend/collectors/github_collector.py:_parse_html` | TopHub → github.com URL 提取 |
| `backend/services/hotspot_service.py:155-179` | API 层 query + count 双重过滤 |
| `backend/repository/hotspot_repo.py:638-688` | `count_by_category` 过滤 mismatch |
