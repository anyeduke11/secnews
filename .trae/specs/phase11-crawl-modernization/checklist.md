# Checklist — Phase 11: 抓取层现代化

## BackendSession
- [x] BackendSession GET 请求成功返回文本
- [x] BackendSession retry 机制（5xx / 429 / timeout 重试 3 次）
- [x] BackendSession rate-limit 生效（每源 5/s）
- [x] BackendSession proxy 自动配置
- [x] BackendSession timeout 触发 retry

## 可读 ID 工厂
- [x] `make_readable_id()` 返回 `{source}:{subtype}:{native_id}` 格式
- [x] 同源同 ID 输出相同 readable_id
- [x] 特殊字符正确处理

## trafilatura 集成
- [x] trafilatura 正常 HTML 提取成功
- [x] trafilatura 失败时 fallback 到 `_parse_html()`
- [x] 未安装 trafilatura 时不报错，返回 None

## HN Collector
- [x] 源配置合法（Firestore API，top 30）
- [x] mock 抓取返回 HotspotItem 列表
- [x] sources=[] 返回空列表
- [x] readable_id 格式正确 (`hn:item:{id}`)
- [x] category 正确

## Reddit Collector
- [x] 源配置合法（Reddit JSON API，r/all top 25）
- [x] mock 抓取返回 HotspotItem 列表
- [x] sources=[] 返回空列表
- [x] readable_id 格式正确 (`reddit:post:{id}`)
- [x] category 正确

## OpenBB Collector
- [x] 源配置合法（RSS feed）
- [x] mock 抓取返回 HotspotItem 列表
- [x] sources=[] 返回空列表
- [x] readable_id 格式正确 (`openbb:article:{id}`)
- [x] category 正确

## Telegram Collector
- [x] 源配置合法（公开频道 HTML）
- [x] mock 抓取返回 HotspotItem 列表
- [x] sources=[] 返回空列表
- [x] readable_id 格式正确 (`telegram:post:{id}`)
- [x] category 正确

## GDELT Collector
- [x] 源配置合法（GDELT JSON API）
- [x] mock 抓取返回 HotspotItem 列表
- [x] sources=[] 返回空列表
- [x] readable_id 格式正确 (`gdelt:article:{id}`)
- [x] category 正确

## OSS Insight Collector
- [x] 源配置合法（OSS Insight）
- [x] mock 抓取返回 HotspotItem 列表
- [x] sources=[] 返回空列表
- [x] readable_id 格式正确 (`ossinsight:trend:{id}`)
- [x] category 正确

## pipeline_config
- [x] `config/pipeline.json` 文件存在
- [x] schema 校验通过
- [x] 配置可加载

## 回归测试
- [x] Phase 11 全部测试通过
- [x] 现有 8 collector 回归测试通过
- [x] 新旧 collector 共存验证