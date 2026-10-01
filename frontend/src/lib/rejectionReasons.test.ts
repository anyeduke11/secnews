/**
 * rejectionReasons — 拒收 flag 词典 + reason 解析 (spec §3)。
 * 意图: 词典兜底层恒可用 — LLM explain 未生成时每条记录仍可读。
 */
import { describe, it, expect } from 'vitest';
import {
  REJECTION_FLAG_LABELS,
  parseRejectionFlags,
  flagLabel,
} from './rejectionReasons';

describe('rejectionReasons — 拒收词典', () => {
  it('10 个生产 flag 全部有映射', () => {
    const REQUIRED = [
      'content_hash_duplicate', 'url_duplicate', 'similar_title_duplicate',
      'category_mismatch', 'title_summary_inconsistent', 'empty_summary',
      'empty_title', 'author_unknown', 'title_spam_words', 'noise_title',
    ];
    for (const f of REQUIRED) {
      expect(REJECTION_FLAG_LABELS[f], `missing: ${f}`).toBeTruthy();
    }
  });

  it('parseRejectionFlags: 裸数组形态', () => {
    expect(
      parseRejectionFlags("['category_mismatch', 'content_hash_duplicate']"),
    ).toEqual(['category_mismatch', 'content_hash_duplicate']);
  });

  it('parseRejectionFlags: flags= 形态 (strict_mode 写入)', () => {
    expect(parseRejectionFlags("flags=['content_hash_duplicate']"))
      .toEqual(['content_hash_duplicate']);
  });

  it('parseRejectionFlags: 空与垃圾输入 → 空数组', () => {
    expect(parseRejectionFlags('')).toEqual([]);
    expect(parseRejectionFlags('noise_title')).toEqual(['noise_title']);
  });

  it('flagLabel: 已知 flag → 中文; 未知 flag 原样', () => {
    expect(flagLabel('content_hash_duplicate')).toBe('与已收录内容重复');
    expect(flagLabel('some_new_flag')).toBe('some_new_flag');
  });
});
