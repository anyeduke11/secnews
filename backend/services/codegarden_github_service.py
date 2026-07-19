"""Phase 2a CodeGarden GitHub REST API 客户端.

职责
----
- fetch_repo_metadata(url): 拉 repo 元信息 (owner/repo/default_branch/upstream)
- compare_commits(repo_url, base, head): 拉 commits behind/ahead
- token 从 secrets_service 获取 (key name: github_token)

设计要点
--------
- 复用 httpx (与 collectors 同栈), 但走 REST API 而非 HTML 抓取
- token 缺失时 raise GithubTokenMissingException, API 层捕获后返回 424
- 速率限制: 403/429 抛 GithubRateLimitException
- 不缓存 (上游同步任务调度间隔 24h)
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse

import httpx

from backend.exceptions import InternalException
from backend.logging_config import logger


GITHUB_API_BASE = "https://api.github.com"
_OWNER_REPO_RE = re.compile(r"^/([^/]+)/([^/]+?)(?:\.git)?/?$")


class GithubTokenMissingException(InternalException):
    """GitHub token 未配置（API 层捕获后返回 424）。"""


class GithubRateLimitException(InternalException):
    """GitHub API 速率限制。"""


@dataclass
class RepoMetadata:
    owner: str
    repo: str
    default_branch: str
    description: Optional[str]
    upstream_url: Optional[str]      # fork source (parent.clone_url)
    upstream_default_branch: Optional[str]
    stars: int
    language: Optional[str]
    homepage: Optional[str]


@dataclass
class CompareResult:
    base: str
    head: str
    commits_behind: int
    commits_ahead: int
    last_commit_messages: list[str]   # 最近 5 条
    last_commit_shas: list[str]


def _parse_owner_repo(repo_url: str) -> tuple[str, str]:
    """从 https://github.com/{owner}/{repo} 解析 owner/repo。"""
    parsed = urlparse(repo_url)
    if parsed.hostname not in ("github.com", "www.github.com"):
        raise InternalException(f"非 GitHub URL: {repo_url}")
    m = _OWNER_REPO_RE.match(parsed.path or "")
    if not m:
        raise InternalException(f"无法解析 owner/repo: {repo_url}")
    return m.group(1), m.group(2)


def _get_github_token() -> str:
    """从 secrets_service 获取 github_token (通过 name 查找 + reveal)."""
    try:
        from backend.services.secrets_service import SecretsService
    except ImportError as e:
        raise GithubTokenMissingException(f"secrets_service 不可用: {e}") from e

    svc = SecretsService()
    items, _ = svc.list_secrets()
    github_secret = next(
        (s for s in items if s.get("name") == "github_token"),
        None,
    )
    if github_secret is None:
        raise GithubTokenMissingException(
            "github_token 未配置; 请在 Secrets 页面添加 name=github_token 的密钥"
        )
    if not github_secret.get("unlocked"):
        raise GithubTokenMissingException(
            "secrets 未解锁; 请先在 Secrets 页面输入主密钥 unlock"
        )
    revealed = svc.reveal(int(github_secret["id"]))
    token = revealed.get("api_key") or ""
    if not token:
        raise GithubTokenMissingException("github_token 解密后为空")
    return token


def _make_headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "hotspot-codegarden/1.0",
    }


def _check_rate_limit(response: httpx.Response) -> None:
    remaining = response.headers.get("X-RateLimit-Remaining")
    if remaining == "0" or response.status_code in (403, 429):
        reset = response.headers.get("X-RateLimit-Reset", "?")
        raise GithubRateLimitException(
            f"GitHub API 速率限制, reset at {reset}; status={response.status_code}"
        )


