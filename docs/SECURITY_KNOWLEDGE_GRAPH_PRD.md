# 安全知识图谱专项 · 产品需求文档（PRD）

> **版本**: v1.0.0
> **日期**: 2026-07-20
> **产品**: hotspot（热点地图）
> **模块**: 安全知识图谱 + 安全术语标准化
> **基线**: hotspot v1.5+（Phase 53 之后）
> **开源协议**: MIT License（继承 hotspot）
> **关联文档**:
> - [SECURITY_KNOWLEDGE_GRAPH.md](./SECURITY_KNOWLEDGE_GRAPH.md) 系统架构
> - [SECURITY_KNOWLEDGE_GRAPH_DEV_PLAN.md](./SECURITY_KNOWLEDGE_GRAPH_DEV_PLAN.md) 开发计划
> - [ARCHITECTURE.md](./ARCHITECTURE.md) hotspot 主架构
> - [CodeGarden_PRD_v1.7.md](./CodeGarden_PRD_v1.7.md) CodeGarden PRD（分层对齐参考）

---

## 0. 版本变更说明

### v1.0.0 初始版本

| 模块 | 说明 |
|---|---|
| 安全知识图谱 | MITRE ATT&CK + NVD CVE + 合规本体的结构化存储与可视化 |
| 安全术语标准化 | canonical term + synonym + taxonomy，消除标签歧义 |
| 热点 enrichment | 采集后自动提取 CVE/ATT&CK/合规标签（异步，不阻塞主路径） |
| 前端安全视图 | KnowledgePage 内嵌 ATT&CK/CVE/合规矩阵/时间线视图 |

---

## 1. 产品概述

### 1.1 产品定位

安全知识图谱是 hotspot 的**安全领域专项增强模块**，为 IT 安全从业者提供：
1. **结构化安全情报**：将散落在热点资讯中的 CVE、ATT&CK 技术、合规条款提取出来，建立关联
2. **术语统一**：消除安全领域标签歧义，建立内部知识库的标准语言
3. **专业视图**：ATT&CK 战术/技术图谱、CVE 时间线、合规覆盖度矩阵

### 1.2 目标用户

| 用户画像 | 核心需求 | 本模块价值 |
|---|---|---|
| 安全运营分析师 | 快速追踪新 CVE、理解攻击技术、对齐检测策略 | CVE 时间线 + ATT&CK 图谱 + 知识条目关联 |
| 等保/合规专员 | 监控法规动态、评估合规覆盖度 | 合规矩阵 + 条款 ↔ 热点映射 |
| 渗透测试工程师 | 研究 ATT&CK 技术、查找相关漏洞利用 | ATT&CK 图谱 + CVE 关联 + 技术详情 |
| 安全团队负责人 | 掌握团队关注的安全领域分布、知识缺口 | 安全知识图谱 + 术语统计 |

### 1.3 核心价值主张

> **"从安全热点流中自动提取结构化知识，建立 CVE → 技术 → 合规 → 知识的关联网络，让每一次阅读都成为知识图谱的一次扩展。"**

### 1.4 与 hotspot 主产品的关系

```
┌──────────────────────────────────────────────────────────────────┐
│                      hotspot v1.5+ 平台                           │
├──────────────────────┬───────────────────────────────────────────┤
│  SecNews 资讯聚合    │  Knowledge LLM-Wiki 知识管理              │
│  (安全/AI/科技资讯)  │  (items/concepts/learning/content)        │
├──────────────────────┼───────────────────────────────────────────┤
│                      │  Security Knowledge Graph (本 PRD)       │
│   共享基础设施        │  • ATT&CK 战术/技术图谱                   │
│  ─────────────────   │  • CVE 漏洞关联 + NVD  enrichment       │
│  • FastAPI 后端      │  • 合规条款映射（等保/关基/数据安全法）   │
│  • React 前端        │  • 安全术语标准化（同义词/层级）           │
│  • SQLite + 同步包   │  • CVE 时间线 + 热点关联                  │
│  • 任务队列          │                                           │
│  • Secrets 管理      │                                           │
│  • Skill 系统        │                                           │
│  • 知识联邦          │                                           │
└──────────────────────┴───────────────────────────────────────────┘
```

