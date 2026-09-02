/**
 * settings/FeedbackSettings — 点赞/点踩记录 + 角色倾向总结 (V2 哨兵化)
 *
 * v0.7.x SettingsHub V2: st-section + st-cellgrid + st-chip + st-table
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

  return (
    <div className="space-y-3" data-testid="feedback-settings">
      <section className="st-section" aria-label="统计">
        <h3>反馈画像</h3>
        <p className="st-section-desc">
          你的点赞/点踩记录将用于生成个性化内容推荐与阅读风格总结。
        </p>
        <div className="st-section-body">
          {loading && <p className="st-cellnote">正在加载反馈画像…</p>}
          {error && <p className="st-info bad">{error}</p>}
          {!loading && !error && (
            <div className="st-cellgrid">
              <div className="st-cell">
                <span className="st-cellk">LIKES</span>
                <span className="st-cellv mint">{profile?.total_likes ?? 0}</span>
              </div>
              <div className="st-cell">
                <span className="st-cellk">DISLIKES</span>
                <span className="st-cellv red">{profile?.total_dislikes ?? 0}</span>
              </div>
            </div>
          )}
        </div>
      </section>

      {!loading && !error && role && (
        <section className="st-section" aria-label="角色倾向">
          <h3>角色倾向总结</h3>
          <p className="st-section-desc">
            阅读风格: {role.reading_style} · 置信度: {Math.round((role.confidence ?? 0) * 100)}%
          </p>
          <div className="st-section-body">
            <p className="st-cellnote" style={{ color: 'var(--sn-ink)', lineHeight: 1.5 }}>
              {role.summary}
            </p>
            <div className="st-ctrlrow" style={{ gap: 6 }}>
              {role.interests?.map((item) => (
                <span key={item} className="st-chip ok"><i aria-hidden />{item}</span>
              ))}
              {role.dislikes?.map((item) => (
                <span key={item} className="st-chip bad"><i aria-hidden />{item}</span>
              ))}
            </div>
          </div>
        </section>
      )}

      {!loading && !error && (
        <section className="st-section" aria-label="最近记录">
          <h3>最近记录 ({history.length})</h3>
          {history.length === 0 ? (
            <p className="st-cellnote">暂无反馈记录</p>
          ) : (
            <table className="st-table" aria-label="反馈记录">
              <thead>
                <tr>
                  <th style={{ width: 36 }}>反应</th>
                  <th>标题</th>
                  <th>分类</th>
                  <th>日期</th>
                </tr>
              </thead>
              <tbody>
                {history.map((item) => (
                  <tr key={item.id} className={item.action === 'like' ? '' : 'is-warn'}>
                    <td style={{ color: item.action === 'like' ? 'var(--sn-mint)' : 'var(--sn-red)' }}>
                      {item.action === 'like' ? '👍' : '👎'}
                    </td>
                    <td>
                      <span className="st-nm">{item.title || item.entity_id}</span>
                    </td>
                    <td>{item.category || '—'}</td>
                    <td>{new Date(item.created_at).toLocaleDateString('zh-CN')}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      )}
    </div>
  );
}

export default FeedbackSettings;