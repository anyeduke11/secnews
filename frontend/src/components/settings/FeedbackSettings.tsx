/**
 * settings/FeedbackSettings — 点赞/点踩记录 + 角色倾向总结。
 */
import { useState, useEffect } from 'react';

interface FeedbackEvent {
  id: number;
  entity_type: string;
  entity_id: string;
  action: 'like' | 'dislike';
  signal: number;
  category?: string;
  source?: string;
  tags?: string;
  title?: string;
  created_at: string;
}

interface FeedbackProfile {
  total_likes: number;
  total_dislikes: number;
  recent: FeedbackEvent[];
}

interface RoleSummary {
  summary: string;
  interests: string[];
  dislikes: string[];
  preferred_sources: string[];
  reading_style: string;
  confidence: number;
}

export function FeedbackSettings() {
  const [profile, setProfile] = useState<FeedbackProfile | null>(null);
  const [history, setHistory] = useState<FeedbackEvent[]>([]);
  const [role, setRole] = useState<RoleSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const [profileRes, historyRes, roleRes] = await Promise.all([
          fetch('/api/feedback/profile?limit=50'),
          fetch('/api/feedback/history?limit=100'),
          fetch('/api/feedback/role-summary'),
        ]);
        if (!profileRes.ok || !historyRes.ok || !roleRes.ok) {
          throw new Error(`加载失败 (${profileRes.status}/${historyRes.status}/${roleRes.status})`);
        }
        const profileData = await profileRes.json();
        const historyData = await historyRes.json();
        const roleData = await roleRes.json();
        if (!cancelled) {
          setProfile(profileData);
          setHistory(historyData.items ?? []);
          setRole(roleData.summary ?? null);
        }
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : '加载失败');
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => { cancelled = true; };
  }, []);

  const renderContent = () => {
    if (loading) {
      return <div className="text-xs py-6 text-center" style={{ color: 'var(--text-muted)' }}>正在加载反馈画像…</div>;
    }
    if (error) {
      return <div className="text-xs py-6 text-center" style={{ color: 'var(--color-error)' }}>{error}</div>;
    }

    return (
      <div className="space-y-4">
        {/* 统计卡片 */}
        <div className="grid grid-cols-2 gap-2">
          <div className="p-3 rounded" style={{ border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-secondary)' }}>
            <div className="text-[10px] font-mono uppercase tracking-widest mb-1" style={{ color: 'var(--text-muted)' }}>点赞</div>
            <div className="text-xl font-bold" style={{ color: 'var(--color-success)' }}>{profile?.total_likes ?? 0}</div>
          </div>
          <div className="p-3 rounded" style={{ border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-secondary)' }}>
            <div className="text-[10px] font-mono uppercase tracking-widest mb-1" style={{ color: 'var(--text-muted)' }}>点踩</div>
            <div className="text-xl font-bold" style={{ color: 'var(--color-error)' }}>{profile?.total_dislikes ?? 0}</div>
          </div>
        </div>

        {/* 角色倾向总结 */}
        {role && (
          <div className="p-3 rounded" style={{ border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-secondary)' }}>
            <div className="text-[10px] font-mono uppercase tracking-widest mb-2" style={{ color: 'var(--accent)' }}>角色倾向总结</div>
            <p className="text-xs leading-relaxed mb-2" style={{ color: 'var(--text-primary)' }}>{role.summary}</p>
            <div className="flex flex-wrap gap-1 mb-2">
              {role.interests?.map((item) => (
                <span key={item} className="text-[10px] font-mono px-1.5 py-0.5 rounded" style={{ backgroundColor: 'color-mix(in srgb, var(--color-success) 15%, transparent)', color: 'var(--color-success)' }}>
                  {item}
                </span>
              ))}
            </div>
            <div className="flex flex-wrap gap-1 mb-2">
              {role.dislikes?.map((item) => (
                <span key={item} className="text-[10px] font-mono px-1.5 py-0.5 rounded" style={{ backgroundColor: 'color-mix(in srgb, var(--color-error) 15%, transparent)', color: 'var(--color-error)' }}>
                  {item}
                </span>
              ))}
            </div>
            <div className="text-[10px] font-mono" style={{ color: 'var(--text-muted)' }}>
              阅读风格: {role.reading_style} · 置信度: {Math.round((role.confidence ?? 0) * 100)}%
            </div>
          </div>
        )}

        {/* 反馈记录 */}
        <div>
          <div className="text-[10px] font-mono uppercase tracking-widest mb-2" style={{ color: 'var(--text-muted)' }}>最近记录</div>
          <div className="space-y-1">
            {history.length === 0 && (
              <div className="text-xs py-4 text-center" style={{ color: 'var(--text-muted)' }}>暂无反馈记录</div>
            )}
            {history.map((item) => (
              <div key={item.id} className="flex items-center gap-2 p-2 rounded text-[11px]" style={{ border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-secondary)' }}>
                <span className="shrink-0 font-mono" style={{ color: item.action === 'like' ? 'var(--color-success)' : 'var(--color-error)' }}>
                  {item.action === 'like' ? '👍' : '👎'}
                </span>
                <span className="flex-1 min-w-0 truncate" style={{ color: 'var(--text-primary)' }}>
                  {item.title || item.entity_id}
                </span>
                <span className="shrink-0 font-mono" style={{ color: 'var(--text-muted)' }}>
                  {item.category || '-'}
                </span>
                <span className="shrink-0 font-mono" style={{ color: 'var(--text-muted)' }}>
                  {new Date(item.created_at).toLocaleDateString('zh-CN')}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>
    );
  };

  return (
    <div className="space-y-2">
      <div className="text-sm font-bold tracking-wide" style={{ color: 'var(--text-primary)' }}>
        <span className="font-mono mr-2">♥</span>
        反馈画像
      </div>
      <div className="text-[10px] font-mono mb-2" style={{ color: 'var(--text-muted)' }}>
        你的点赞/点踩记录将用于生成个性化内容推荐与阅读风格总结。
      </div>
      {renderContent()}
    </div>
  );
}
