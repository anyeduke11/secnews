"""Phase 10 回溯脚本: 修复 DB 中 source=KrebsOnSecurity 的噪声数据

背景
----
Phase 10 用户反馈: krebsonsecurity.com 抓取的资讯标题错抓为 "X Comments"
(评论数) + URL 末尾带 "#comments" 锚点。修复 base.py 默认 _parse_html 后
**未来** 抓取不会再有这个问题, 但 DB 里已经存的旧数据需要回溯。

修复策略
--------

1. **URL 端**: 去掉 #comments / #respond / #comment-NNN 锚点后缀
   (URL 实际指向文章本体, 锚点只是评论数链接的位置)
2. **标题端**: 对 URL 末带 #comments 的项, 重新抓取 krebsonsecurity 主页
   HTML → 找到同 URL 对应 article 的 h1/h2.entry-title 真实标题 → 替换。
   主页拉取失败则用 URL slug 推断标题 (e.g. "cisa-admin-leaked-aws-govcloud-keys-on-github"
   → "CISA Admin Leaked AWS GovCloud Keys on Github")
3. **删除多余条目**: 标题是 "X comments" 形式 (e.g. "17 Comments") 的项
   直接删除 (因为它们是评论数链接, 不是真实资讯)

执行方式
--------
- 同步执行, 单线程, 跑完输出统计
- 修改 hotspot_db 之前先 COUNT, 跑完再 COUNT, 给出 diff
- 不修改 quality_score / quality_flags / quality_checked_at (避免污染审计)

只针对 source = 'KrebsOnSecurity' (其他源不改动)
"""
from __future__ import annotations

import re
import sqlite3
import ssl
import sys
import urllib.request
from html import unescape
from pathlib import Path
from urllib.parse import urlparse

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
ANCHOR_SUFFIXES = ("#comments", "#respond", "#comments-area")
COMMENT_TITLE_RE = re.compile(r"^\d+\s+comments?$", re.IGNORECASE)
PERMALINK_PREFIX_RE = re.compile(r"^Permalink to\s+", re.IGNORECASE)


def strip_anchor(url: str) -> tuple[str, bool]:
    """去掉 URL 末尾的 #comments 等锚点。返回 (clean_url, changed)。"""
    for anchor in ANCHOR_SUFFIXES:
        if url.endswith(anchor):
            return url[: -len(anchor)], True
    # 兜底: 找 #comment-NNN 数字注释
    m = re.search(r"#comment-\d+", url)
    if m:
        return url[: m.start()], True
    return url, False


def strip_permalink_title(title: str) -> str:
    """去掉 "Permalink to <真实标题>" 前缀。"""
    return PERMALINK_PREFIX_RE.sub("", title or "").strip()


def fetch_article_titles(blog_url: str) -> dict[str, str]:
    """抓 krebsonsecurity 主页 HTML, 抽 {url: title} 映射。"""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(blog_url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        html = urllib.request.urlopen(req, timeout=20, context=ctx).read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"[WARN] fetch {blog_url} failed: {type(e).__name__}: {e}")
        return {}

    mapping: dict[str, str] = {}
    # 优先: h1/h2.entry-title > a[rel=bookmark]
    pat = re.compile(
        r'<h[12][^>]*class="entry-title"[^>]*>\s*'
        r'<a[^>]+href="([^"]+)"[^>]*rel="bookmark"[^>]*>([^<]+)</a>',
        re.IGNORECASE | re.DOTALL,
    )
    for m in pat.finditer(html):
        url = m.group(1)
        title = unescape(m.group(2)).strip()
        # 去掉 #comments 后缀作为 key
        clean_url, _ = strip_anchor(url)
        if title and clean_url:
            mapping[clean_url] = title
    return mapping


