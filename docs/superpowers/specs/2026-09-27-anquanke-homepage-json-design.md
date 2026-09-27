# 设计：安全客首页 JSON 块解析补齐 (anquanke-homepage-json)

- 日期: 2026-09-27
- 状态: 已批准（owner 裁决: "先立项给安全客加首页 JSON 块解析" — 背景为安全客 RSS 更新滞后, 2026-09-27 实测 RSS 最新 item 停在 09-24 而官网首页日更正常）
- 关联:
  - `docs/superpowers/specs/2026-09-22-settings-refactor-design.md` 无关; 本设计独立小批次
  - 调查证据（2026-09-27 实测，见会话记录）: 安全客源全链路启用无封锁, 拒收日志均为跨轮去重非内容丢失; RSS 只输出 20 条且更新慢, 官网首页 `list` JSON 块含 43 篇文章 id, 覆盖面约 2 倍

## 1. 问题

安全客 (`security:安全客`, `https://www.anquanke.com/`, rss_url=`https://api.anquanke.com/data/v1/rss`) 走 Phase 22 RSS 路由（`fetchers.py`: 源有 `rss_url` → `_fetch_rss`, 完全跳过 HTML 抓取）。RSS 实测缺陷:

1. **更新滞后**: RSS 最新 item pubDate=09-24, 官网首页已更新到 09-27（3 天窗口差）
2. **覆盖面窄**: RSS 固定 20 条, 首页 `list` JSON 块 43 篇（含推荐位/栏目文章, RSS 不收录）

FreeBuf 走同款 RSS 路由但 feed 更新及时（今日已 yield 10 条）, 不在本批次范围。

## 2. 方案

**RSS 主通道不变 + HTML JSON 块作为同源补充抓取**，新增一条"安全客"注册行而不是改既有行：

### 2.1 抓取实现

- `backend/collectors/security_collector.py` 新增源条目:

```python
{
    "name": "安全客首页",  # 与 RSS 源区分; 注册行 id = security:安全客首页
    "url": "https://www.anquanke.com/",
    # 不给 rss_url → 走 HTML 抓取路径 (_parse_html)
    "score": 72,  # 略低于 RSS 源 75: RSS 快照仍优先, 首页块补覆盖
},
```

- `SecurityCollector._parse_html` 已有首页 JSON 块解析能力（Phase 33 注释: 安全客首页 JSON 块 `list` 数组混入 4 类非资讯条目, 已有 `_ANQUANKE_COMPANY_NAME_RE` / `_ANQUANKE_JOB_TITLE_RE` 黑名单过滤 + `anquanke.com` url 域限定）。实施时核实该路径对当前页面结构的解析完整度，按需修复——**只修不重写**。
- 去重依赖既有 `content_hash_duplicate` 硬门（实测工作正常: 跨源/跨轮重复全部被拦）: 同一文章 RSS 先入则首页跳过, 反之亦然, 无需额外协同逻辑。

### 2.2 注册行落库

- 新迁移 `backend/repository/migrations/128_anquanke_homepage_source.sql`（编号以实施时 `migrations/` 实际最大号 +1 为准）:

```sql
INSERT INTO crawler_sources (id, category, name, kind, url, cadence_seconds, priority, max_items, enabled, use_proxy, network_zone, media_kind)
VALUES ('security:安全客首页', 'security', '安全客首页', 'html', 'https://www.anquanke.com/', 1800, 72, 50, 1, 'auto', 'domestic', 'web');
```

- `source_stats` 不预插（首抓自动建行）。

### 2.3 噪声防线（已有, 核实即可）

Phase 33 黑名单: 安全客首页 JSON 块混入的公司名/招聘/活动条目由 `_ANQUANKE_COMPANY_NAME_RE` / `_ANQUANKE_JOB_TITLE_RE` 过滤（仅 `anquanke.com` 域生效）。实测样例（会话调查）: "一口气搞懂 45 个 AI 术语"、"每周AI全球资讯播报" 等正常资讯不被误伤（标题黑名单只打公司名/招聘模式）。

## 3. 明确不做

- 不动 FreeBuf（其 RSS 健康）
- 不动既有 `security:安全客` RSS 源（保留为主通道）
- 不改 `fetchers.py` 路由逻辑（HTML 路径既有）
- 不做标题黑名单扩充（先看真实抓取噪声率, 有问题再迭代）

## 4. 验收

1. 迁移后 `crawler_sources` 出现 `security:安全客首页` 行
2. 手动触发一轮 security 采集（或等 cadence 30min）: 新源 yield > 0, 且包含 RSS 没有的文章（对比两源 item url 集合）
3. `content_hash_duplicate` 拦截 RSS/首页双通道重复, `hotspots` 无重复 URL
4. 噪声抽检: 新源入库条目无招聘/公司宣传类垃圾（Phase 33 黑名单有效）
5. 定向测试: `pytest backend/tests/ -k "security_collector or anquanke" -q` 全绿; 全量 0 failed

## 5. 文档同步义务（收口时）

- DEV_LOG 追加 [DEV-0235]
- PRD 第 6 章 Collectors 无新 collector 文件（SecurityCollector 内部增源）, 数字不变, 仅在 security 源描述处补一句（若该章有源清单）
- `generate_meta --check`: 无新 service/router/job, 预期数字不变

## 6. 后续批次（无）

单任务小批次, 一次交付。
