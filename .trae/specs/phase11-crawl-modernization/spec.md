# Phase 11 — 抓取层现代化 (BackendSession + 可读 ID + trafilatura + 6 新 collector)

> **版本**: v2.0 (Phase 11)
> **日期**: 2026-07-29
> **周期**: ~5 天
> **spec 路径**: `.trae/specs/phase11-crawl-modernization/`
> **PRD 章节**: `docs/hotspot_v2.0_PRD.md` B.10.4
> **开发计划**: `docs/hotspot_v2.0_dev_plan.md` Phase 11
> **前置**: Phase 10 (T1/T2 触发器) ✅ + 046 迁移 ✅

---

## 1. 背景与目标

### 1.1 背景

hotspot v1.7 的抓取层由 8 个 collector 组成（AI / Security / Finance / Startup / Bid / GitHub / Tech / AISecurity），每个 collector 直接使用 `aiohttp.ClientSession` 或 `ProxySession` 进行 HTTP 请求。目前存在以下问题：

1. **Session 不统一**：每个 collector 各自创建 session，没有统一的 retry / rate-limit / timeout 策略
2. **ID 不可读**：HotspotItem.id 使用 sha256 hash，无法从 ID 推断来源
3. **HTML 提取单一**：仅靠 `_parse_html()` 的 CSS Selector / 正则提取，无结构化提取器
4. **数据源覆盖不足**：缺少 HN / Reddit / OpenBB / Telegram / GDELT / OSS Insight 等优质信源

### 1.2 目标

1. **BackendSession**：httpx 统一 session，内置 proxy + retry + rate-limit + timeout
2. **可读 ID 工厂**：`readable_id` 格式 `{source}:{subtype}:{native_id}`，旧 hash ID 保留为 `hotspot_id`
3. **trafilatura 集成**：作为可选 HTML 提取器，fallback 到现有 `_parse_html()`
4. **6 个新 collector**：HN / Reddit / OpenBB / Telegram / GDELT / OSS Insight
5. **JSON pipeline_config**：集中式 pipeline 配置（源列表 + 阈值 + 输出）
6. **测试覆盖**：6 collector × 5 用例 + BackendSession 注入 + trafilatura fallback

---

## 2. 变更范围

### 2.1 新增文件

| 文件 | 类型 | 说明 |
|------|------|------|
| `backend/collectors/session.py` | 后端 | BackendSession：httpx + proxy + retry + rate-limit |
| `backend/collectors/id_factory.py` | 后端 | 可读 ID 工厂：`{source}:{subtype}:{native_id}` |
| `backend/parsers/trafilatura_parser.py` | 后端 | trafilatura 可选提取器 |
| `backend/collectors/hn_collector.py` | 后端 | HackerNews collector |
| `backend/collectors/reddit_collector.py` | 后端 | Reddit collector |
| `backend/collectors/openbb_collector.py` | 后端 | OpenBB collector |
| `backend/collectors/telegram_collector.py` | 后端 | Telegram collector |
| `backend/collectors/gdelt_collector.py` | 后端 | GDELT collector |
| `backend/collectors/ossinsight_collector.py` | 后端 | OSS Insight collector |
| `config/pipeline.json` | 配置 | 集中式 pipeline 配置 |
| `backend/tests/test_phase11_collectors.py` | 测试 | 6 collector × 5 用例 |
| `backend/tests/test_backend_session.py` | 测试 | BackendSession 注入测试 |
| `backend/tests/test_trafilatura.py` | 测试 | trafilatura fallback 测试 |

### 2.2 修改文件

| 文件 | 变更 |
|------|------|
| `backend/collectors/__init__.py` | 导出新模块 |
| `backend/collectors/base.py` | 接入 BackendSession 作为默认 session 工厂 |
| `backend/api/__init__.py` | 注册新 collector（如 API 直接调用） |
| `backend/config.py` | 新增 pipeline.json 路径配置 |

### 2.3 不修改的文件

- 现有 8 个 collector 的 `sources` 列表不修改
- 现有 `proxy_session.py` 保留兼容（不删除）
- 现有 `collectors/base.py` 的 `_session_factory` 保留（**不**替换为 BackendSession，仅新增可选接入路径）

---

## 3. 详细设计

### 3.1 BackendSession

```python
# backend/collectors/session.py

class BackendSession:
    """
    httpx 统一 HTTP 客户端。
    
    - proxy: 自动从 proxy_config 读取代理配置
    - retry: 指数退避（1s/3s/10s），最多 3 次
    - rate-limit: 每源每秒最多 N 请求（默认 5/s）
    - timeout: 连接 10s + 读取 30s
    """
```

**设计要点**:
- 使用 `httpx.AsyncClient` 替代 `aiohttp.ClientSession`
- retry 策略：`(1, 3, 10)` 秒指数退避，仅对 `5xx` / `429` / `timeout` 重试
- rate-limit：使用 `asyncio.Semaphore` 或 `asyncio.Semaphore` 每源限制
- proxy：复用 `proxy_config.get_proxy_url()` / `should_use_proxy()` 逻辑
- 与现有 `ProxySession` 共存（`BackendSession` 是新增可选路径，不替换现有 session）

**使用示例**:
```python
from backend.collectors.session import BackendSession

async with BackendSession() as session:
    text = await session.get("https://example.com/data")
```

### 3.2 可读 ID 工厂