def fetch_repo_metadata(repo_url: str) -> RepoMetadata:
    """拉 GitHub repo 元信息（含 fork 源）。"""
    owner, repo = _parse_owner_repo(repo_url)
    token = _get_github_token()
    headers = _make_headers(token)

    with httpx.Client(timeout=15.0) as client:
        resp = client.get(f"{GITHUB_API_BASE}/repos/{owner}/{repo}", headers=headers)
        _check_rate_limit(resp)
        if resp.status_code == 404:
            raise InternalException(f"GitHub repo 不存在: {repo_url}")
        if resp.status_code != 200:
            raise InternalException(
                f"GitHub API /repos 失败: status={resp.status_code}, body={resp.text[:200]}"
            )
        data = resp.json()

        upstream_url: Optional[str] = None
        upstream_default_branch: Optional[str] = None
        parent = data.get("parent")
        if parent:
            upstream_url = parent.get("clone_url") or parent.get("html_url")
            # 拉 upstream default branch (额外一次 API 调用)
            if upstream_url:
                try:
                    parent_owner = parent.get("owner", {}).get("login")
                    parent_repo = parent.get("name")
                    if parent_owner and parent_repo:
                        pr = client.get(
                            f"{GITHUB_API_BASE}/repos/{parent_owner}/{parent_repo}",
                            headers=headers,
                        )
                        if pr.status_code == 200:
                            upstream_default_branch = pr.json().get("default_branch")
                except Exception as e:
                    logger.warning(f"fetch upstream default_branch failed: {e}")

        return RepoMetadata(
            owner=owner,
            repo=repo,
            default_branch=data.get("default_branch", "main"),
            description=data.get("description"),
            upstream_url=upstream_url,
            upstream_default_branch=upstream_default_branch,
            stars=int(data.get("stargazers_count", 0) or 0),
            language=data.get("language"),
            homepage=data.get("homepage") or None,
        )


def compare_commits(
    repo_url: str,
    base: str,           # 上游 default branch (e.g. "main")
    head: str,           # 本地 fork branch 或 commit sha
) -> CompareResult:
    """调 GitHub compare 端点拉 commits behind/ahead。"""
    owner, repo = _parse_owner_repo(repo_url)
    token = _get_github_token()
    headers = _make_headers(token)

    with httpx.Client(timeout=15.0) as client:
        resp = client.get(
            f"{GITHUB_API_BASE}/repos/{owner}/{repo}/compare/{base}...{head}",
            headers=headers,
        )
        _check_rate_limit(resp)
        if resp.status_code == 404:
            raise InternalException(
                f"compare 失败 (404): {repo_url} base={base} head={head}"
            )
        if resp.status_code != 200:
            raise InternalException(
                f"compare 失败: status={resp.status_code}, body={resp.text[:200]}"
            )
        data = resp.json()

        commits = data.get("commits", [])[:5]
        return CompareResult(
            base=base,
            head=head,
            commits_behind=int(data.get("behind_by", 0) or 0),
            commits_ahead=int(data.get("ahead_by", 0) or 0),
            last_commit_messages=[c.get("commit", {}).get("message", "").split("\n")[0]
                                   for c in commits],
            last_commit_shas=[c.get("sha", "") for c in commits],
        )


def fetch_upstream_releases(repo_url: str, limit: int = 5) -> list[dict]:
    """拉 upstream 最近 releases（可选功能, 用于显示最新版本）。"""
    owner, repo = _parse_owner_repo(repo_url)
    token = _get_github_token()
    headers = _make_headers(token)

    with httpx.Client(timeout=15.0) as client:
        resp = client.get(
            f"{GITHUB_API_BASE}/repos/{owner}/{repo}/releases?per_page={limit}",
            headers=headers,
        )
        _check_rate_limit(resp)
        if resp.status_code != 200:
            return []
        return [
            {
                "tag": r.get("tag_name"),
                "name": r.get("name") or r.get("tag_name"),
                "published_at": r.get("published_at"),
                "html_url": r.get("html_url"),
                "prerelease": bool(r.get("prerelease")),
            }
            for r in resp.json()
        ]


__all__ = [
    "RepoMetadata",
    "CompareResult",
    "fetch_repo_metadata",
    "compare_commits",
    "fetch_upstream_releases",
    "GithubTokenMissingException",
    "GithubRateLimitException",
]