### 1.5 关键决策

| 决策项 | 结论 | 理由 |
|---|---|---|
| 部署形态 | 复用 hotspot 本地 Web 服务 | 单进程、零额外部署成本 |
| 数据存储 | 复用 `hotspot.db`，新增 5 张表 + 2 张表扩展 | 与现有 Repository 模式一致 |
| MITRE ATT&CK 存储 | 全量 STIX 解析 → `security_entities` + `security_edges` | 支持离线查询，MITRE CC-BY-4.0 |
| NVD CVE 查询 | 按需查询 + 本地缓存（TTL 30 天） | 20 万+ CVE 不适合全量同步 |
| 图谱展示 | 同构合并，前端 view 切换 | 不新建页面，复用 `KnowledgeGraph.tsx` |
| 术语标准化 | 可选调用，不强制 | 保持 `auto_classifier.py` 纯函数 |
| 跨端同步 | `security_terms` 纳入 sync_bundle；`security_entities`/`security_edges` 不纳入 | 前者用户自定义，后者可重建 |

---

## 2. 用户故事与需求

### 2.1 用户故事地图

| 用户角色 | 需求 | 故事 | 优先级 |
|---|---|---|---|
| 安全运营分析师 | CVE 追踪 | 作为安全运营分析师，我希望热点条目中的 CVE 自动提取并关联 NVD 详情，以便快速评估影响 | **P0** |
| 安全运营分析师 | ATT&CK 图谱 | 作为安全运营分析师，我希望看到 ATT&CK 战术/技术图谱，以便理解攻击路径 | **P0** |
| 安全运营分析师 | 术语统一 | 作为安全运营分析师，我希望安全标签统一规范，以便知识库搜索不遗漏 | **P1** |
| 等保/合规专员 | 合规映射 | 作为合规专员，我希望看到热点内容 ↔ 等保/关基条款的映射，以便评估合规覆盖度 | **P1** |
| 渗透测试工程师 | 技术关联 | 作为渗透测试工程师，我希望通过 ATT&CK 技术查找相关 CVE 和知识条目，以便研究利用方式 | **P1** |
| 安全团队负责人 | 术语管理 | 作为安全团队负责人，我希望管理安全术语同义词和层级，以便团队使用统一语言 | **P2** |
| 安全团队负责人 | 知识图谱统计 | 作为安全团队负责人，我希望看到安全知识图谱的统计（CVE 数量、技术覆盖度等），以便评估知识库健康度 | **P2** |

### 2.2 功能需求

#### FR-SG-01：安全实体存储

**需求描述**：系统能够存储和管理安全领域结构化实体（CVE、ATT&CK、合规条款等）。

**验收标准**：
- [ ] 支持 7 种实体类型：tactic / technique / cve / cwe / compliance / product / cpe
- [ ] 每个实体有唯一 ID、名称、描述、外部引用链接
- [ ] 实体 metadata 字段支持存储 CVSS、severity 等扩展属性
- [ ] 支持按 entity_type 查询
- [ ] 支持按名称模糊搜索

#### FR-SG-02：安全语义边

**需求描述**：系统能够表达安全实体之间的语义关系。

**验收标准**：
- [ ] 支持 7 种边类型：uses / subtechnique-of / mitigates / causes / fixes / requires / related-to
- [ ] 边有权重属性（强度/置信度）
- [ ] 支持查询某节点的关联节点（指定深度）
- [ ] 支持按边类型过滤

#### FR-SG-03：MITRE ATT&CK 同步

**需求描述**：系统能够从 MITRE ATT&CK 同步战术/技术/软件/分组数据。

**验收标准**：
- [ ] 支持首次全量同步（STIX bundle → security_entities + security_edges）
- [ ] 支持每周增量同步（检测 MITRE GitHub 更新）
- [ ] 同步失败不影响采集主路径
- [ ] 同步完成后可查询 ATT&CK 战术/技术图谱