```python
# backend/collectors/id_factory.py

def make_readable_id(source: str, subtype: str, native_id: str) -> str:
    """生成可读 ID: {source}:{subtype}:{native_id}
    
    - source: 源名称（小写，如 "hn", "reddit"）
    - subtype: 子类型（如 "item", "comment", "post"）
    - native_id: 源原生 ID（如 HN 的 story ID）
    - 返回: "hn:item:12345678"
    """
```

**设计要点**:
- 新 collector 使用 `readable_id` 作为 `HotspotItem.id`
- 旧 collector 的 sha256 hash ID 保留为 `hotspot_id` 字段（不修改）
- 双写策略：新 collector 写 `id=readable_id`；旧 collector 写 `id=sha256_url`
- `readable_id` 可作为 `hotspot_id` 的别名（通过 `hotspot_id` 字段兼容）

### 3.3 trafilatura 集成

```python
# backend/parsers/trafilatura_parser.py

def extract_content(html: str, url: str) -> dict | None:
    """使用 trafilatura 从 HTML 提取结构化内容。
    
    返回: {"title", "text", "author", "date", "categories", "tags"} 或 None
    """
```

**设计要点**:
- trafilatura 是可选依赖（`pip install trafilatura`），未安装时返回 None
- 调用链：`BaseCollector.fetch_source()` 尝试 trafilatura → 失败 fallback 到 `_parse_html()`
- 仅在 `source` 配置中标记 `"extractor": "trafilatura"` 时启用
- 适用于正文内容丰富的站点（如 HN 文章详情页）

### 3.4 6 个新 collector

每个 collector 继承 `BaseCollector`，遵循现有模式：

| Collector | 源类型 | API/URL | 特殊处理 |
|-----------|--------|---------|---------|
| **HN** | JSON API | `https://hacker-news.firebaseio.com/v0/` | Firestore API，top 30 stories |
| **Reddit** | JSON API | `https://www.reddit.com/r/all/top.json` | JSON 端点，限制 25 条 |
| **OpenBB** | RSS | `https://openbb.co/rss/` | RSS feed，金融/数据新闻 |
| **Telegram** | Web | 公开频道 HTML 抓取 | 使用 `renderer: "aiohttp"` |
| **GDELT** | JSON API | `https://api.gdeltproject.org/api/v2/` | 实时新闻 API |
| **OSS Insight** | Web | `https://ossinsight.io/` | 开源项目趋势 |

**抗反爬策略**:
- 3 个优先实现（HN / Reddit / OpenBB）：JSON API + RSS 为主，反爬风险低
- 3 个延迟实现（Telegram / GDELT / OSS Insight）：如遇到反爬，`collect()` 返回空并记录 warning
- 所有 collector 通过 `BackendSession` 走统一代理

### 3.5 JSON pipeline_config

```json
{
  "version": "1.0",
  "pipeline": {
    "default_output": "knowledge_items",
    "thresholds": {
      "min_score": 7,
      "max_items_per_source": 50
    }
  },
  "sources": [
    {"name": "hn", "enabled": true, "url": "https://hacker-news.firebaseio.com/v0/"},
    {"name": "reddit", "enabled": true, "url": "https://www.reddit.com/r/all/top.json"}
  ]
}
```

---

## 4. 测试计划

### 4.1 BackendSession 测试 (5 用例)

| 用例 | 验证 |
|------|------|
| `test_backend_session_get` | GET 请求成功返回文本 |
| `test_backend_session_retry` | 模拟 5xx 错误，验证重试 3 次 |
| `test_backend_session_rate_limit` | 短时间内多发请求，验证不超限制 |
| `test_backend_session_proxy` | 代理配置生效 |
| `test_backend_session_timeout` | 超时触发 retry |

### 4.2 可读 ID 测试 (3 用例)

| 用例 | 验证 |
|------|------|
| `test_make_readable_id` | 格式正确 `{source}:{subtype}:{native_id}` |
| `test_readable_id_uniqueness` | 同源同 ID 输出相同 readable_id |
| `test_readable_id_special_chars` | 特殊字符正确处理 |

### 4.3 trafilatura 测试 (3 用例)

| 用例 | 验证 |
|------|------|
| `test_trafilatura_extract` | 正常 HTML 提取成功 |
| `test_trafilatura_fallback` | trafilatura 失败时 fallback 到 _parse_html |
| `test_trafilatura_not_installed` | 未安装时不报错，返回 None |

### 4.4 Collector 测试 (6 collector × 5 用例 = 30 用例)

每个 collector 覆盖：

| 用例 | 验证 |
|------|------|
| `test_<name>_returns_hotspot_items` | mock 成功抓取，返回 HotspotItem 列表 |
| `test_<name>_returns_empty_when_sources_fail` | sources=[] 返回空列表 |
| `test_<name>_readable_id_format` | 生成的 readable_id 格式正确 |
| `test_<name>_category_correct` | category 正确（AI / Security 等） |
| `test_<name>_source_config_valid` | 源配置合法（url/name/score 完整） |

---

## 5. 验收标准

| # | 标准 | 验证方式 |
|---|------|---------|
| 1 | BackendSession GET / retry / rate-limit / proxy 通过 | 5 用例 |
| 2 | 可读 ID 格式正确，100% 映射 | 3 用例 |
| 3 | trafilatura fallback 正常 | 3 用例 |
| 4 | 6 collector × 5 用例全部通过 | 30 用例 |
| 5 | 新旧 collector 共存，现有 8 collector 测试不失败 | 全量回归 |
| 6 | pipeline_config.json schema 校验通过 | 手动验证 |
| 7 | 现有 collector 的 `_session_factory` 不受影响 | 回归测试 |