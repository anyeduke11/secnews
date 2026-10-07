"""MCP tool → FastAPI operation_id 映射清单 (v0.8.7 P3-B 自 mcp_config 拆出, 行数纪律)。

fastapi-mcp ``include_operations`` 按 OpenAPI operation_id 匹配; 路由函数改名
或路径迁移后对应 id 失效 → 工具被**静默丢弃** (无告警)。
防漂移: ``test_mcp_server.test_operation_ids_resolve_in_openapi`` 对真实 app
OpenAPI 全量解析断言 (fail-loud)。

推导规律: ``{fn}_{path 斜杠转下划线}_{method}``; path 参数段 (如
``{session_id}``) 转为 ``_session_id_``。工具名 ≠ handler 函数名
(如 search_knowledge → list_items), 故清单显式维护、不程序化推导。
"""
from __future__ import annotations

MCP_TOOL_OPERATION_IDS = [
    # 读 (5)
    "list_hotspots_api_hotspots_get",                              # search_hotspots
    "get_hotspot_api_hotspots__item_id__get",                      # get_hotspot
    "list_favorites_api_favorites_get",                            # list_favorites
    "list_items_api_knowledge_items_get",                          # search_knowledge
    "get_personal_profile_api_profile_get",                        # get_personal_profile (mcp_adapters.py)
    # 写 (4)
    "add_favorite_by_hotspot_api_favorites_by_hotspot_post",       # add_favorite (MCP 入口, 内部查 hotspot + 写 created_via='mcp')
    "remove_favorite_api_favorites__hotspot_id__delete",           # remove_favorite
    "create_annotation_endpoint_api_annotations_post",             # add_annotation
    "update_item_api_knowledge_items__item_id__patch",            # update_knowledge_item
    # v0.5 §18.4: wiki_* 工具族 (llm-wiki-2.0 消费面)
    "wiki_search_api_wiki_search_post",                            # wiki_search
    "wiki_read_api_wiki_read_get",                                 # wiki_read
    "wiki_graph_api_wiki_graph_get",                               # wiki_graph
    "db_trace_api_wiki_trace_post",                                # db_trace
    # v0.5 §18.2 强约束 1: agent 持久产物唯一写路径
    "wiki_write_api_wiki_write_post",                              # wiki_write
    # v0.6 Phase 5 commit 3: 5 个 MCP tool 扩展 (KL 推进 + DSH 分析)
    "kl_enqueue_api_mcp_kl_enqueue_post",                          # kl_enqueue
    "kl_status_api_mcp_kl_status_get",                             # kl_status
    "kl_retry_api_mcp_kl_retry_post",                              # kl_retry
    "dsh_analyze_api_mcp_dsh_analyze_post",                        # dsh_analyze
    "dsh_session_api_mcp_dsh_session__session_id__get",            # dsh_session
    # v0.8.7 P3-B: v1 执行域只读导出 (4)
    "list_proposals_api_proposals_get",                            # list_proposals
    "list_runs_api_v1_runs_get",                                   # list_runs
    "list_artifacts_api_v1_artifacts_get",                         # list_artifacts
    "list_cases_endpoint_api_v1_cases_get",                        # list_cases
]

__all__ = ["MCP_TOOL_OPERATION_IDS"]