#### FR-SG-04：NVD CVE 按需查询

**需求描述**：系统能够在热点条目中提取 CVE ID，并按需查询 NVD 补全详情。

**验收标准**：
- [ ] 正则提取 CVE ID（CVE-YYYY-NNNNN）
- [ ] 查询本地缓存，未命中时调用 NVD API 2.0
- [ ] NVD 结果缓存 30 天
- [ ] NVD 故障时降级（使用本地已有数据，不阻塞）
- [ ] 支持 rate limit 处理（指数退避）

#### FR-SG-05：热点条目 Enrichment

**需求描述**：系统能够对热点条目自动提取安全实体标签。

**验收标准**：
- [ ] 正则提取 CVE IDs → 存入 `knowledge_items.cve_ids`
- [ ] 正则提取 ATT&CK IDs → 存入 `knowledge_items.attack_techniques`
- [ ] 正则提取合规关键词 → 存入 `knowledge_items.compliance_refs`
- [ ] 提取失败不影响条目入库
- [ ] enrichment 在独立 job 中执行，不阻塞采集主路径

#### FR-SG-06：安全知识图谱 API

**需求描述**：系统提供安全知识图谱查询 API。

**验收标准**：
- [ ] `GET /api/security/graph?view=attack` 返回 ATT&CK 子图
- [ ] `GET /api/security/graph?view=cve` 返回 CVE 子图
- [ ] `GET /api/security/graph?view=compliance` 返回合规子图
- [ ] `GET /api/security/graph?view=full` 返回完整安全图谱
- [ ] `GET /api/security/entities/{id}` 返回单个实体详情
- [ ] `GET /api/security/entities/{id}/related` 返回关联节点（指定深度）
- [ ] `GET /api/security/search?q=xxx` 支持实体搜索

#### FR-SG-07：安全知识图谱前端

**需求描述**：前端提供安全知识图谱可视化。

**验收标准**：
- [ ] KnowledgePage 内嵌 view 切换器（[概念图谱] [ATT&CK] [CVE] [合规矩阵]）
- [ ] ATT&CK 视图：战术/技术分层展示，支持缩放/拖拽
- [ ] CVE 视图：按 severity 着色，支持时间筛选
- [ ] 合规矩阵视图：条目 ↔ 合规条款映射表格
- [ ] 安全实体详情面板（点击节点展示）
- [ ] 响应式布局，暗色主题

#### FR-SG-08：安全术语标准化

**需求描述**：系统提供安全术语标准化服务。

**验收标准**：
- [ ] `POST /api/security/terminology/normalize` 标准化自由文本
- [ ] 支持精确匹配（canonical / synonym）
- [ ] 支持正则提取（CVE ID / ATT&CK ID）
- [ ] 支持模糊匹配（中文同义词）
- [ ] `GET /api/security/terminology/search` 搜索术语
- [ ] `GET /api/security/terminology/taxonomy` 获取术语层级
- [ ] 前端 TermStandardizer 组件：输入框实时标准化建议

#### FR-SG-09：术语与分类集成

**需求描述**：安全术语标准化与现有自动分类系统集成。

**验收标准**：
- [ ] `auto_classifier.py` 新增 `batch_classify_with_terminology()` wrapper
- [ ] 分类前自动将自由标签标准化为 canonical
- [ ] 不破坏原有 `classify_item()` 纯函数 signature
- [ ] 可选调用：不传 `term_svc` 时降级到原有纯规则

#### FR-SG-10：跨端同步

**需求描述**：安全术语数据纳入跨端同步。

**验收标准**：
- [ ] `security_terms` 纳入 sync_bundle
- [ ] `security_entities` / `security_edges` 不纳入 sync_bundle
- [ ] 跨端同步后术语数据一致

---

## 3. 非功能需求

### 3.1 性能

