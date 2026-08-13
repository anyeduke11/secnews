/**
 * report/types — ReportPage 共享类型定义。
 *
 * 拆自原 ReportPage.tsx (1401 行): 三个报告模式 (日报/周报/月报) 的
 * overview 类型 + 模式切换 Tab 类型 + 页面 props。
 * 纯结构拆分, 类型定义与原文件逐字等价。
 */

// ── 页面级 ──

export type Tab = 'daily' | 'weekly' | 'monthly';

export interface ReportPageProps {
  onBack: () => void;
}

// ── 共享文章行类型 (三个模式的文章结构一致) ──

export interface ReportHighlightArticle {
  id: string;
  title: string;
  summary: string;
  source: string;
  url: string;
  score: number;
}

// ── Daily Report Types ──

export type DailyHighlightArticle = ReportHighlightArticle;

export interface DailyHighlight {
  id: string;
  title: string;
  count: number;
  summary: string;
  articles: DailyHighlightArticle[];
}

export interface DailyStats {
  events: number;
  selected: number;
  sources: number;
  reading_time: number;
}

export interface DailyOverview {
  date: string;
  total: number;
  category_counts: Record<string, number>;
  main_theme: string;
  hot_analysis: string;
  highlights: DailyHighlight[];
  other_news: Array<{ id: string; title: string; url: string; source: string; category: string; category_label: string }>;
  stats: DailyStats;
  generated_at: string;
}

// ── Weekly Report Types ──

export interface WeeklyPeriod {
  label: string;
  vol: string;
  start: string;
  end: string;
  week_start: string;
}

export interface WeeklyStats {
  events: number;
  selected: number;
  daily_reports: number;
  reading_time: number;
}

export type WeeklyHighlightArticle = ReportHighlightArticle;

export interface WeeklyHighlight {
  id: string;
  title: string;
  count: number;
  summary: string;
  articles: WeeklyHighlightArticle[];
}

export interface WeeklyOverview {
  period: WeeklyPeriod;
  total: number;
  category_counts: Record<string, number>;
  main_theme: string;
  highlights: WeeklyHighlight[];
  stats: WeeklyStats;
  generated_at: string;
}

// ── Monthly Report Types ──

export interface MonthlyPeriod {
  label: string;
  start: string;
  end: string;
  offset: number;
}

export type MonthlyHighlightArticle = ReportHighlightArticle;

export interface MonthlyHighlight {
  id: string;
  title: string;
  count: number;
  summary: string;
  articles: MonthlyHighlightArticle[];
}

export interface MonthlyStats {
  events: number;
  selected: number;
  daily_reports: number;
  reading_time: number;
}

export interface MonthlyOverview {
  period: MonthlyPeriod;
  total: number;
  category_counts: Record<string, number>;
  main_theme: string;
  highlights: MonthlyHighlight[];
  stats: MonthlyStats;
  generated_at: string;
}
