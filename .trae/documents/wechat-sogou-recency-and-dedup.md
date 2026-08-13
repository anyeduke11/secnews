# 微信公众号抓取脚本更新（搜狗搜索）— 强制 1 周窗口 + 反重复 + 反离题

## Context

`backend/collectors/sogou_search.py` 走 `weixin.sogou.com` 抓微信公众号文章,被 security / ai / tech / finance 四个 collector 共用。当前存在三个问题:

1. **时效过宽**:`backend/collectors/item_builder.py:73` 对 `renderer == "wechat"` 用 `now - 30 days` 作为 `recency_threshold`,实际抓到 1-3 周前甚至更老的文章还会入库。原因是"搜狗索引的文章日期可能较旧"的妥协,现在用户要求收紧。
2. **重复抓取浪费**:每次 scheduler tick 都重新 `fetch_weixin_html` + 解析整套响应。同一批文章会被反复解析,直到 `DuplicateGate` 在入库时挡掉。浪费的是 HTTP 请求 + 解析 + quality pipeline 调用。
3. **离题内容漏过**:`_is_title_blocked` 只挡 招聘/校招/广告/隐私/协议,娱乐/明星/养生/旅游/带货/鸡汤 等与"AI+安全"主题无关的内容会进入候选,再被 `_title_relevant` 关键词白名单二次过滤(只对 `ai` 分类生效,`security` 分类默认放行)。

**用户要求(2026-08-04)**:
- 只抓一周内的资讯(7 天)
- 任何抓取窗口硬上限 14 天
- 禁止重复抓取
- 禁止抓取非相关主题
- 沿用现有实现思路(sogou weixin 搜索路径)

**目标**:让 `renderer == "wechat"` 的源默认抓 7 天内的文章,硬上限 14 天;在 fetch 层就跳过 DB 中已存在的 URL;在 parse 层加严"非相关主题"黑名单,大幅降低入库前的噪声。

---

## 实施方案

### 1. `backend/collectors/sogou_search.py` — 增强 `parse_wechat_articles_html`

新签名(在现有 `(html, account_name, max_items)` 基础上扩展):

```python
def parse_wechat_articles_html(
    html: str,
    account_name: str | None = None,
    max_items: int = 20,
    *,
    max_age_days: int = 7,                    # 新增:一周默认
    topic_keywords: list[str] | None = None,  # 新增:可选正面白名单(默认 None=不强制)
    seen_urls_external: set[str] | None = None,  # 新增:DB 已存在的 URL,跨次去重
) -> list[dict[str, Any]]:
```

**过滤逻辑(每条 article 都要过 4 道关)**:

```python
now = datetime.now(timezone.utc)
cutoff = now - timedelta(days=min(max_age_days, 14))  # 硬上限 14 天

for m in _WEIXIN_BLOCK_RE.finditer(html):
    # ... 现有解析 title/url/summary/account_name/published_at ...

    # 关 1: 黑名单(招聘/校招/广告/隐私) — 已存在
    if _is_title_blocked(title):
        continue

    # 关 1.5: 新增"非相关主题"黑名单(娱乐/明星/养生/旅游/带货/鸡汤/游戏/体育/时尚)
    if _NON_RELEVANT_TOPIC_RE.search(title):
        continue

    # 关 2: 新增正面白名单(如 source 指定了 topic_keywords,标题必须命中至少 1 个)
    if topic_keywords and not any(kw in title for kw in topic_keywords):
        continue

    # 关 3: 7 天(硬上限 14 天)时效门禁 — 缺失 published_at 一律拒绝
    if published_at is None or published_at < cutoff:
        continue

    # 关 4: 跨次去重 — 已在 DB 内的 URL 跳过
    if seen_urls_external and full_url in seen_urls_external:
        continue
```

**新增模块级常量**(放在 `_TITLE_BLOCKLIST_RE` 附近):

```python
# 非相关主题黑名单 — 娱乐/明星/养生/旅游/带货/鸡汤/游戏/体育/时尚等
# 与本项目定位"AI + 安全"无关,即使来源是科技/财经公众号也应拒收
_NON_RELEVANT_TOPIC_RE = re.compile(
    r"(?:"
    r"娱乐|明星|八卦|爆料|绯闻|"
    r"美食|菜谱|食谱|探店|餐厅|"
    r"旅游|景点|民宿|酒店|攻略|"
    r"养生|保健|减肥|瘦身|美容|护肤|化妆|"
    r"星座|运势|塔罗|"
    r"鸡汤|励志|情感|恋爱|婚姻|"
    r"带货|直播|主播|种草|安利|"
    r"游戏|电竞|手游|端游|主机|"
    r"体育|赛事|世界杯|奥运|CBA|NBA|中超|"
    r"时尚|穿搭|街拍|潮流|"
    r"萌宠|宠物|猫狗|"
    r"育儿|母婴|幼儿|早教|"
    r"家居|装修|户型"
    r")",
    re.IGNORECASE,
)
```

