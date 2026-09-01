/**
 * routes/oauth-callback — OAuth 授权回调页 (D1 Batch ⑧).
 *
 * 流程:
 * 1. CloudBase OAuth 授权后跳转回 ?code=...&state=...
 * 2. 校验 state 与 sessionStorage 一致 (CSRF 防护)
 * 3. 用 code 换 access_token (前端直接 POST /api/secrets/unlock-with-oauth? —
 *    实际生产中前端应通过后端 /api/secrets/oauth-exchange 间接换 token,
 *    避免 client_secret 暴露; 当前 mock 模式直接传 token 字符串即可)
 * 4. 跳回 /secnews/settings (或上一页面)
 */
import { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';

export function OAuthCallbackPage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const [status, setStatus] = useState<'pending' | 'ok' | 'fail'>('pending');
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      const code = params.get('code');
      const state = params.get('state');
      const expectedState = sessionStorage.getItem('oauth_state');
      sessionStorage.removeItem('oauth_state');

      if (!code) {
        setStatus('fail');
        setErr('缺少 authorization code');
        return;
      }
      if (!state || state !== expectedState) {
        setStatus('fail');
        setErr('OAuth state 不匹配 (可能 CSRF)');
        return;
      }

      // mock 模式: code 直接是 token; 真身模式需要后端交换
      // 把 code 当 token 传给后端 /api/secrets/unlock-with-oauth
      try {
        const r = await fetch('/api/secrets/unlock-with-oauth', {
          method: 'POST',
          headers: { 'content-type': 'application/json' },
          body: JSON.stringify({ token: code, role: 'admin' }),
        });
        if (!r.ok) {
          const t = await r.text();
          setStatus('fail');
          setErr(`OAuth 解锁失败: ${r.status} ${t}`);
          return;
        }
        setStatus('ok');
        // 短暂显示成功信息后跳转
        setTimeout(() => navigate('/secnews/settings', { replace: true }), 1500);
      } catch (e: any) {
        setStatus('fail');
        setErr(`网络错误: ${e?.message || e}`);
      }
    })();
  }, [params, navigate]);

  return (
    <div className="flex items-center justify-center min-h-[60vh]">
      <div className="flex flex-col gap-3 items-center">
        {status === 'pending' && (
          <p className="text-sm" style={{ color: 'var(--text-muted)' }}>OAuth 回调处理中…</p>
        )}
        {status === 'ok' && (
          <p className="text-sm" style={{ color: 'var(--color-success)' }}>
            ✓ 解锁成功, 正在跳转…
          </p>
        )}
        {status === 'fail' && (
          <p className="text-sm" style={{ color: 'var(--color-error)' }}>
            ✗ {err}
          </p>
        )}
      </div>
    </div>
  );
}