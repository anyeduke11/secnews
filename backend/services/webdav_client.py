"""Phase 42 跨端同步: WebDAV 客户端 (httpx async)。

设计要点
--------

- 协议: WebDAV (RFC 4918) — PROPFIND / PUT / GET / HEAD / MKCOL。
- 服务端: 坚果云 (``https://dav.jianguoyun.com/dav/``) 为主, 也兼容其他
  标准 WebDAV 服务 (Nextcloud / ownCloud / 群晖 WebDAV 等)。
- 凭据: HTTP Basic Auth, 使用应用专用密码 (坚果云 / Nextcloud 都有),
  不使用登录密码。``WebDAVClient`` 不持久化任何凭据 — 每次调用显式传入
  ``username / password``。
- 超时: 10s connect, 30s read, 避免慢速网络长时间阻塞 scheduler。
- 失败语义: ``test_connection`` 区分「服务器不可达」/「凭据错误」/「成功」,
  其余方法失败直接抛 ``WebDAVError`` (含 status_code + reason)。

安全原则
--------

- 不在异常消息里回显密码。
- 调试日志只打印 ``url`` 路径部分, 不打印 ``?query`` 或 auth header。
- ``download`` 在服务端 404 时返回 ``None`` (语义: "远端无文件") 而非抛错。
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional
from urllib.parse import quote, urlparse

import httpx

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _body_hint(resp: httpx.Response, max_len: int = 200) -> str:
    """从响应中抽取 body 摘要, 便于错误信息可读。

    - 截断 ``max_len`` 字符, 避免日志/前端爆炸
    - 隐藏 XML 中的 <D:error> 标签, 保留文本内容
    """
    try:
        body = (resp.text or "").strip()
    except Exception:
        return "<binary body>"
    if not body:
        return "<empty body>"
    if len(body) > max_len:
        body = body[:max_len] + f"...(+{len(body) - max_len} chars)"
    return body


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------
class WebDAVError(Exception):
    """WebDAV 操作失败基类。"""

    def __init__(self, message: str, *, status_code: Optional[int] = None,
                 reason: Optional[str] = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.reason = reason


class WebDAVAuthError(WebDAVError):
    """凭据错误 (401/403)。"""


class WebDAVNotFoundError(WebDAVError):
    """资源不存在 (404) — download 返回 None 而不是抛错, 这里用于 mkdir / 其他。"""


# ---------------------------------------------------------------------------
# WebDAV client
# ---------------------------------------------------------------------------
class WebDAVClient:
    """极简 WebDAV 客户端, 仅实现同步所需子集。

    使用方式::

        client = WebDAVClient("https://dav.jianguoyun.com/dav",
                              username="user@example.com",
                              password="app-password")
        ok, msg = await client.test_connection()
        if ok:
            await client.mkdir("/hotspot")
            await client.upload("/hotspot/config.json", payload)
            data = await client.download("/hotspot/config.json")
    """

    def __init__(self, url: str, username: str, password: str,
                 *, timeout_connect: float = 10.0, timeout_read: float = 30.0,
                 user_agent: str = "HotspotSync/1.0") -> None:
        if not url or not username or password is None:
            raise WebDAVError("url / username / password 必填")
        # 去掉末尾 /, 自己控制路径拼接
        self.base_url = url.rstrip("/")
        self.username = username
        self.password = password
        self.auth = httpx.BasicAuth(username, password)
        self.timeout = httpx.Timeout(
            connect=timeout_connect,
            read=timeout_read,
            write=timeout_read,
            pool=timeout_connect,
        )
        self.user_agent = user_agent

    # ---- 内部 helper ----
    def _join(self, path: str) -> str:
        """拼接 base_url + path, 处理重复 / 与路径编码。"""
        if not path.startswith("/"):
            path = "/" + path
        # 路径分段 URL-encode (保留 /)
        encoded = "/".join(quote(seg, safe="") for seg in path.split("/") if seg)
        return f"{self.base_url}/{encoded}"

    def _log_path(self, path: str) -> str:
        """仅打印路径 (不含 query / fragment / auth), 避免泄漏。"""
        parsed = urlparse(self._join(path))
        return parsed.path

    async def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        url = self._join(path)
        async with httpx.AsyncClient(auth=self.auth, timeout=self.timeout,
                                     headers={"User-Agent": self.user_agent}) as client:
            try:
                resp = await client.request(method, url, **kwargs)
            except httpx.ConnectError as e:
                raise WebDAVError(f"无法连接 {self.base_url}: {e}") from e
            except httpx.TimeoutException as e:
                raise WebDAVError(f"请求超时: {e}") from e
            except httpx.HTTPError as e:
                raise WebDAVError(f"HTTP 错误: {e}") from e
            return resp

    # ---- public API ----
    async def test_connection(self) -> tuple[bool, str]:
        """探测连通性 + 凭据。

        返回 ``(ok, message)``。``message`` 人类可读, 用于 UI 展示。
        """
        url = self._join("/")
        logger.info("WebDAV test_connection: %s", self.base_url)
        try:
            async with httpx.AsyncClient(auth=self.auth, timeout=self.timeout,
                                         headers={"User-Agent": self.user_agent}) as client:
                resp = await client.request("PROPFIND", url, headers={
                    "Depth": "0",
                    "Content-Type": "application/xml",
                }, content=b'<?xml version="1.0" encoding="utf-8"?>'
                          b'<d:propfind xmlns:d="DAV:"><d:prop><d:resourcetype/></d:prop></d:propfind>')
        except httpx.ConnectError as e:
            return False, f"无法连接服务器: {e}"
        except httpx.TimeoutException as e:
            return False, f"连接超时: {e}"
        except httpx.HTTPError as e:
            return False, f"网络错误: {e}"

        if resp.status_code in (200, 207):
            return True, "连接成功"
        if resp.status_code in (401, 403):
            return False, "认证失败: 用户名或应用密码错误"
        if resp.status_code == 404:
            return False, "服务器响应 404, 可能是 WebDAV 路径错误"
        return False, f"服务器响应 {resp.status_code}"

    async def exists(self, path: str) -> bool:
        """检查远端文件 / 目录是否存在 (HEAD)。

        返回: True = 存在, False = 不存在。
        抛: 真认证失败 (其他未知错误含 body 摘要)。

        **坚果云 quirk 综合防护** (Phase 49 修复):
        坚果云对目录的 HEAD 行为与文件不同, 见下表:
        - ``HEAD /hotspot`` (存在的目录) → **403 Forbidden** (坚果云 quirk, 不是认证失败)
        - ``HEAD /hotspot/x.txt`` (不存在的文件) → 404
        - ``HEAD /hotspot/x.txt`` (存在的文件) → 200
        - ``PROPFIND /hotspot`` → 207 (正常)

        决策表:
        - 200/207 → 存在
        - 301/405/409/403 → 视为存在 (坚果云 quirk, 目录 HEAD 受限)
        - 404 → 不存在
        - 401 → 真认证失败 (抛 WebDAVAuthError)
        """
        log_path = self._log_path(path)
        logger.debug("WebDAV exists: %s", log_path)
        resp = await self._request("HEAD", path)
        if resp.status_code in (200, 207, 301, 405, 409, 403):
            # 200/207 = exists, 301 = redirect (重定向到存在的资源),
            # 405 = exists but HEAD not allowed, 409 = 坚果云 quirk (exists),
            # 403 = 坚果云 quirk (目录 HEAD 受限), 不当认证失败
            return True
        if resp.status_code == 404:
            return False
        if resp.status_code == 401:
            raise WebDAVAuthError(f"认证失败 (401)", status_code=401)
        raise WebDAVError(
            f"HEAD 失败: {resp.status_code} {resp.reason_phrase}: {_body_hint(resp)}",
            status_code=resp.status_code, reason=resp.reason_phrase,
        )

    async def mkdir(self, path: str) -> bool:
        """创建远端目录 (MKCOL)。若已存在返回 True 不报错。

        返回: True = 创建成功或已存在; False = 失败 (抛错前 swallow 的非关键失败)。

        **坚果云 quirk**: 对已存在的目录 MKCOL 会返回 409 (其他 server 通常
        返回 405)。这里把 409 视为"目录已存在"成功, 避免误报。
        """
        log_path = self._log_path(path)
        logger.info("WebDAV mkdir: %s", log_path)
        resp = await self._request("MKCOL", path)
        if resp.status_code in (201, 200, 405, 301, 409):
            # 201/200 = created, 405 = already exists (RFC 4918),
            # 301 = already a collection, 409 = 坚果云 quirk (已存在)
            return True
        if resp.status_code in (401, 403):
            raise WebDAVAuthError(f"认证失败 ({resp.status_code})",
                                  status_code=resp.status_code)
        raise WebDAVError(
            f"MKCOL 失败: {resp.status_code} {resp.reason_phrase}: {_body_hint(resp)}",
            status_code=resp.status_code, reason=resp.reason_phrase,
        )

    async def ensure_parent_dirs(self, file_path: str, *, force_mkcol: bool = False) -> None:
        """递归确保 ``file_path`` 的所有父目录存在 (MKCOL)。

        例: ``file_path=/hotspot/a/b.json`` → MKCOL /hotspot, MKCOL /hotspot/a
        已存在的目录会被吞掉 (依赖 :meth:`mkdir` 接受 409/405)。

        ``force_mkcol=True`` 时跳过 exists 检查, 强制重做 MKCOL (用于 retry 链路:
        HEAD 409 不可信, 必须重做 MKCOL 才能让父目录真正落库)。

        **坚果云 quirk 二次防护**:
        坚果云 MKCOL 偶发"假成功" — 返 201 Created, 但 server 端异步落库,
        立即 PUT 会撞 AncestorsNotFound。这里 MKCOL 后用 HEAD 探一次父目录,
        若 404 则 sleep 0.3s 再 MKCOL 一次, 最多重试 2 次。
        """
        # 拆分出父目录链
        parts = [seg for seg in file_path.split("/") if seg]
        if len(parts) <= 1:
            # 无父目录 (根目录下的文件), 不需要 MKCOL
            return
        # 累加路径: /a, /a/b, /a/b/c, ...
        for i in range(1, len(parts)):
            sub = "/" + "/".join(parts[:i])
            await self._ensure_one_dir(sub, force_mkcol=force_mkcol)

    async def _ensure_one_dir(self, path: str, *, max_attempts: int = 2,
                              force_mkcol: bool = False) -> None:
        """MKCOL + HEAD 验证单层父目录; 坚果云 quirk 时自动重试。

        ``force_mkcol=True`` 时**完全跳过** exists HEAD 检查, 强制 MKCOL 一次
        后直接返回 (用于 retry 链路: HEAD 409 不可信, 必须重做 MKCOL)。

        正常模式 (force_mkcol=False): 每次循环 exists HEAD 探, 不存在才 MKCOL,
        MKCOL 后再 exists 验证; 仍不存在则 sleep 0.3s 再来一次 (最多 max_attempts)。
        """
        if force_mkcol:
            # 强制 MKCOL, 不查 HEAD (HEAD 409 不可信时只能信任 MKCOL)
            await self.mkdir(path)
            return
        for attempt in range(1, max_attempts + 1):
            # 已存在就直接返回 (HEAD 200/207)
            if await self.exists(path):
                return
            # 不存在 → MKCOL
            await self.mkdir(path)
            # MKCOL 完后用 HEAD 验证 server 真的落库
            if await self.exists(path):
                return
            if attempt < max_attempts:
                logger.warning(
                    "WebDAV MKCOL 后 HEAD 仍 404, sleep + 重试: %s (attempt %d/%d)",
                    path, attempt, max_attempts,
                )
                await asyncio.sleep(0.3)
        # 重试 N 次后仍 404, 抛错
        raise WebDAVError(
            f"无法创建远端目录 (MKCOL + HEAD 验证失败): {path}",
        )

    async def upload(self, path: str, data: bytes,
                     *, content_type: str = "application/octet-stream",
                     ensure_parents: bool = True,
                     retry_on_ancestors_not_found: bool = True,
                     max_attempts: int = 4) -> int:
        """上传数据 (PUT)。返回 HTTP status_code。

        ``ensure_parents=True`` 时先递归 MKCOL 所有父目录 (推荐)。
        关掉后可走手写 mkdir 流程 (兼容旧用法)。

        ``retry_on_ancestors_not_found=True`` 时, 若 PUT 返回 409 且 body 含
        ``AncestorsNotFound`` (坚果云 quirk: MKCOL 异步落库导致 PUT 撞祖先不存在),
        自动指数退避 sleep + 再 ensure_parents(force_mkcol) + 再 PUT。

        ``max_attempts`` (默认 4): 最大尝试次数。坚果云 quirk 严重时可能需要
        3-5 次才能成功, 2 次不够 (Phase 49 改进)。
        """
        if not isinstance(data, (bytes, bytearray)):
            raise WebDAVError("data 必须为 bytes")
        if max_attempts < 1:
            raise WebDAVError("max_attempts 必须 >= 1")

        path_for_log = self._log_path(path)
        last_err: Optional[httpx.Response] = None
        for attempt in range(1, max_attempts + 1):
            # ensure_parents 必须用原始 path 计算父目录链, 不能先 _log_path
            if ensure_parents:
                # retry 时 force_mkcol=True: 强制重做 MKCOL (HEAD 409 不可信)
                await self.ensure_parent_dirs(path, force_mkcol=(attempt > 1))
            logger.info(
                "WebDAV upload: %s (%d bytes, attempt %d/%d)",
                path_for_log, len(data), attempt, max_attempts,
            )
            resp = await self._request(
                "PUT", path,
                content=bytes(data),
                headers={"Content-Type": content_type, "Content-Length": str(len(data))},
            )
            if resp.status_code in (200, 201, 204):
                return resp.status_code
            if resp.status_code in (401, 403):
                raise WebDAVAuthError(f"认证失败 ({resp.status_code})",
                                      status_code=resp.status_code)
            # 409 + AncestorsNotFound → 坚果云 quirk, 指数退避后重试
            is_ancestors_not_found = (
                resp.status_code == 409
                and b"AncestorsNotFound" in (resp.content or b"")
            )
            if is_ancestors_not_found and retry_on_ancestors_not_found and attempt < max_attempts:
                # 指数退避: 0.5s, 1.0s, 1.5s, 2.0s ...
                sleep_s = 0.5 * attempt
                logger.warning(
                    "PUT 409 AncestorsNotFound, sleep %.1fs + 重试: %s (attempt %d/%d)",
                    sleep_s, path_for_log, attempt, max_attempts,
                )
                last_err = resp
                await asyncio.sleep(sleep_s)
                continue
            # 最后一次仍失败, 抛错
            suffix = " (重试后)" if (is_ancestors_not_found and attempt > 1) else ""
            raise WebDAVError(
                f"PUT 失败{suffix}: {resp.status_code} "
                f"{resp.reason_phrase}: {_body_hint(resp)}",
                status_code=resp.status_code, reason=resp.reason_phrase,
            )
        # 防御性 fallthrough (理论不会到)
        raise WebDAVError(
            f"PUT 失败 (重试后): {last_err.status_code if last_err else '?'}",
            status_code=last_err.status_code if last_err else None,
            reason=last_err.reason_phrase if last_err else None,
        )

    async def download(self, path: str) -> Optional[bytes]:
        """下载文件 (GET)。

        404 → 返回 ``None`` (语义: 远端尚无此文件, 首次 push 前正常)。
        其他非 2xx → 抛 ``WebDAVError``。
        """
        log_path = self._log_path(path)
        logger.info("WebDAV download: %s", log_path)
        resp = await self._request("GET", path, headers={"Accept": "*/*"})
        if resp.status_code == 404:
            logger.info("WebDAV download: %s 不存在", path)
            return None
        if resp.status_code in (200, 206):
            return resp.content
        if resp.status_code in (401, 403):
            raise WebDAVAuthError(f"认证失败 ({resp.status_code})",
                                  status_code=resp.status_code)
        raise WebDAVError(
            f"GET 失败: {resp.status_code} {resp.reason_phrase}: {_body_hint(resp)}",
            status_code=resp.status_code, reason=resp.reason_phrase,
        )


__all__ = [
    "WebDAVClient",
    "WebDAVError",
    "WebDAVAuthError",
    "WebDAVNotFoundError",
]