| 指标 | 目标 | 测量方式 |
|---|---|---|
| 安全图谱构建（view=attack） | < 100ms | API 响应时间 |
| 术语标准化（精确匹配） | < 1ms | 单次调用延迟 |
| 术语标准化（模糊匹配） | < 10ms | 单次调用延迟 |
| enrichment 单条 | < 50ms | 正则 + 本地缓存查询 |
| MITRE 全量同步 | < 5 分钟 | 首次同步耗时 |
| NVD 按需查询 | < 2s（含网络） | 外部 API 调用 |

### 3.2 可靠性

| 指标 | 目标 |
|---|---|
| 采集主路径可用性 | 100%（外部 API 故障不影响） |
| 数据持久化 | 100%（SQLite WAL，进程崩溃不丢） |
| MITRE 同步失败重试 | 3 次指数退避 |
| NVD 查询失败降级 | 使用本地缓存，不抛异常 |

### 3.3 兼容性

| 兼容项 | 说明 |
|---|---|
| 现有采集主路径 | 零破坏，仅增加本地 enrichment |
| 现有知识图谱 | 不动，独立安全图谱路径 |
| 现有 auto_classifier | 不动，新增 wrapper |
| sync_bundle | 扩展（security_terms 纳入），不破坏现有 bundle 格式 |
| 前端路由 | 不新增路由，复用 KnowledgePage |

---

## 4. 用户界面设计

### 4.1 KnowledgePage 视图切换

```
┌──────────────────────────────────────────────────────────────────┐
│  KnowledgePage                                                    │
│                                                                  │
│  [概念图谱] [ATT&CK] [CVE] [合规矩阵] [时间线]                    │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                                                          │   │
│  │             当前选中视图的内容区域                         │   │
│  │                                                          │   │
│  │  • 概念图谱：现有 KnowledgeGraph（concept 共现）           │   │
│  │  • ATT&CK：战术/技术分层图谱 + 知识条目关联               │   │
│  │  • CVE：漏洞列表 + severity 着色 + 时间线                 │   │
│  │  • 合规矩阵：条目 ↔ 合规条款映射表格                      │   │
│  │  • 时间线：CVE 发布时间 + 热点关联                        │   │
│  │                                                          │   │
│  └──────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────┘
```

### 4.2 SecurityGraph 节点样式

| 实体类型 | 形状 | 颜色 | 大小 |
|---|---|---|---|
| tactic | 六边形 | #e85d5d（红） | 按子技术数量缩放 |
| technique | 矩形 | #f0c929（黄） | 按关联条目数缩放 |
| cve | 圆形 | #e8891a（橙） | 按 CVSS 分数着色 |
| cwe | 菱形 | #8b5cf6（紫） | 固定 |
| compliance | 圆角矩形 | #00bcd4（青） | 固定 |
| product | 小圆形 | #7c6aff（靛蓝） | 固定 |
| knowledge item | 虚线边框 | #888899（灰） | 固定 |

### 4.3 SecurityEntityDetail 面板

```
┌──────────────────────────────────────────────────────────────┐
│  CVE-2024-38077                              [关闭]          │
│  ─────────────────────────────────────────────────────────── │
│  名称：Windows Win32k 权限提升漏洞                           │
│  CVSS：7.8 (High)                                            │
│  发布日期：2024-07-09                                         │
│  受影响产品：Windows 11 / Windows Server 2016-2022           │
│                                                              │
│  ATT&CK 技术：                                               │
│  • T1059 - Command and Scripting Interpreter                │
│  • T1068 - Exploitation for Privilege Escalation            │
│                                                              │
│  关联知识条目：                                               │
│  • [知识卡片] Windows 内核漏洞分析                            │
│  • [知识卡片] 2024年7月安全月报                               │
│                                                              │
│  合规要求：                                                   │
│  • 等保2.0-三级（安全区域边界）                               │
│                                                              │
│  [NVD 链接] [MITRE 链接]                                     │
└──────────────────────────────────────────────────────────────┘
```

---

## 5. 数据字典

### 5.1 security_entities

