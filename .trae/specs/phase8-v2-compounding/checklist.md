# Phase 8 — 复利基础设施 + 资讯收藏聚合 验证清单

> **spec**: `.trae/specs/phase8-v2-compounding/spec.md`
> **tasks**: `.trae/specs/phase8-v2-compounding/tasks.md`

## 1. 数据模型

- [x] 1.1 迁移文件 `043_v2.0_fingerprints_scores.sql` 创建 4 张表（content_fingerprints / ai_scores / item_entities / knowledge_links）
- [x] 1.2 6 个索引全部创建（idx_fp_simhash / idx_fp_url_canonical / idx_ai_score / idx_entity_name / idx_item_id / idx_kl_from / idx_kl_to）
- [x] 1.3 db.py init_db 加载 043 迁移
- [x] 1.4 sqlite3 验证 4 张表存在 + 字段完整 + CHECK 约束
- [x] 1.5 knowledge_repo.list_items() 扩展 `sources`/`keyword`/`exclude_urls` 参数

## 2. simhash 去重

- [x] 2.1 `backend/services/simhash.py` 实现 64-bit simhash 计算
- [x] 2.2 Hamming distance 比较函数实现（阈值 < 5）
- [x] 2.3 URL canonicalize 函数（去除 tracking params、hash、统一协议）
- [x] 2.4 title 规范化函数（小写、去除标点、trim）
- [x] 2.5 集成到 `backend/services/collection_service.py`：collect() 后去重
- [x] 2.6 重复内容自动跳过 + 记录 duplicate_count
- [x] 2.7 test_simhash.py 5 用例全通过

## 3. MCP Tool

- [x] 3.1 `backend/api/mcp_phase8.py` 文件创建并注册 4 个 tool
- [x] 3.2 `score_item` tool：写入 ai_scores 表，返回 score_id
- [x] 3.3 `enrich_concept` tool：写入 concepts/{name}.md，返回 file path
- [x] 3.4 `link_items` tool：写入 knowledge_links 表，返回 link_id
- [x] 3.5 `trigger_codegarden_drift` tool：评估 tech_stack，返回 drift_score
- [x] 3.6 4 tool 全部通过外部 Agent 调通（MCP 协议兼容）
- [x] 3.7 4 tool 的 idempotency 测试通过
- [x] 3.8 test_mcp_phase8.py 8 用例全通过
- [x] 3.9 api/__init__.py 的 register_routers() 包含 mcp_phase8 路由

## 4. 指纹测试

- [x] 4.1 test_fingerprint.py 5 用例全通过（指纹写入、去重检测、重复跳过、索引验证）

## 5. 资讯收藏聚合后端

- [x] 5.1 `backend/services/imported_aggregator.py` 实现 5 源合并逻辑
- [x] 5.2 favorites_repo.list() 拉取收藏数据
- [x] 5.3 knowledge_repo.list_items() 拉取 secnews 数据（扩展参数）
- [x] 5.4 cubox 缓存文件读取
- [x] 5.5 bookmark JSON 文件读取
- [x] 5.6 secnews_archive 标记读取
- [x] 5.7 合并去重（URL 去重）+ 排序（ingested_at DESC）+ 分页
- [x] 5.8 `backend/api/knowledge_imported.py` 实现 GET /api/knowledge/imported
- [x] 5.9 参数：type / keyword / since / until / page / page_size
- [x] 5.10 test_imported_aggregator.py 8 用例全通过
- [x] 5.11 test_knowledge_imported_api.py 7 用例全通过

## 6. 资讯收藏聚合前端

- [x] 6.1 `KnowledgeFavoritesView.tsx` 组件渲染 5 源列表
- [x] 6.2 5 类型筛选（tags/下拉菜单）
- [x] 6.3 名称搜索（input + debounce）
- [x] 6.4 时间范围选择（起止日期）
- [x] 6.5 分页（上一页/下一页/页码）
- [x] 6.6 `useImported.ts` hook 封装 API 调用
- [x] 6.7 5th action card 添加到导航栏
- [x] 6.8 路由配置（`/knowledge/imported`）
- [x] 6.9 KnowledgeFavoritesView.test.tsx 5 用例全通过
- [x] 6.10 e2e 验证：启动 dev → 5th card 跳转 → 5 类型筛选 + 搜索 + 时间 + 分页

## 7. 测试覆盖率

- [x] 7.1 后端总测试用例数 ≥ 38（simhash 5 + mcp 8 + fingerprint 5 + aggregator 8 + api 7 + 未计其他）
- [x] 7.2 前端测试用例数 ≥ 5
- [x] 7.3 后端测试全部通过：`.venv/bin/python -m pytest backend/tests/ -v -k "simhash or mcp_phase8 or fingerprint or imported"`

## 8. 文档

- [x] 8.1 `docs/phase8_changelog.md` 更新（Phase 8 新增功能说明）
- [x] 8.2 `docs/hotspot_v2.0_PRD.md` 中的 Phase 8 验收标准已在 B.11.2 对齐