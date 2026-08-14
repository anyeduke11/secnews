"""URL 批量校验服务 — Phase 2.2 (Crawler v2) 全量 URL 校验。

从 hotspots 中获取未校验的条目，执行 HEAD/GET 请求验证，
结果写入 crawl_url_checks 表并更新 hotspots.url_check_status。
"""
from __future__ import annotations

import asyncio

from backend.logging_config import logger
from backend.repository.crawl_url_check_repo import CrawlUrlCheckRepo

# 并发控制
_MAX_CONCURRENT = 5
_TIMEOUT_SECONDS = 5
_MAX_RETRIES = 2
_UA = "hotspot-url-check/2.0"


def _head_status(url: str, timeout: int) -> int:
    """同步 HEAD 请求，返回 HTTP status。"""
    import urllib.request
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": _UA})
    resp = urllib.request.urlopen(req, timeout=timeout)
    return resp.status


def _get_status(url: str, timeout: int) -> int:
    """同步 GET 请求，返回 HTTP status。"""
    import urllib.request
    req = urllib.request.Request(url, method="GET", headers={"User-Agent": _UA})
    resp = urllib.request.urlopen(req, timeout=timeout)
    return resp.status


def _check_url(url: str) -> int:
    """检查单个 URL 可达性，返回 HTTP status。

    Priority: HEAD → GET → fallback
    """
    import urllib.error
    try:
        try:
            return _head_status(url, _TIMEOUT_SECONDS)
        except urllib.error.HTTPError as e:
            if e.code in (405, 501):
                return _get_status(url, _TIMEOUT_SECONDS)
            return e.code
    except urllib.error.URLError:
        return 0  # 连接失败
    except Exception:
        return -1  # 未知错误


def _check_url_with_retry(url: str, max_retries: int = _MAX_RETRIES) -> int:
    """带重试的 URL 检查。

    Args:
        url: 被检查的 URL
        max_retries: 最大重试次数（默认 2）

    Returns:
        HTTP status code，失败返回 0 或 -1
    """
    import time
    for attempt in range(max_retries + 1):
        status = _check_url(url)
        if status >= 200:
            return status
        if attempt < max_retries:
            # 指数退避：1s, 2s
            wait = 2 ** attempt
            time.sleep(wait)
    return status


class UrlBatchCheckService:
    """URL 批量校验服务。"""

    def __init__(self, max_concurrent: int = _MAX_CONCURRENT):
        self.max_concurrent = max_concurrent
        self.repo = CrawlUrlCheckRepo()

    async def run_check(self, since_minutes: int = 1440, limit: int = 200) -> dict:
        """执行一次批量校验。

        Args:
            since_minutes: 查询最近多少分钟内的条目（默认 1440 = 24h）
            limit: 最大校验条数

        Returns:
            dict 含 checked, succeeded, failed
        """
        unchecked = self.repo.get_unchecked(since_minutes=since_minutes, limit=limit)
        if not unchecked:
            return {"checked": 0, "succeeded": 0, "failed": 0}

        results: list[tuple[str, str, int]] = []  # (item_id, url, status)

        # 限并发
        sem = asyncio.Semaphore(self.max_concurrent)

        async def _check_one(item: dict) -> None:
            item_id = str(item["id"])
            url = str(item["url"])
            async with sem:
                status = await asyncio.to_thread(_check_url_with_retry, url)
                results.append((item_id, url, status))

        tasks = [_check_one(it) for it in unchecked]
        await asyncio.gather(*tasks, return_exceptions=True)

        # 写入结果
        succeeded = 0
        failed = 0
        for item_id, url, status in results:
            self.repo.insert(item_id=item_id, url=url, status_code=status)
            if 200 <= status < 400:
                self.repo.update_status(item_id=item_id, status_code=status)
                succeeded += 1
            else:
                failed += 1

        logger.info(
            f"url_batch_check: checked={len(results)} "
            f"succeeded={succeeded} failed={failed}"
        )
        return {"checked": len(results), "succeeded": succeeded, "failed": failed}


__all__ = ["UrlBatchCheckService"]