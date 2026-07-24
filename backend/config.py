"""集中配置中心（Pydantic Settings）

- 单例 config 直接 import 使用
- 环境变量前缀：HOTSPOT_*
- 默认读取项目根目录下的 .env
"""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="HOTSPOT_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Server
    host: str = "0.0.0.0"
    port: int = 8000

    # Paths
    log_dir: Path = BASE_DIR / "logs"
    db_path: Path = BASE_DIR / "hotspot.db"
    backup_dir: Path = BASE_DIR / "backups"

    # Cache
    cache_ttl_seconds: int = 300
    cache_maxsize: int = 64

    # Collection
    collect_interval_seconds: int = 300
    collect_timeout_seconds: int = 60
    collect_single_source_timeout: int = 30

    # Logging
    log_level: str = "INFO"
    log_max_bytes: int = 50 * 1024 * 1024  # 50MB
    log_backup_count: int = 5

    # Proxy
    proxy_mode: str = "off"  # off / auto / manual

    # Quality
    quality_strict_mode: bool = False
    quality_min_score: int = 50
    quality_url_check_enabled: bool = True
    quality_url_check_sample_rate: float = 0.1
    quality_url_check_timeout: int = 8
    quality_url_check_interval_seconds: int = 300
    quality_reputation_interval_seconds: int = 21600

    # v1.4 Knowledge
    local_wiki_enabled: bool = False
    local_wiki_path: str = ""
    local_wiki_readonly: bool = True
    # v1.4 Phase 1c Group N: Obsidian watchdog (knowledge/ .md file watcher)
    knowledge_watchdog_enabled: bool = True

    # v1.7 Phase 6 Task 6.2: Feature Flags
    # 控制 v1.7 新功能的启用状态; 默认开启已稳定功能, 未稳定功能默认关闭
    feature_tags: bool = True              # 标签系统 (Phase 1)
    feature_auto_extract: bool = True      # 三层自动提取 (Phase 1)
    feature_annotations: bool = True      # 笔记/标注 (Phase 2)
    feature_unified_search: bool = True   # 统一跨层搜索 (Phase 3)
    feature_tech_stack: bool = True       # 技术栈管理 (Phase 2)
    # 待观察功能 (默认关闭, 验证后再开启)
    feature_reviews: bool = False          # SM-2 间隔复习 (Phase 2)
    feature_alerts: bool = False           # 告警规则 + SSE (Phase 3)
    feature_recommendations: bool = False # 个性化推荐 (Phase 4)
    feature_personalization: bool = False # 个人画像 EMA (Phase 4)
    feature_source_health: bool = True    # 数据源健康指示 (Phase 4)
    feature_digests: bool = True          # 每日简报 (Phase 4)
    feature_agent: bool = False           # Agent 双向环 (Phase 5)
    feature_kv_cache: bool = True         # KV 缓存层 (Phase 5)


# 全局单例
config = Settings()


__all__ = ["Settings", "config", "BASE_DIR"]
