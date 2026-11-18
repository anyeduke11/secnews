/**
 * SentinelHomePage — 哨兵终端 · 资料层首页 (容器)
 *
 * B4 (2026-11-18) 绞杀者拆分: 原 808 行单文件按区块拆为 feed/ 下 7 个文件
 * (feedModel / FeedAtoms / UrlImport / FeedControls / FeedStates /
 *  FeedMustRead / FeedStream), 本文件只保留状态、取数与区块组合;
 * DOM / class / data-testid 与拆分前逐字一致 (页面测试原样复用)。
 *
 * 刷新节奏契约 (cadence 修正批, 2026-09-10): 后端按 settings 间隔跑 collect_all,
 * 一轮结束发一次 collect_done; SSE 路径绝不触发采集, 否则 "采集 → collect_done →
 * POST /api/refresh → 再采集" 会形成自激循环 (owner 反馈"刷新频率过高"的根因)。
 * B4 起右栏质量门禁与精选走 useQuery, collect_done 经 bindInvalidateOn('feed:')
 * 以 10s 节流整域失效; 主列 (useHotspotData) 保持 3s 防抖合并重拉。
 */
import { Suspense, useCallback, useEffect, useMemo, useState } from 'react';
import { SSE_EVENTS, useRealtimeInvalidation } from '../../hooks/realtime';
import { bindInvalidateOn, useQuery } from '../../hooks/useQuery';
import { useHotspotData } from '../../hooks/useHotspotData';
import { useFavorites } from '../../hooks/useFavorites';
import { useReactions } from '../../hooks/useReactions';
import { HotspotItem, plainSummary } from '../../types';
import { trackInterest } from '../../lib/interest';
import { getQualitySummary, getNewsAlertUnread, getPickedItems } from '../../api/secnews';
import { getRefreshIntervalSetting } from '../../api/shared';
import { PriorityDigestCard } from './PriorityDigestCard';
import { useReactionAction } from './ReactionButtons';
import { SentinelShell, usePipeReloadOnSse } from './SentinelShell';
import { RailWithPipe, SignalPanelLazy } from './SentinelHomeAux';
import { SignalPanelCompact } from '../v1/panels/SignalPanelCompact';
import { FeedModeBar, FeedSearchBar } from './feed/FeedControls';
import { FeedErrorPanel, FeedEmptyPanel, FeedSkeleton } from './feed/FeedStates';
import { FeedMustRead } from './feed/FeedMustRead';
import { FeedPicked, FeedDeep, FeedQueue, FeedRead } from './feed/FeedStream';
import type { FeedRowBinding } from './feed/FeedAtoms';
import {
  DEFAULT_COLLECT_MINUTES, KEYWORD_DEBOUNCE_MS, SIDE_RELOAD_GATE_MS,
  type QualitySummaryRaw, type ReadMode,
} from './feed/feedModel';
import './sentinel.css';