| 字段 | 类型 | 说明 | 示例 |
|---|---|---|---|
| id | TEXT PK | 实体唯一标识 | CVE-2024-38077 |
| entity_type | TEXT | 实体类型 | cve / tactic / technique / cwe / compliance / product / cpe |
| name | TEXT | 实体名称 | Windows Win32k 权限提升漏洞 |
| description | TEXT | 简要描述 | 简要描述文本 |
| external_ref | TEXT | 外部引用 URL | https://nvd.nist.gov/vuln/detail/CVE-2024-38077 |
| metadata | TEXT (JSON) | 扩展元数据 | {"cvss": 7.8, "severity": "High", "products": ["Windows 11"]} |
| created_at | TEXT | 创建时间（ISO 8601） | 2026-07-20T10:00:00+00:00 |
| updated_at | TEXT | 更新时间（ISO 8601） | 2026-07-20T10:00:00+00:00 |

### 5.2 security_edges

| 字段 | 类型 | 说明 | 示例 |
|---|---|---|---|
| id | INTEGER PK | 自增主键 | 1 |
| source_id | TEXT | 源实体 ID | T1059 |
| target_id | TEXT | 目标实体 ID | CVE-2024-38077 |
| edge_type | TEXT | 边类型 | uses / causes / mitigates |
| weight | REAL | 权重/置信度 | 1.0 |
| metadata | TEXT (JSON) | 扩展元数据 | {"source": "mitre", "confidence": 1.0} |
| created_at | TEXT | 创建时间 | 2026-07-20T10:00:00+00:00 |

### 5.3 security_terms

| 字段 | 类型 | 说明 | 示例 |
|---|---|---|---|
| id | INTEGER PK | 自增主键 | 1 |
| canonical | TEXT UNIQUE | 规范形式 | 等保2.0-三级 |
| term_type | TEXT | 术语类型 | compliance / cve / attack_technique / generic |
| category | TEXT | 分类 | security / compliance / vulnerability |
| definition | TEXT | 定义 | 网络安全等级保护2.0 第三级要求 |
| external_id | TEXT | 外部 ID | 等保2.0-三级 |
| external_ref | TEXT | 外部引用 URL | https://www.mos.gov.cn/... |
| metadata | TEXT (JSON) | 扩展元数据 | {} |
| created_at | TEXT | 创建时间 | 2026-07-20T10:00:00+00:00 |
| updated_at | TEXT | 更新时间 | 2026-07-20T10:00:00+00:00 |

### 5.4 security_synonyms

| 字段 | 类型 | 说明 | 示例 |
|---|---|---|---|
| id | INTEGER PK | 自增主键 | 1 |
| term_id | INTEGER FK | 关联 security_terms.id | 1 |
| synonym | TEXT | 同义词 | 等保三级 |
| locale | TEXT | 语言标签 | zh-CN |
| created_at | TEXT | 创建时间 | 2026-07-20T10:00:00+00:00 |

### 5.5 security_taxonomy

| 字段 | 类型 | 说明 | 示例 |
|---|---|---|---|
| id | INTEGER PK | 自增主键 | 1 |
| parent_id | INTEGER FK | 父术语 ID（NULL = root） | NULL |
| term_id | INTEGER FK | 关联 security_terms.id | 2 |
| sort_order | INTEGER | 排序 | 0 |
| created_at | TEXT | 创建时间 | 2026-07-20T10:00:00+00:00 |

---

## 6. API 设计

### 6.1 安全图谱 API

| 方法 | 路径 | 说明 | 响应 |
|---|---|---|---|
| GET | `/api/security/graph` | 获取安全图谱 | `SecurityGraphResponse` |
| GET | `/api/security/entities/{id}` | 获取单个实体详情 | `SecurityEntity` |
| GET | `/api/security/entities/{id}/related` | 获取关联节点 | `{nodes, edges, depth}` |
| GET | `/api/security/search` | 搜索安全实体 | `list<SecurityEntity>` |
| GET | `/api/security/cve/{cve_id}` | 获取 CVE 详情 | `SecurityEntity` |
| GET | `/api/security/attack/{technique_id}` | 获取 ATT&CK 技术详情 | `SecurityEntity` |

