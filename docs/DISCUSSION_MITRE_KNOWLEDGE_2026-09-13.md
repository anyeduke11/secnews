# mitre ATT&CK 数据的知识梳理应用场景（讨论稿）

- 日期：2026-09-13
- 状态：**讨论稿** — owner 裁决 (决策 6)："用来做知识梳理，但需要设计好具体的应用场景，可以先讨论"。本文列出候选场景供挑选，**未经确认不动代码**
- 现状：`backend/data/mitre/enterprise-attack.json`（46MB，ATT&CK Enterprise 全量，含 tactics/techniques/groups/mitigations/software + 关系）已就位；`security/mitre_attack.py` 有加载器（env 可覆盖缓存路径），`POST /api/cve/attack-data/load` 手动入口存在但**零数据落库**（attack_techniques 0 / attack_cwe_map 0 / security_edges 0 / tactic 仅 1 行测试数据——第一性原理 D18"图谱是死种子"）

---

## 场景清单（按"价值 ÷ 成本"排序）

### M1 图谱点火：ATT&CK 数据落库 + 安全图谱有边 ⭐ 推荐首发

- **做什么**：跑通 `load_attack_data()` 把 techniques/tactics 落 `attack_techniques`；补 `security_edges` 的写入路径（technique↔tactic 隶属、technique↔mitigation、CVE↔technique 经 CWE 映射表），让 `security/graph.py` 的图真正有边
- **解决什么**：D18 的三个"永远空"视图（/knowledge/process、/secnews/analytics 的 ATT&CK/合规视图、compliance 恒"暂无数据"）直接复活；`_load_compliance_edges()` 硬编码空列表一并接通
- **成本**：低（加载器+表都在，主要是把断掉的调用链接上 + `iter_builtin()` 合规种子落库）；1~2 天
- **结果**：图谱页/分析页首次显示真实 ATT&CK 结构；后续所有场景的地基

### M2 资讯/CVE 的战术标注（TTP 打标）⭐ 与兴趣引擎同构

- **做什么**：对 hotspots/知识条目做 ATT&CK 技术提及识别（规则先行：technique 名称/别名/编号 Txxxx 匹配 + 安全域过滤），打 `attack_technique` 标签；CVE 条目经 attack_cwe_map 间接获得战术标签
- **解决什么**：Subject 360 视图能回答"这个 CVE/厂商关联哪些战术"；资讯流的战术维度筛选；兴趣引擎的 practice 域权重可消费
- **成本**：中（匹配规则 + 打标管线 + 前端徽标）；2~3 天
- **注意**：误标控制——只在安全域条目上跑（复用 info_filter/兴趣域的域判定），ai/tech 域不打标

### M3 判断辅助：Case/Judgment 的战术知识卡 ⭐ 与三层壳语义对齐

- **做什么**：CaseDetail/Judgment 上下文装配时，若 subject/CVE 关联了战术，自动附"战术知识卡"（technique 描述、检测建议、常见缓解）；从 ATT&CK 数据生成 technique 知识条目进 wiki（wiki-first 存储）
- **解决什么**：判断时不用离开看板查 MITRE 官网；知识库获得结构化战术条目（约 600+ Enterprise techniques，按需生成不一次全量）
- **成本**：中；2~3 天

### M4 合规映射：ATT&CK ↔ 等保 2.0 / GDPR 控制项

- **做什么**：`compliance_event_map` 落真实映射（ATT&CK 官方有 control 映射数据源；等保映射需人工词表或社区数据）；合规矩阵页显示"该控制项关联的战术/事件"
- **解决什么**：合规举证视图从空壳变可用；这是你金融安全客户场景（等保）的直接价值点
- **成本**：中高（等保映射数据需要构造，官方无现成）；3~5 天，建议排 M1 之后看图谱效果再定

### M5 实践域联动（与 CodeGarden 转型合流）

- **做什么**：technique → 开源实践项目推荐（Atomic Red Team 按战术覆盖、Sigma 规则库、开源检测项目）；CodeGarden 候选池的项目打"战术覆盖"标签
- **解决什么**："学了这个战术，有什么工具可以上手练"——知识梳理到动手实践的桥
- **成本**：低（M1 数据就位后是纯映射表 + 查询）；1 天
- **依赖**：M1 + CodeGarden CP-1（候选池）

### M6 全量战术知识库生成（不建议现在做）

- 600+ technique 全部生成 wiki 条目：内容质量不可控、存储膨胀、违背"判断价值随时间递增"的按需原则。**建议保持按需生成（M3 路径）**。

## 推荐组合与排期

| 批 | 内容 | 理由 |
|---|---|---|
| 第一批 | **M1**（图谱点火） | 所有场景的地基；成本最低；直接复活三个死视图 |
| 第二批 | **M2 + M5**（战术打标 + 实践联动） | 复用兴趣引擎管线；打通"资讯→战术→实践"主线 |
| 第三批 | M3（知识卡）→ M4（合规映射） | 看前两批效果后定深度 |

## 需 owner 确认的开放问题

1. **数据新鲜度**：ATT&CK 数据是静态缓存（当前 2026-09 下载）——需要定期更新吗（ATT&CK 半年一版）？推荐手动 `POST /api/cve/attack-data/load` 时重新下载即可，不做定时。
2. **打标范围**（M2）：只标 security 域，还是 ai_security 也标？推荐 security + ai_security。
3. **等保映射**（M4）：你的客户场景是否需要等保 2.0 专项映射？若是，映射词表由你提供初版还是我构造草稿你审？
4. **知识条目归属**（M3）：technique 条目进现有 wiki 根还是 v1_knowledge？推荐 v1_knowledge（带 evidence 与 review_at，符合证据引擎纪律）。