export function SentinelHomePage() {
  const [mode, setMode] = useState<ReadMode>('brief');
  const [channel, setChannel] = useState('all');
  const [timeRange, setTimeRange] = useState('24h');

  // 搜索框受控值 (即时反馈) 与实际下发给 hook 的防抖值
  const [keywordInput, setKeywordInput] = useState('');
  const [keyword, setKeyword] = useState('');

  const [collectMinutes, setCollectMinutes] = useState<number>(DEFAULT_COLLECT_MINUTES);

  const reloadPipe = usePipeReloadOnSse();

  // ── 资料层主数据: 全文搜索 + 时间窗 + cursor 分页统一由 hook 负责 ──
  const {
    items, total, categoryCounts, loading, loadingPage, error,
    hasMore, page, pageSize, totalPages, setPage, refresh, refetch,
    latestIngestionCount, latestIngestionAt, interestDomains,
  } = useHotspotData(channel, timeRange, keyword);

  // ── 收藏: 模块级单例 store, 乐观更新 + 失败回滚 ──
  const { count: favoriteCount, isFavorite, toggleFavorite } = useFavorites();
  // DEV-0311: 赞/踩 (available=false 时隐藏按钮组, 不渲染死键)
  const { reactionOf, available: reactionsAvailable } = useReactions();

  useEffect(() => {
    if (keywordInput === keyword) return;
    const t = window.setTimeout(() => setKeyword(keywordInput), KEYWORD_DEBOUNCE_MS);
    return () => window.clearTimeout(t);
  }, [keywordInput, keyword]);

  // 右栏质量门禁 (R-13: 待办域退役, 右栏只剩质量门禁): 缓存 + 20 分钟内不重复拉取
  const qualityQuery = useQuery<QualitySummaryRaw>(
    'feed:quality',
    () => getQualitySummary<QualitySummaryRaw>(),
  );
  const quality = qualityQuery.data ?? null;

  // ── 精选视图 (P2 2026-09-27): 独立数据源 /api/hotspots/picked, 仅 scan 模式取数 ──
  // pick_refresh SSE 已裁剪 (计划 Self-Review #1): 30min 采集粒度足够。
  const pickedQuery = useQuery(
    'feed:picked',
    () => getPickedItems().then(d => d.items),
    { enabled: mode === 'scan' },
  );

  // SSE 整域失效: 右栏质量门禁 + 精选, 10s 节流兜底重连回放多条 collect_done
  useEffect(
    () => bindInvalidateOn(SSE_EVENTS.COLLECT_DONE, 'feed:', { throttleMs: SIDE_RELOAD_GATE_MS }),
    [],
  );

  // 真实采集间隔 (分钟): 供页脚 / 空态文案, 与 /settings 里的选择保持一致
  useEffect(() => {
    let alive = true;
    getRefreshIntervalSetting()
      .then(d => {
        if (alive && d && typeof d.interval_minutes === 'number' && d.interval_minutes > 0) {
          setCollectMinutes(d.interval_minutes);
        }
      })
      .catch(() => { /* 接口不可达时保留默认值展示 */ });
    return () => { alive = false; };
  }, []);

  // 告警未读徽标 (scope=news 4 规则域): 挂载拉一次 + SSE news_alert 刷新
  const [newsUnread, setNewsUnread] = useState(0);
  const reloadNewsUnread = useCallback(() => {
    getNewsAlertUnread()
      .then(d => setNewsUnread(d.count))
      .catch(() => { /* 接口不可达时保留现值 */ });
  }, []);
  useEffect(() => { reloadNewsUnread(); }, [reloadNewsUnread]);

  // ── 深度视图 (P2): 当前条目长文过滤 (纯前端, spec §4) ──
  const deepItems = useMemo(
    () => items.filter(i => (i.summary?.length ?? 0) >= 200 || /分析|详解|深度|指南|research/.test(i.title)),
    [items],
  );

  // SSE: 只响应 collect_done (一轮采集只发一次)。其余事件与资料层无关, 不刷页面。
  // 心跳条: usePipeReloadOnSse 内部自带 10s 节流 + mountedReload 优先 (DEV-0167)
  // 主列: 3s 合并 (重连回放可能连发多条 collect_done), 避免翻页缓存被反复清空
  useRealtimeInvalidation([
    { types: SSE_EVENTS.COLLECT_DONE, handler: () => reloadPipe() },
    { types: SSE_EVENTS.COLLECT_DONE, handler: () => void refetch(), debounceMs: 3000 },
    { types: SSE_EVENTS.NEWS_ALERT, handler: reloadNewsUnread },
  ]);

  const [lead, secondaries] = useMemo(
    () => [items[0] ?? null, items.slice(1, 3)],
    [items],
  );

  // ── R-15 三段递进: 今日必读 (评分 Top3) → 待读 (未打开) → 已读 (本次会话打开过) ──
  // 已读仅为会话内真实阅读动作, 不落库、不造数; 刷新页面回到待读。
  const [readIds, setReadIds] = useState<string[]>([]);
  const markRead = useCallback((id: string) => {
    setReadIds(prev => (prev.includes(id) ? prev : [...prev, id]));
  }, []);
  const readSet = useMemo(() => new Set(readIds), [readIds]);
  const flashes = useMemo(() => items.slice(3), [items]);
  const toRead = useMemo(() => flashes.filter(i => !readSet.has(i.id)), [flashes, readSet]);
  const readItems = useMemo(() => flashes.filter(i => readSet.has(i.id)), [flashes, readSet]);

  // 今日一句话摘要条: 从头条 summary 抽首句 (真实数据, 无摘要时回退为收录计数)
  const todayLine = useMemo(() => {
    if (!lead) return null;
    const s = plainSummary(lead.summary);
    const first = s ? (s.split(/(?<=[。！？!?])/)[0] || s).trim() : '';
    return first ? first.slice(0, 120) : `今日收录 ${total} 篇 · 头条「${lead.title}」`;
  }, [lead, total]);

  // 「今日收录」口径: 后端 time_range=24h 即"今日 00:00 起"; 换频道/放宽时间窗/搜索后
  // total 已不是当日语义, 改标「范围内 / 匹配」, 心跳条该格回退为 '…' 避免误导。
  const isTodayScope = channel === 'all' && timeRange === '24h' && !keyword;
  const scopeLabel = keyword ? '匹配' : isTodayScope ? '今日收录' : '范围内';
  const ingestedForHeader = isTodayScope ? total : null;

  const star = useCallback((item: HotspotItem) => {
    // DEV-0314: 收藏动作入兴趣信号 (favorite 权重 3.0 此前完全闲置); 取消收藏无对应信号型
    if (!isFavorite(item.id)) trackInterest(item.id, 'favorite');
    void toggleFavorite(item);
  }, [toggleFavorite, isFavorite]);
  const doReact = useReactionAction();

  const goPrev = useCallback(() => setPage(page - 1), [page, setPage]);
  const goNext = useCallback(() => setPage(page + 1), [page, setPage]);

  const binding = useMemo<FeedRowBinding>(() => ({
    interestDomains,
    isFavorite,
    onStar: star,
    reactionOf,
    onReact: doReact,
    showReactions: reactionsAvailable,
  }), [interestDomains, isFavorite, star, reactionOf, doReact, reactionsAvailable]);

  const collectNow = useCallback(async () => {
    await refresh();
    qualityQuery.refetch();
    reloadPipe();
  }, [refresh, qualityQuery, reloadPipe]);

  return (
    <SentinelShell layer="data" mode={mode} ingested={ingestedForHeader}>
      {/* ===== 阅读模式 & 频道条 ===== */}
      <FeedModeBar
        mode={mode}
        onModeChange={setMode}
        newsUnread={newsUnread}
        channel={channel}
        onChannelChange={setChannel}
        total={total}
        categoryCounts={categoryCounts}
      />

      {/* ===== 检索条: 全文搜索 + 时间窗 ===== */}
      <FeedSearchBar
        keywordInput={keywordInput}
        onKeywordInput={setKeywordInput}
        onClearKeyword={() => { setKeywordInput(''); setKeyword(''); }}
        timeRange={timeRange}
        onTimeRangeChange={setTimeRange}
        onImported={() => { void refetch(); }}
        scopeLabel={scopeLabel}
        total={total}
        page={page}
        totalPages={totalPages}
        favoriteCount={favoriteCount}
        loadingPage={loadingPage}
      />

      {/* ===== 今日一句话摘要条 (R-15): 内容取自头条 summary, 不硬编码 ===== */}
      {mode !== 'scan' && !loading && !error && todayLine && (
        <div className="sn-oneline" data-testid="today-oneline" role="status">
          <span className="sn-oneline-k" aria-hidden="true">今日一句话</span>
          <p className="sn-oneline-v" title={todayLine}>{todayLine}</p>
          {lead && <span className="sn-oneline-src num">{lead.source}</span>}
        </div>
      )}

      {/* ===== 主布局 ===== */}
      <div className="layout">
        <main className="maincol">
          {mode === 'scan' ? (
            /* 精选视图 (P2 2026-09-27): 独立数据源, 自带加载/空态, 不混排常规快讯流 */
            <FeedPicked state={pickedQuery.state} items={pickedQuery.data} binding={binding} />
          ) : loading ? (
            <FeedSkeleton />
          ) : error ? (
            <FeedErrorPanel error={error} onRetry={() => void refetch()} />
          ) : items.length === 0 ? (
            <FeedEmptyPanel keyword={keyword} collectMinutes={collectMinutes} onCollect={collectNow} />
          ) : mode === 'deep' ? (
            /* 深度视图 (P2 2026-09-27): 长文候选过滤, 纯前端 */
            <FeedDeep items={deepItems} binding={binding} />
          ) : (
            <>
              {/* DEV-0177 T0.5 收敛: SK-01 今日重点情报 (实践域分区) */}
              <PriorityDigestCard />

              {/* ① 今日必读 — 评分最高的头条 + 次级重点 */}
              <FeedMustRead lead={lead} secondaries={secondaries} itemsCount={items.length} binding={binding} />

              {/* ② 待读 / 告警 (2026-09-27: alert 接真告警列表) + 游标分页 */}
              <FeedQueue
                mode={mode}
                toRead={toRead}
                binding={binding}
                onOpen={markRead}
                page={page}
                totalPages={totalPages}
                total={total}
                hasMore={hasMore}
                loadingPage={loadingPage}
                itemsCount={items.length}
                latestIngestionCount={latestIngestionCount}
                latestIngestionAt={latestIngestionAt}
                onPrev={goPrev}
                onNext={goNext}
              />

              {/* ③ 已读 — 仅本次会话真实打开过的条目, 无数据时整段不渲染 */}
              {mode !== 'alert' && readItems.length > 0 && (
                <FeedRead items={readItems} binding={binding} onOpen={markRead} />
              )}
            </>
          )}
        </main>

        {/* 右栏 */}
        <aside className="rail">
          {/* R-15: 今日 Signal 摘要 (同一 signals 数据源, 无数据为空态) */}
          <SignalPanelCompact />
          <RailWithPipe quality={quality} />
        </aside>
      </div>

      {/* v0.8.5 能力区块: 受管信号 (SK-01 供给, 立项 → /cases/:id)
          D7 收口: 本区块位于主列之后 (首屏之下), 改为按需加载, 不占首屏 JS 包体 */}
      <Suspense fallback={<section aria-label="受管信号 (v1.0 能力区块)">载入中…</section>}>
        <SignalPanelLazy />
      </Suspense>

      {/* 页脚状态行 */}
      <footer className="endnote">
        <span>SECNEWS EDITORIAL DESK · 资料层</span>
        <span>本地运行 · 无云端依赖</span>
        <span>SSE 已连接 · 每 {collectMinutes} 分钟自动采集 · 采集完成即刷新</span>
        <span>{scopeLabel} {total} 篇 · 每页 {pageSize}</span>
      </footer>
    </SentinelShell>
  );
}

export default SentinelHomePage;