def slug_to_title(slug: str) -> str:
    """URL slug → 推断标题 (兜底: 主页拉取失败时使用)

    e.g. "cisa-admin-leaked-aws-govcloud-keys-on-github"
       → "Cisa Admin Leaked Aws Govcloud Keys On Github"
    """
    text = slug.replace("-", " ").strip()
    if not text:
        return text
    # Title Case 全部单词
    return " ".join(w[:1].upper() + w[1:] for w in text.split())


def main() -> int:
    db_path = Path("backend/hotspot.db")
    if not db_path.exists():
        print(f"[ERR] DB not found: {db_path}")
        return 1

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        # 1. 先扫一遍需要修复的行
        rows = conn.execute(
            "SELECT id, title, url, source FROM hotspots "
            "WHERE source = 'KrebsOnSecurity' "
            "ORDER BY id"
        ).fetchall()
        print(f"[init] source=KrebsOnSecurity rows: {len(rows)}")

        # 分类
        to_delete: list[int] = []  # 标题是 "X comments"
        to_strip_anchor: list[tuple[int, str, str]] = []  # (id, old_url, new_url)
        to_retitle: list[tuple[int, str, str, str]] = []  # (id, old_title, url, source)
        to_strip_permalink: list[tuple[int, str]] = []  # (id, "Permalink to X" → "X")
        for r in rows:
            t = (r["title"] or "").strip()
            # 标题是评论数
            if COMMENT_TITLE_RE.match(t):
                to_delete.append(r["id"])
                continue
            # 标题是 "Permalink to ..."
            stripped = strip_permalink_title(t)
            if stripped != t and stripped:
                to_strip_permalink.append((r["id"], stripped))
            # URL 有锚点
            clean_url, changed = strip_anchor(r["url"])
            if changed:
                to_strip_anchor.append((r["id"], r["url"], clean_url))
                to_retitle.append((r["id"], t, clean_url, r["source"]))

        print(f"[scan] to_delete(comment-titled): {len(to_delete)}")
        print(f"[scan] to_strip_anchor: {len(to_strip_anchor)}")
        print(f"[scan] to_strip_permalink: {len(to_strip_permalink)}")
        print(f"[scan] to_retitle: {len(to_retitle)}")

        if (
            not to_delete
            and not to_strip_anchor
            and not to_retitle
            and not to_strip_permalink
        ):
            # 仍然跑 entity decode + match replace(它们每次都扫描)
            pass

        # 2. 拉主页拿正确标题映射
        title_map = fetch_article_titles("https://krebsonsecurity.com/")
        print(f"[fetch] {len(title_map)} articles found in blog index")

        # 3. 删除噪声项 (评论数标题)
        if to_delete:
            placeholders = ",".join("?" * len(to_delete))
            conn.execute(
                f"DELETE FROM hotspots WHERE id IN ({placeholders})",
                to_delete,
            )
            print(f"[delete] removed {len(to_delete)} comment-titled rows")

        # 4. 修复 URL + 标题
        fixed_url = 0
        fixed_title = 0
        fallback_title = 0
        dup_skipped = 0
        to_delete_after_dup: list[int] = []
        seen_urls: dict[str, int] = {}  # url -> kept id
        for hid, old_url, clean_url in to_strip_anchor:
            # strip anchor
            # 先查 DB 是否已存在同 clean_url (且不是本行)
            existing = conn.execute(
                "SELECT id FROM hotspots WHERE url = ? AND id != ?",
                (clean_url, hid),
            ).fetchone()
            if existing:
                # 重复: 删去 #comments 版本的 (短 id,旧标题)
                # 保留原有的 (无 #comments, 真实标题)
                to_delete_after_dup.append(hid)
                dup_skipped += 1
                continue
            seen_urls[clean_url] = hid
            conn.execute(
                "UPDATE hotspots SET url = ? WHERE id = ?",
                (clean_url, hid),
            )
            fixed_url += 1
        if to_delete_after_dup:
            placeholders = ",".join("?" * len(to_delete_after_dup))
            conn.execute(
                f"DELETE FROM hotspots WHERE id IN ({placeholders})",
                to_delete_after_dup,
            )
        print(f"[update] stripped #comments anchor from {fixed_url} URLs")
        print(f"[update] dedup removed {dup_skipped} duplicate rows (kept clean-url version)")

        for hid, old_title, clean_url, _src in to_retitle:
            if hid in to_delete_after_dup:
                continue
            new_title = title_map.get(clean_url)
            if not new_title:
                # 兜底: 从 slug 推断
                slug = urlparse(clean_url).path.strip("/").split("/")[-1]
                new_title = slug_to_title(slug)
                fallback_title += 1
            conn.execute(
                "UPDATE hotspots SET title = ? WHERE id = ?",
                (new_title, hid),
            )
            fixed_title += 1
        conn.commit()
        print(f"[update] retitled {fixed_title} rows (fallback from slug: {fallback_title})")

        # 4.5 处理 "Permalink to X" 标题 (剥掉前缀)
        fixed_permalink = 0
        for hid, stripped in to_strip_permalink:
            if hid in to_delete_after_dup:
                continue
            conn.execute(
                "UPDATE hotspots SET title = ? WHERE id = ?",
                (stripped, hid),
            )
            fixed_permalink += 1
        conn.commit()
        print(f"[update] stripped 'Permalink to' prefix from {fixed_permalink} titles")

        # 4.6 HTML entity decode (e.g. &#8217; → ', &amp; → &)
        rows = conn.execute(
            "SELECT id, title, url FROM hotspots WHERE source = 'KrebsOnSecurity'"
        ).fetchall()
        fixed_entity = 0
        for r in rows:
            new_title = unescape(r["title"] or "")
            if new_title != r["title"]:
                conn.execute(
                    "UPDATE hotspots SET title = ? WHERE id = ?",
                    (new_title, r["id"]),
                )
                fixed_entity += 1
        conn.commit()
        print(f"[update] HTML entity decoded on {fixed_entity} titles")

        # 4.7 删"句子当标题"项: 标题看起来像 body 片段而非 article 标题
        # 启发式:
        #   - 标题以小写字母开头(文章标题通常首字母大写)
        #   - 或不含 WordPress 标题特征词 (无大写, 无 "How" / "What" / "Why" 等疑问词)
        # 兜底: 只删 URL 含 krebsonsecurity.com 且 title 与 entry-title 显著不一致的
        # 这里简化: 拉主页 entry-title, 凡是与主页 title 显著不匹配但 URL 在主页出现的,
        # 替换为正确 title
        if title_map:
            rows = conn.execute(
                "SELECT id, title, url FROM hotspots "
                "WHERE source = 'KrebsOnSecurity' AND url LIKE '%krebsonsecurity.com%'"
            ).fetchall()
            fixed_match = 0
            for r in rows:
                clean_url, _ = strip_anchor(r["url"])
                good_title = title_map.get(clean_url)
                if good_title and good_title != r["title"]:
                    # 主页有此 article, 用正确 title 替换
                    conn.execute(
                        "UPDATE hotspots SET title = ? WHERE id = ?",
                        (good_title, r["id"]),
                    )
                    fixed_match += 1
            conn.commit()
            print(f"[update] replaced {fixed_match} mismatched titles with blog index title")

        # 4.8 删"明显噪声标题"项: navigation words + 句子片段
        NAV_WORDS = {
            "skip to content", "skip to main content",
            "about", "about the author", "advertising", "advertising/speaking",
            "menu", "linkedin profile", "home",
        }
        # 句子片段启发式: 以小写字母开头且不含标点结尾(句中片段)
        # 或: 整个标题只是一个"短语"(不含 question mark 且不含冠词 the/a/an 在开头大写形式)
        rows = conn.execute(
            "SELECT id, title FROM hotspots WHERE source = 'KrebsOnSecurity'"
        ).fetchall()
        to_del_noise: list[int] = []
        for r in rows:
            t = (r["title"] or "").strip()
            low = t.lower()
            if low in NAV_WORDS:
                to_del_noise.append(r["id"])
                continue
            # 以小写字母开头 + 长度 < 40 (像 "a blog post" / "a breach")
            if t and t[0].islower() and len(t) < 40:
                to_del_noise.append(r["id"])
                continue
            # 整个标题就是个名词短语 (e.g. "residential proxy" / "ransom attacks")
            if " " in t and t[0].islower() and len(t.split()) <= 3 and "?" not in t:
                # 进一步: 不在 title_map 里(说明主页没有此 article)
                in_blog = any(v == t for v in title_map.values())
                if not in_blog:
                    to_del_noise.append(r["id"])
                    continue
        if to_del_noise:
            placeholders = ",".join("?" * len(to_del_noise))
            conn.execute(
                f"DELETE FROM hotspots WHERE id IN ({placeholders})",
                to_del_noise,
            )
            conn.commit()
            print(f"[delete] removed {len(to_del_noise)} sentence-fragment / nav-word rows")

        # 4.9 修复"以小写字母开头"的 Krebs 标题(长 body 片段)
        # 用 URL slug 推断 Article Title Case
        rows = conn.execute(
            "SELECT id, title, url FROM hotspots "
            "WHERE source = 'KrebsOnSecurity' AND url LIKE '%krebsonsecurity.com/%'"
        ).fetchall()
        fixed_slug = 0
        for r in rows:
            t = (r["title"] or "").strip()
            if not t or not t[0].islower():
                continue
            if "?" in t:  # 真实标题有问号
                continue
            # slug → Title Case
            path = urlparse(r["url"]).path.strip("/")
            parts = [p for p in path.split("/") if p]
            if len(parts) < 3:  # 至少 /YYYY/MM/slug
                continue
            slug = parts[-1]
            new_title = slug_to_title(slug)
            if new_title and new_title != t:
                conn.execute(
                    "UPDATE hotspots SET title = ? WHERE id = ?",
                    (new_title, r["id"]),
                )
                fixed_slug += 1
        conn.commit()
        print(f"[update] slug-inferred title on {fixed_slug} lowercase rows")

        # 4.10 删 source=KrebsOnSecurity 但 URL 不在 krebsonsecurity.com 域
        #      且 title 像是 body 片段(< 60 字符 + 至少 2 词)
        #      理由: Krebs 主页 _parse_html stage 2 偶尔会抓到跨域的 body 链接
        #      (如 senate.gov PDF / justice.gov indictment) 当作 Krebs 文章
        rows = conn.execute(
            "SELECT id, title, url FROM hotspots "
            "WHERE source = 'KrebsOnSecurity' "
            "AND (url NOT LIKE '%krebsonsecurity.com%' OR url IS NULL OR url = '')"
        ).fetchall()
        to_del_external: list[int] = []
        for r in rows:
            t = (r["title"] or "").strip()
            if not t:
                to_del_external.append(r["id"])
                continue
            # 启发式: < 60 字符 + 多个词(像短语) + 不含问号
            if len(t) < 60 and len(t.split()) >= 2 and "?" not in t and "CISA" not in t:
                to_del_external.append(r["id"])
                continue
            # 标题以小写开头
            if t and t[0].islower():
                to_del_external.append(r["id"])
        if to_del_external:
            placeholders = ",".join("?" * len(to_del_external))
            conn.execute(
                f"DELETE FROM hotspots WHERE id IN ({placeholders})",
                to_del_external,
            )
            conn.commit()
            print(f"[delete] removed {len(to_del_external)} external-url rows attributed to Krebs")

        # 5. 总结
        print(
            f"\n[summary] deletions={len(to_delete) + dup_skipped + len(to_del_noise) + len(to_del_external)} "
            f"url_fixed={fixed_url} retitled={fixed_title} "
            f"permalink_fixed={fixed_permalink} entity_decoded={fixed_entity} "
            f"slug_inferred={fixed_slug}"
        )
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
