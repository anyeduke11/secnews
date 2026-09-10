/**
 * useGoBack — 工具页「返回」按钮的统一行为 (2026-09-10 壳统一后取代 useGoHome)
 *
 * 壳的品牌锚点 / 资料层 tab 已经提供「回首页」, 页级返回按钮只有在能回到来路时才有价值:
 *   - 站内有上一页 → navigate(-1)   (BrowserRouter 在 history.state.idx 记录站内栈深度, 首次落地为 0,
 *                                    外站跳入时该条目也无 idx, 所以 idx>0 ⇔ 上一条是本应用页面)
 *   - 直接落地 / 无来路 → navigate(fallback), 默认 '/'
 *
 * 用法:
 *   const goBack = useGoBack();               // 回上一页, 否则首页
 *   const goBack = useGoBack('/skill-store'); // 详情页: 回上一页, 否则回商店
 */
import { useCallback } from 'react';
import { useNavigate } from 'react-router-dom';

export function useGoBack(fallback = '/') {
  const navigate = useNavigate();
  return useCallback(() => {
    const idx = (window.history.state as { idx?: unknown } | null)?.idx;
    if (typeof idx === 'number' && idx > 0) navigate(-1);
    else navigate(fallback);
  }, [navigate, fallback]);
}
