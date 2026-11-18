// DeepReadPage — Phase 4 S4-2: 深度分析面板 (分类型动态分节)
//
// 路由: /deep/:type/:id
// 布局: 顶部元信息条 (provider / model / latency / tokens / cost) + 动态分节折叠卡 + 重新生成按钮
//
// 分节集合由后端按**文章类型**下发 (视角 profile 决定有哪几节、叫什么、什么色调),
// 前端不再假设固定 4 节 —— 只负责按 tone 上色、按 key 查图标 (未知 key 用默认图标)。
// 首次生成会真调 LLM, sensenova 实测十几到几十秒, 二次访问命中后端缓存则瞬时返回。
//
// 与老版 DeepReadView 的区别:
//   - 老版: 三栏 (文章 / 推荐 / 笔记), 不调 LLM
//   - 新版: 分节报告, 调 /api/deep-read LLM 生成, 二次访问走 cache
import { useState, useEffect, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import { useDeepRead } from '../hooks/useDeepRead';
import { useGoBack } from '../hooks/useGoBack';
import { DeepReadPageHeader } from './DeepReadPageHeader';
import { DeepReadPageMetaBar } from './DeepReadPageMetaBar';
import { SectionCard } from './DeepReadPageSectionCard';

export function DeepReadPage() {
  const { type, id } = useParams<{ type: string; id: string }>();
  const goBack = useGoBack();
  const { data, sections, loading, error, regenerate, clear } = useDeepRead();
  // v3.1: 用户显式选择的框架 ('' = 自动, LLM 按内容自选); 一次选择只影响
  // 本次重新生成, 不落库——刷新页面回到自动模式。
  const [pickedFramework, setPickedFramework] = useState('');

  // 进入即分析: force=false 命中后端缓存则瞬时返回, 无缓存则直接调 LLM 生成
  useEffect(() => {
    if (!type || !id) return;
    regenerate(type, id, false);
    return clear;
  }, [type, id, regenerate, clear]);

  const handleRegenerate = useCallback(async (fw?: string) => {
    if (!type || !id) return;
    await regenerate(type, id, true, fw);
  }, [type, id, regenerate]);

  if (!type || !id) {
    return (
      <div style={{ padding: 'var(--space-6, 32px)', textAlign: 'center', color: 'var(--text-muted)' }}>
        缺少实体类型或 ID
      </div>
    );
  }

  const isEmpty = !data && !loading && !error;

  return (
    <div
      style={{
        maxWidth: 'min(1080px, 100%)',
        margin: '0 auto',
        padding: 'var(--space-4, 16px)',
        display: 'flex',
        flexDirection: 'column',
        gap: 'var(--space-3, 12px)',
      }}
    >
      {/* v3.1 标题区: headline 大标题 + 框架选择器 (选择即按该框架重新生成);
          旧报告无 headline 时只剩选择器行 */}
      <DeepReadPageHeader
        data={data}
        loading={loading}
        pickedFramework={pickedFramework}
        onPickFramework={setPickedFramework}
        onRegenerate={handleRegenerate}
      />
      {/* 顶部元信息条 */}
      <DeepReadPageMetaBar
        type={type}
        id={id}
        data={data}
        loading={loading}
        pickedFramework={pickedFramework}
        onRegenerate={handleRegenerate}
        onBack={goBack}
      />

      {/* 错误 */}
      {error && (
        <div
          style={{
            padding: 'var(--space-3, 12px)',
            border: '1px solid var(--color-error)',
            borderRadius: 'var(--radius-md, 8px)',
            background: 'color-mix(in srgb, var(--color-error) 8%, transparent)',
            color: 'var(--color-error)',
            fontSize: 13,
          }}
        >
          {error}
        </div>
      )}

      {/* 空状态 (首次访问, 无 cache) */}
      {isEmpty && !error && (
        <div
          style={{
            padding: 'var(--space-6, 32px)',
            textAlign: 'center',
            color: 'var(--text-muted)',
            fontSize: 13,
          }}
        >
          深度分析未完成, 点击右上角"重新生成"重试。
        </div>
      )}

      {/* 加载中 (首次要真调 LLM, 实测十几~几十秒) */}
      {loading && (
        <div
          style={{
            padding: 'var(--space-4, 16px)',
            textAlign: 'center',
            color: 'var(--text-muted)',
            fontSize: 13,
            lineHeight: 1.7,
          }}
        >
          正在按文章类型生成深度解读，请稍候…
          <br />
          <span style={{ fontSize: 11 }}>首次生成需调用 AI，通常十几到几十秒；再次访问将直接读取已存结果。</span>
        </div>
      )}

      {/* 分节报告 (节集合与顺序由后端按文章类型下发) */}
      {data && !loading && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2, 8px)' }}>
          {sections.map((sec) => (
            <SectionCard key={sec.key} section={sec} />
          ))}
        </div>
      )}
    </div>
  );
}