### 6.2 术语标准化 API

| 方法 | 路径 | 说明 | 响应 |
|---|---|---|---|
| POST | `/api/security/terminology/normalize` | 标准化术语 | `{canonical, term_type, match_type, confidence}` |
| GET | `/api/security/terminology/search` | 搜索术语 | `list<SecurityTerm>` |
| GET | `/api/security/terminology/taxonomy` | 获取术语层级 | `list<SecurityTaxonomyNode>` |
| GET | `/api/security/terminology/synonyms/{canonical}` | 获取同义词 | `list<string>` |

### 6.3 管理 API（可选）

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/security/terminology/terms` | 新增术语（管理员） |
| POST | `/api/security/terminology/terms/{id}/synonyms` | 新增同义词 |
| POST | `/api/security/mitre/sync` | 手动触发 MITRE 同步 |
| POST | `/api/security/nvd/refresh` | 手动刷新 NVD 缓存 |

---

## 7. 与现有系统的集成

### 7.1 采集主路径

```
CollectionService.run_once()
  → 7 collectors → upsert_many
  → 本地 enrichment（正则提取 CVE/ATT&CK ID，查本地缓存）
    → 写入 knowledge_items.cve_ids / attack_techniques / compliance_refs
  → trend rebuild
  → cache invalidate
```

**关键约束**：本地 enrichment 仅正则 + 本地缓存查询，**不调用外部 API**。

### 7.2 异步 enrichment job

```
security_enrichment_job (Interval 300s)
  → 扫描近 24h 未 enrichment 的 hotspot items
  → 对每条 item：
    → 正则提取 CVE IDs
    → 查本地 security_entities（未命中则 NVD 按需查询）
    → 更新 knowledge_items
```

### 7.3 自动分类集成

```python
# backend/services/auto_classifier.py（新增 wrapper）
def batch_classify_with_terminology(items, term_svc=None):
    if term_svc is None:
        return batch_classify(items)  # 降级
    for item in items:
        item["tags"] = _normalize_tags(item.get("tags", []), term_svc)
    return batch_classify(items)
```

### 7.4 同步包集成

```python
# backend/services/sync_bundle.py
SECURITY_TERMS_TABLES = ["security_terms", "security_synonyms", "security_taxonomy"]

def build_bundle():
    # 现有 tables
    tables = ["favorites", "todos", "skills", "custom_sources", "settings", "secrets"]
    # 新增
    tables.extend(SECURITY_TERMS_TABLES)
    ...