> **不强制 topic_keywords**:现有源配置没有这个字段,新逻辑不传 = 不做正面白名单,只靠黑名单拦截离题内容。后续如果某个源要更严,可显式配置。

### 2. `backend/collectors/fetchers.py` — `_fetch_wechat_source` 接线

把 source config 的 `max_age_days` / `topic_keywords` 传给 parser,并在 parse 前查一次 DB:

```python
async def _fetch_wechat_source(
    self, source: dict, start: datetime
) -> tuple[list[HotspotItem], SourceResult]:
    from backend.collectors.sogou_search import (
        fetch_weixin_html, parse_wechat_articles_html,
    )
    from backend.repository.hotspot_repo import hotspot_repo  # 新增导入

    account_name = source.get("account_name") or source.get("name", "")
    if not account_name:
        return [], SourceResult(...)

    max_items = source.get("max_items", 15) or 15
    max_age_days = min(int(source.get("max_age_days", 7) or 7), 14)  # 硬上限 14
    topic_keywords = source.get("topic_keywords")  # None = 不强制

    # 跨次去重:查询 source 在 7 天窗口内已入库的 URL 集合
    seen_urls_external: set[str] = set()
    try:
        cutoff_iso = (datetime.now(timezone.utc)
                      - timedelta(days=max_age_days)).isoformat()
        seen_urls_external = hotspot_repo.list_recent_urls_by_source(
            source_name=source["name"], since_iso=cutoff_iso,
        )
    except Exception as e:
        self.logger.debug(
            f"wechat dedup query failed for {account_name}: {e}"
        )
        # 查询失败 = 不去重,继续抓(避免阻塞主路径)

    # ... 现有 _wechat_lock + 随机延迟 + fetch_weixin_html ...

    try:
        raw_items = parse_wechat_articles_html(
            html,
            account_name=account_name,
            max_items=max_items,
            max_age_days=max_age_days,
            topic_keywords=topic_keywords,
            seen_urls_external=seen_urls_external,
        )
        items = self._build_items(raw_items, source)
    # ... 现有 error handling ...
```

**SourceResult 增加 dedup 计数**(可选,便于运维):
不增字段,改在 logger 里加一条 `wechat dedup: account=X db_urls=N kept=M`,与现有日志风格一致。

### 3. `backend/repository/hotspot_repo.py` — 新增小 helper

```python
def list_recent_urls_by_source(
    self, source_name: str, since_iso: str,
) -> set[str]:
    """返回 ``source`` 列匹配 ``source_name`` 且 ``ingested_at >= since_iso`` 的去重 URL 集合。

    用途:公众号 wechat renderer 在抓取前预查询,跳过 DB 中已存在的 URL,
    避免每次 scheduler tick 都重复 fetch + parse + quality pipeline 同一批老文章。
    """
    if not source_name:
        return set()
    conn = get_connection()
    rows = conn.execute(
        "SELECT DISTINCT url FROM hotspots "
        "WHERE source = ? AND COALESCE(ingested_at, published_at) >= ?",
        (source_name, since_iso),
    ).fetchall()
    return {str(r["url"]) for r in rows if r["url"]}
```

放在 `count_unique_urls_in_range` 之后(同区域、读路径)。

### 4. `backend/collectors/item_builder.py` — 时效门禁同步收紧

把第 73 行的 wechat 特例从硬编码 30 天改为读取 source 的 `max_age_days`:

```python
# 旧:
if renderer == "wechat":
    recency_threshold = now - __import__("datetime").timedelta(days=30)
else:
    recency_threshold = current_week_start()

# 新:
if renderer == "wechat":
    wechat_max_age = int(source.get("max_age_days", 7) or 7)
    wechat_max_age = max(1, min(wechat_max_age, 14))  # 硬上限 14
    recency_threshold = now - __import__("datetime").timedelta(days=wechat_max_age)
else:
    recency_threshold = current_week_start()
```

> **与 parser 二重门**:parser 在 `parse_wechat_articles_html` 已经按 `max_age_days` 过滤过,这里再过一遍是 defense-in-depth(防止 source dict 漏传 / 解析路径绕开)。

### 5. (可选)把显式 `max_age_days=7` 加到现有 WeChat 源

