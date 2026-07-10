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
    quality_min_score: int = 30
    quality_url_check_enabled: bool = True
    quality_url_check_sample_rate: float = 0.1
    quality_url_check_timeout: int = 8
    quality_url_check_interval_seconds: int = 300
    quality_reputation_interval_seconds: int = 21600


# 全局单例
config = Settings()


__all__ = ["Settings", "config", "BASE_DIR"]
