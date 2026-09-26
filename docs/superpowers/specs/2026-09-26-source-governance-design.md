# 数据源体系治理 + 介质分类 + 手动管理 — 设计稿 (2026-09-26)

## 1. 第一性原理分析结论 (实测 2026-09-26)

数据源本质 = 向管线供给「过门资讯」的通道。根本属性四维: **介质**(内容从哪来) /
**有效性**(可达×产出×时效) / **价值密度**(质量×域命中) / **成本**(耗时×封锁风险)。

三层结构实测:
- 注册层 crawler_sources 37 源 (html 26 / rss 11): 健康机+自动退役运行良好, 但无介质分类、无手动删除
- 统计层 source_stats 152 行: 56 行从未产出 (dead+total=0 空壳注册)、同源跨类目重复行 (UI 矩阵 77 源假象的来源)
- 用户层 custom_sources 0 行: CRUD API 完整且参与真实采集 (inject_custom_sources), 纯粹缺前端使用

通道介质: 常规网页 37 (主力健康) / 微信 0 (搜狗镜像 8 月被反爬封禁, 6 源全灭各 ~1300 产出) / 多媒体 0 (完全空白)。

## 2. owner 裁决 (2026-09-26)

1. 微信通道: **归档待替代** — 6 个(搜狗)源标 media_kind='wechat' + retired, 保留审计, 待自建 RSSHub 等替代通道再激活。
2. 多媒体: **建框架 + 首批 2-3 个安全向视频源** (media_kind='multimedia', 如 YouTube 安全频道公开 RSS / B 站 API)。
3. 系统源: **支持彻底删除** (含审计记录); 自定义源已有 CRUD。

## 3. 设计

### 3.1 介质维度 (media_kind)

- migration: `ALTER TABLE crawler_sources ADD COLUMN media_kind TEXT NOT NULL DEFAULT 'web'`
- 值域: `web` / `wechat` / `multimedia` (kind 列保留 = 采集方式 html/rss, 与介质正交)
- 存量推断: name 含 `(搜狗)` → wechat; url 含 youtube/bilibili → multimedia; 其余 web
- source_stats 同步加 media_kind (同推断规则), 供矩阵分组

### 3.2 清理 (审计表 source_cleanup_log)

- 新表: `source_cleanup_log(id, source_layer, source_ident, reason, executed_at, executed_by)`
- 清理对象: source_stats 中 `status='dead' AND total_items=0` 的 56 行 (从未产出 = 与供给目标无实质关联)
- 不清理: 12 个有产出的 dead (复活探测覆盖) / 15 个 retired (审计资产)
- 脚本 `scripts/fix_source_stats_cleanup.py`: --dry-run 默认, 逐行写 source_cleanup_log 后 DELETE, 幂等
- 对应 crawler_sources 已 retired 的 15 个维持 (健康机资产)

### 3.3 系统源手动管理

- 新端点 (挂既有 source 域 router, 行数门内): `DELETE /api/sources/system/{id}` — 软语义=物理删 crawler_sources 行, 但**必须**先写 source_cleanup_log (reason 必填由前端传入) + 同步删对应 source_stats 行; `PATCH /api/sources/system/{id}` enable/disable toggle
- 防呆: 删除前若 status='active' 需前端二次确认 (后端不强拦, 记审计)

### 3.4 多媒体首批源

- 注册 2-3 个安全向视频源进 crawler_sources (media_kind='multimedia'):
  YouTube 公开 RSS (`youtube.com/feeds/videos.xml?channel_id=...`, 需代理) / B 站 UP 主 API — 实现时以 probe 通过为准, probe 不过则换源并在汇报说明
- 采集: 复用 rss/html collector 路径 (RSS 是标准格式), category 归 security 或新建? → 归入既有类目, 不新增 Category 枚举

### 3.5 前端

- 源健康矩阵 (SourceMatrixCard): 按 media_kind 分组 tab 或筛选器 (全部/微信/网页/多媒体); 清理后 77→~80 行口径自然收敛; retired 行灰显
- 设置页采集分区核验: 手动添加入口 = custom 源 API 的前端挂载点 (无则补一张"手动添加源"卡)

## 4. 实施任务

- **T1** migration (media_kind 两表) + 存量推断 + 搜狗归档 + 首批多媒体源注册 + 测试
- **T2** 清理脚本 + source_cleanup_log 表 + 系统源 DELETE/PATCH API + 测试
- **T3** 前端矩阵分组/筛选 + 手动添加入口核验 + 测试
- **T4** 收口: 全量回归 + DEV-0232 + 计划落账

## 5. 非目标

- 不做微信通道替代实现 (RSSHub 自建另立项)
- 不改 13 collector 抓取本体; 不动健康机状态机语义