**不推荐** — 默认值已经是 7,source dict 不写就是 7。保持"显式优于隐式"的话可以加,但 surgical changes 原则(Rule 3)下不动,等用户真要调时再加。

### 6. 测试

新增 `backend/tests/test_sogou_wechat_recency.py`(纯函数,无 DB):

| 用例 | 输入 | 期望 |
|------|------|------|
| `test_7d_default_rejects_10d_old` | `published_at = now-10d` | 拒收 |
| `test_7d_default_keeps_3d_old` | `published_at = now-3d` | 通过 |
| `test_14d_hard_cap_rejects_30d_old` | `max_age_days=14, published_at=now-30d` | 拒收(14d 兜底) |
| `test_max_age_days_capped_at_14` | `max_age_days=99, published_at=now-15d` | 拒收(99 被 cap 到 14) |
| `test_no_published_at_rejected` | `published_at=None` | 拒收 |
| `test_topic_blocklist_filters_entertainment` | title="某明星八卦爆料" | 拒收 |
| `test_topic_blocklist_filters_travel` | title="xxx 5 月旅游攻略" | 拒收 |
| `test_topic_blocklist_keeps_security` | title="某 APT 组织最新活动" | 通过 |
| `test_seen_urls_external_dedup` | `seen_urls_external={full_url}` | 拒收 |
| `test_seen_urls_external_dedup_distinct` | `seen_urls_external` 不含 | 通过 |
| `test_topic_keywords_positive_filter` | `topic_keywords=["GPT","AI"]`, title="娱乐八卦" | 拒收(没命中白名单) |
| `test_topic_keywords_positive_filter_match` | `topic_keywords=["GPT"]`, title="GPT-5 发布" | 通过 |

---

## 关键文件清单

| 文件 | 修改内容 |
|------|----------|
| `backend/collectors/sogou_search.py` | `parse_wechat_articles_html` 新增 3 个参数 + 新增 `_NON_RELEVANT_TOPIC_RE` 常量 |
| `backend/collectors/fetchers.py` | `_fetch_wechat_source` 读取 source.max_age_days / topic_keywords,新增 DB 预查询,透传给 parser |
| `backend/repository/hotspot_repo.py` | 新增 `list_recent_urls_by_source(source_name, since_iso) -> set[str]` |
| `backend/collectors/item_builder.py` | `_build_items` 中 wechat 特例改读 source.max_age_days(默认 7,硬上限 14) |
| `backend/tests/test_sogou_wechat_recency.py` | 新增 ~12 个纯函数测试 |

## 复用的现有 utilities

- `_TITLE_BLOCKLIST_RE` / `_is_title_blocked` (`sogou_search.py:84-92,175-179`) — 现有黑名单,继续用
- `_WEIXIN_BLOCK_RE` / `_ACCOUNT_NAME_RE` / `_TIMESTAMP_RE` / `_clean_html_text` / `_parse_unix_timestamp` (`sogou_search.py:287-313`) — 现有解析器,不动
- `_wechat_lock` (`fetchers.py:32`) — 现有串行化锁,继续用
- `get_connection` (`backend/repository/db.py`) — DB helper,新 helper 沿用

---

## 验证步骤

1. **单测**: `cd backend && .venv/bin/python3 -m pytest backend/tests/test_sogou_wechat_recency.py -v`
2. **全量后端测试**: `.venv/bin/python3 -m pytest backend/tests/ -k "wechat or sogou or fetch" -v`(确保不破现有路径)
3. **类型检查**: `cd frontend && npx tsc --noEmit`(前端的测试组件没动,只走个保险)
4. **手动抽测**: 启动后端 `python run.py`, 触发一次 `security` 分类的 collect,看 `/api/hotspots?category=security` 返回的 items:
   - 所有 `published_at` 都在最近 7 天内
   - 同一篇文章不会重复出现(在已存在的情况下)
   - 标题没有"明星/八卦/养生"等离题词
5. **日志抽查**: 跑完后看日志有没有 `wechat dedup: account=X db_urls=N` 这种新 log(可选)

## 不在范围内

- 不改 source dict(`max_age_days` 默认 7,无需改任何源)
- 不动 RSS / crawl4ai / aiohttp 路径(只动 wechat renderer)
- 不改 `parse_sogou_weixin_html`(那是 sogou.com/web 通用搜索,非公众号专用)
- 不动 `category_keywords`(`_CAT_KEYWORDS` 已有的 AI / security 白名单对 ai 分类已生效,wechat 路径已受益)
- 不动 `DuplicateGate`(仍保留作为最终兜底)
- 不动 `recency_threshold` 的非-wechat 路径(其他 renderer 仍走 `current_week_start()`)
