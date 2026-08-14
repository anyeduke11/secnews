"""Simhash 中文标题相似度检测 — 用于三层去重第 2 层。

实现：
- 中文按字符 bigram 提取特征
- 英文按空格分词
- 64-bit simhash 值
- Hamming 距离 < 阈值视为重复
"""
from __future__ import annotations

import re
from typing import Optional

# 非字母数字分隔符
_WORD_SPLIT_RE = re.compile(r"[^\w]+")


def _tokenize(text: str) -> list[str]:
    """中文按字符 bigram，英文按空格分词。

    >>> _tokenize("hello world")
    ['hello', 'world']
    >>> _tokenize("网络安全")
    ['网络', '络安', '全']  # bigram: 网络, 络安, 安全
    """
    if not text:
        return []

    tokens: list[str] = []
    # 先按空白/标点切分英文单词
    words = _WORD_SPLIT_RE.split(text.strip())
    for word in words:
        if not word:
            continue
        # 判断是否包含中文字符
        if any("\u4e00" <= ch <= "\u9fff" for ch in word):
            # 中文：按字符 bigram
            chars = list(word)
            for i in range(len(chars)):
                if i + 1 < len(chars):
                    tokens.append(chars[i] + chars[i + 1])
                else:
                    tokens.append(chars[i])
        else:
            # 英文：整体作为一个 token
            if word:
                tokens.append(word.lower())
    return tokens


def _hash_token(token: str) -> int:
    """对 token 计算确定性 64-bit hash。

    P1 修复: 原实现用 Python 内置 ``hash()`` — 其对 str 有 PYTHONHASHSEED
    进程级随机化, 同一 token 在不同进程/运行下 hash 值不同 → simhash 相似度
    判定跨运行不稳定 (test_duplicate_similar_title 全量 flaky 的根因, 且
    生产去重在服务重启后结果也会漂移)。改用 SHA-256 前 8 字节, 确定性且
    分布均匀。
    """
    import hashlib

    digest = hashlib.sha256(token.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


def compute_simhash(text: str) -> int:
    """计算文本的 64-bit simhash 值。

    Args:
        text: 输入文本（标题）

    Returns:
        64-bit 整数 simhash 值
    """
    tokens = _tokenize(text)
    if not tokens:
        return 0

    # 64 维向量，初始化为 0
    v = [0] * 64

    for token in tokens:
        h = _hash_token(token)
        for i in range(64):
            if h & (1 << i):
                v[i] += 1
            else:
                v[i] -= 1

    # 聚合为 64-bit 值
    fingerprint = 0
    for i in range(64):
        if v[i] > 0:
            fingerprint |= (1 << i)
    return fingerprint


def hamming_distance(a: int, b: int) -> int:
    """计算两个 simhash 值的 Hamming 距离。

    Args:
        a: 第一个 simhash 值
        b: 第二个 simhash 值

    Returns:
        Hamming 距离（不同的 bit 数）
    """
    xor = a ^ b
    # 统计 1 的个数
    count = 0
    while xor:
        count += xor & 1
        xor >>= 1
    return count


def is_duplicate(
    simhash_a: int,
    simhash_b: int,
    threshold: int = 5,
) -> bool:
    """判断两个 simhash 值是否重复。

    Args:
        simhash_a: 第一个文本的 simhash
        simhash_b: 第二个文本的 simhash
        threshold: Hamming 距离阈值（默认 5）

    Returns:
        Hamming 距离 < threshold 返回 True
    """
    return hamming_distance(simhash_a, simhash_b) < threshold


__all__ = [
    "compute_simhash",
    "hamming_distance",
    "is_duplicate",
    "_tokenize",
]