```

---

## 8. 里程碑

### Milestone 1：基础设施（预计 1-2 周）

| 任务 | 产出 | 验收标准 |
|---|---|---|
| 022_security_graph.sql 迁移 | 5 张新表 + 2 张表扩展 | 迁移执行成功，schema_version 更新 |
| SecurityRepository | CRUD + 搜索 | 单测覆盖 |
| SecurityEntity / SecurityEdge dataclass | 领域模型 | 与 Repository 对齐 |
| 内置术语种子数据 | 等保/关基/数安法/常见 CVE/ATT&CK 格式 | 可导入数据库 |

### Milestone 2：MITRE ATT&CK 同步（预计 1 周）

| 任务 | 产出 | 验收标准 |
|---|---|---|
| MitreAttackClient | STIX 下载 + 解析 | 首次全量同步 < 5 分钟 |
| mitre_sync_job | scheduler job | 每周日 04:00 自动执行 |
| /api/security/entities 基础查询 | GET 列表/详情 | 可查询 tactic/technique |

### Milestone 3：安全图谱核心（预计 2 周）

| 任务 | 产出 | 验收标准 |
|---|---|---|
| SecurityGraphEngine | build_graph / enrich_item | 返回 {nodes, edges} |
| SecurityGraphService | 业务编排 | get_graph(view) |
| /api/security/graph | FastAPI router | 支持 view=attack/cve/compliance/full |
| security_enrichment_job | scheduler job | 每 300s 异步 enrichment |
| KnowledgeGraph.tsx view 扩展 | 前端组件 | 4 个视图可切换 |

### Milestone 4：术语标准化（预计 1 周）

| 任务 | 产出 | 验收标准 |
|---|---|---|
| TerminologyService | normalize / search / taxonomy | 精确/正则/模糊匹配 |
| /api/security/terminology/* | FastAPI router | 4 个端点 |
| auto_classifier wrapper | batch_classify_with_terminology | 可选调用 |
| TermStandardizer 组件 | 前端组件 | 实时标准化建议 |

### Milestone 5：CVE 时间线 + 合规矩阵（预计 1 周）

| 任务 | 产出 | 验收标准 |
|---|---|---|
| SecurityTimeline.tsx | CVE 时间线组件 | 按日期展示 CVE + 关联热点 |
| ComplianceMatrix.tsx | 合规矩阵组件 | 条目 ↔ 合规条款映射表格 |
| SecurityEntityDetail.tsx | 详情面板 | 点击节点展示完整信息 |

### Milestone 6：NVD 集成 + 告警（预计 1 周，可选）

| 任务 | 产出 | 验收标准 |
|---|---|---|
| NVDClient | CVE API 2.0 客户端 | 按需查询 + 缓存 |
| NVD 集成到 enrichment | 自动补全 CVSS/severity | 缓存 30 天 |
| CVE 告警触发 | cg_events 写入 | CVSS >= 9.0 时触发 |

---

## 9. 成功指标

| 指标 | 目标 | 测量方式 |
|---|---|---|
| 安全实体覆盖率 | 热点条目中 >= 30% 包含至少一个 CVE/ATT&CK ID | 采集后 enrichment 统计 |
| 术语标准化率 | security 标签中 >= 80% 可标准化为 canonical | TerminologyService 统计 |
| 图谱构建耗时 | view=attack < 100ms | API 响应时间 |
| NVD 缓存命中率 | >= 70%（避免重复查询） | security_entities 查询统计 |
| MITRE 同步成功率 | >= 99%（网络故障时保留旧数据） | scheduler job 日志 |
| 前端图谱渲染帧率 | >= 30 FPS（1000 节点） | 浏览器 DevTools |

---

## 10. 附录

### 10.1 MITRE ATT&CK 数据结构（STIX 摘要）

MITRE ATT&CK STIX bundle 包含：
- `intrusion-set`（威胁行为者，如 APT29）
- `malware`（恶意软件）
- `tool`（工具，如 Mimikatz）
- `attack-pattern`（技术，如 T1059）
- `tactic`（战术，如 TA0002）
- `relationship`（关系，如 threat-actor uses technique）

解析目标：
- `attack-pattern` → `security_entities` (entity_type='technique')
- `tactic` → `security_entities` (entity_type='tactic')
- `relationship` (type='uses') → `security_edges` (edge_type='uses')

### 10.2 NVD CVE API 2.0 响应格式

```json
{
  "vulnerabilities": [
    {
      "cve": {
        "id": "CVE-2024-38077",
        "descriptions": [{"lang": "en", "value": "..."}],
        "metrics": {
          "cvssMetricV31": [{
            "cvssData": {
              "baseScore": 7.8,
              "baseSeverity": "HIGH"
            }
          }]
        },
        "configurations": [{
          "nodes": [{
            "cpeMatch": [{
              "criteria": "cpe:2.3:o:microsoft:windows_11:*:*:*:*:*:*:*:*"
            }]
          }]
        }]
      }
    }
  ]
}
```

标准化映射：
- `id` → `security_entities.id`
- `descriptions[0].value` → `description`
- `metrics.cvssMetricV31[0].cvssData.baseScore` → `metadata.cvss`
- `metrics.cvssMetricV31[0].cvssData.baseSeverity` → `metadata.severity`
- `configurations[0].nodes[0].cpeMatch[*].criteria` → `metadata.products`（解析 CPE）
