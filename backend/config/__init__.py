"""集中配置中心（Pydantic Settings）

- 单例 config 直接 import 使用
- 环境变量前缀：HOTSPOT_*
- 默认读取项目根目录下的 .env

Note: This file was merged from ``backend/config.py`` to resolve a
conflict between the ``backend/config`` module and the
``backend/config/`` package (Phase 16 Hybrid AI).
"""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="HOTSPOT_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Server
    # 默认仅监听回环地址：全 API 无认证，绑 0.0.0.0 会把写接口暴露给整个局域网。
    # 确需局域网访问时显式设置 HOTSPOT_HOST=0.0.0.0。
    host: str = "127.0.0.1"
    port: int = 8000

    # Paths
    log_dir: Path = BASE_DIR / "logs"
    db_path: Path = BASE_DIR / "hotspot.db"
    backup_dir: Path = BASE_DIR / "backups"
    # v0.5 M2-T6: 分类型存储 (HOT/WARM/COLD/FROZEN)
    # 默认与 hotspot.db 同目录, 启动期 ATTACH
    warm_db_path: Path = BASE_DIR / "hotspot-warm.db"
    cold_db_path: Path = BASE_DIR / "hotspot-cold.db"
    # COLD 加密 master key (env HOTSPOT_COLD_DB_KEY); 留空 = 不加密 (dev)
    cold_db_key: str = ""

    # Cache
    cache_ttl_seconds: int = 300
    cache_maxsize: int = 64

    # Collection
    collect_interval_seconds: int = 300
    # v0.4.0 注: collect_timeout_seconds / collect_single_source_timeout 为预留 —
    # 抓取超时目前在 fetchers.py 内按路径各自设置, 待统一 BackendSession 接线后启用
    collect_timeout_seconds: int = 60
    collect_single_source_timeout: int = 30
    # v1.8: 启动时自动追抓「本周一 → 现在」(真实全网抓取);
    # 测试环境必须关闭 (conftest autouse fixture), env HOTSPOT_CATCHUP_ON_STARTUP 可覆盖
    catchup_on_startup: bool = True

    # Logging
    log_level: str = "INFO"
    log_max_bytes: int = 50 * 1024 * 1024  # 50MB
    log_backup_count: int = 5

    # Proxy
    proxy_mode: str = "off"  # off / auto / manual

    # Quality
    quality_strict_mode: bool = False
    quality_min_score: int = 50
    # v0.4.0 注: quality_url_check_enabled 为预留 — URL 内容校验由 collect_all
    # 尾部 post-ingest 链统一执行 (独立调度已收敛); interval 同样由链内节奏决定
    quality_url_check_enabled: bool = True
    quality_url_check_timeout: int = 8
    quality_url_check_interval_seconds: int = 300
    # v0.4.0: 接线到 source_reputation_rebuild 调度间隔
    quality_reputation_interval_seconds: int = 21600

    # v1.4 Knowledge
    local_wiki_enabled: bool = False
    local_wiki_path: str = ""
    local_wiki_readonly: bool = True
    # v1.4 Phase 1c Group N: Obsidian watchdog (knowledge/ .md file watcher)
    knowledge_watchdog_enabled: bool = True

    # v1.7 Phase 6 Task 6.2: Feature Flags
    # 控制 v1.7 新功能的启用状态; 默认开启已稳定功能, 未稳定功能默认关闭
    feature_tag: bool = True              # 标签系统 (Phase 1)
    feature_auto_extract: bool = True      # 三层自动提取 (Phase 1)
    feature_annotation: bool = True      # 笔记/标注 (Phase 2)
    feature_unified_search: bool = True   # 统一跨层搜索 (Phase 3)
    feature_tech_stack: bool = True       # 技术栈管理 (Phase 2)
    # 待观察功能 (默认关闭, 验证后再开启)
    # P0-3 (2026-08-15): 以下三个 flag 对应的前端 UI 均已可达 (ReviewMode/
    # AlertMode/RecommendationSidebar), flag=False 时路由不注册 → 前端 404。
    # 后端实现完备 (数据流断裂问题由 Phase 3 修复), 因此改为默认开启,
    # 消除"页面可达但 API 404"的脱钩。
    feature_review: bool = True           # SM-2 间隔复习 (Phase 2)
    feature_alert: bool = True            # 告警规则 + SSE (Phase 3)
    feature_recommendation: bool = True   # 个性化推荐 (Phase 4)
    feature_personalization: bool = False # 个人画像 EMA (Phase 4)
    feature_source_health: bool = True    # 数据源健康指示 (Phase 4)
    feature_digest: bool = True          # 每日简报 (Phase 4)
    # v1.8: feature_kv_cache 已删除 (kv_cache_service 于 Phase 7 移除)
    # v1.7 Phase 7 Option A: MCP server 替代 Phase 5 内部 hotspot-agent
    feature_mcp: bool = True       # MCP Server (Phase 7, 替代 feature_agent)
    feature_workbench_ui: bool = True  # Phase 4 工作台 UI (v0.6.1, 5 视图统一壳)

    # v0.5 M3.5: llm-wiki-2.0 知识真源（md 文件优先, SQLite 退化为索引）
    # 默认开启；env HOTSPOT_LLM_WIKI_V2=false 退回 v0.4 knowledge/ 路径
    # 关闭后 wiki_archiver / retention_engine job 跳过调度，ai_hub 仍可写
    # （但写入目标改为 knowledge/，与 v0.4 行为一致）
    llm_wiki_v2: bool = True
    # repo root (BASE_DIR = backend/, llm-wiki-2.0/ 在 repo 根目录与 knowledge/ 平级)
    llm_wiki_v2_path: Path = BASE_DIR.parent / "llm-wiki-2.0"


# 全局单例
config = Settings()


__all__ = ["BASE_DIR", "Settings", "config"]