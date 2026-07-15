import React, { useState, useEffect } from 'react';
import type { SkillConfig } from '../types';

const SKILL_NAMES: Record<string, string> = {
  'baoyu-post-to-wechat': '微信发布',
  'baoyu-post-to-x': 'X 发布',
  'baoyu-post-to-weibo': '微博发布',
  'baoyu-slide-deck': '幻灯片',
  'baoyu-infographic': '信息图',
  'baoyu-cover-image': '封面图',
  'baoyu-translate': '翻译',
  'baoyu-markdown-to-html': 'MD转HTML',
  'baoyu-xhs-images': '小红书图',
  'baoyu-youtube-transcript': 'YT字幕',
  'baoyu-url-to-markdown': 'URL转MD',
  'baoyu-image-gen': 'AI绘图',
  'baoyu-compress-image': '图片压缩',
};

const SKILL_ICONS: Record<string, string> = {
  'baoyu-post-to-wechat': '💬',
  'baoyu-post-to-x': '🐦',
  'baoyu-post-to-weibo': '📣',
  'baoyu-slide-deck': '🎞',
  'baoyu-infographic': '📊',
  'baoyu-cover-image': '🖼',
  'baoyu-translate': '🌐',
  'baoyu-markdown-to-html': '⚙',
  'baoyu-xhs-images': '📸',
  'baoyu-youtube-transcript': '📜',
  'baoyu-url-to-markdown': '🔗',
  'baoyu-image-gen': '🎨',
  'baoyu-compress-image': '🗜',
};

export function SkillEntryGrid() {
  const [skills, setSkills] = useState<SkillConfig[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [runningSkill, setRunningSkill] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);

  useEffect(() => {
    fetch('/api/knowledge/skills')
      .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then(data => {
        setSkills(data.skills || []);
        setLoading(false);
      })
      .catch(e => {
        setError(e?.message || String(e));
        setLoading(false);
      });
  }, []);

  const handleRun = (skill: SkillConfig) => {
    if (!skill.enabled) return;
    setRunningSkill(skill.skill_name);
    fetch('/api/knowledge/tasks', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        task_type: 'execute_skill',
        params: { skill_name: skill.skill_name },
      }),
    })
      .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then(() => {
        const label = SKILL_NAMES[skill.skill_name] || skill.skill_name;
        setToast(`✓ ${label} 任务已创建`);
        setTimeout(() => setToast(null), 2500);
      })
      .catch(e => {
        setToast(`✗ 失败: ${e?.message || String(e)}`);
        setTimeout(() => setToast(null), 2500);
      })
      .finally(() => setRunningSkill(null));
  };

  if (loading) {
    return <p className="text-xs" style={{ color: 'var(--text-muted)' }}>加载中…</p>;
  }

  if (error) {
    return <p className="text-xs" style={{ color: '#e85d5d' }}>加载失败: {error}</p>;
  }

  return (
    <div>
      <div className="grid grid-cols-3 gap-1">
        {skills.map(s => {
          const label = SKILL_NAMES[s.skill_name] || s.skill_name;
          const icon = SKILL_ICONS[s.skill_name] || '🔧';
          const running = runningSkill === s.skill_name;
          return (
            <button
              key={s.id}
              onClick={() => handleRun(s)}
              disabled={!s.enabled || running}
              className="flex flex-col items-center justify-center gap-0.5 p-1.5 rounded-[var(--radius-sm)] text-[10px]"
              style={{
                backgroundColor: 'var(--bg-hover)',
                color: s.enabled ? 'var(--text-primary)' : 'var(--text-muted)',
                opacity: s.enabled ? 1 : 0.4,
                cursor: s.enabled ? 'pointer' : 'not-allowed',
                border: '1px solid transparent',
              }}
              title={s.skill_name}
            >
              <span className="text-sm">{running ? '⏳' : icon}</span>
              <span className="truncate w-full text-center">{label}</span>
            </button>
          );
        })}
      </div>
      {skills.length === 0 && (
        <p className="text-[10px] mt-1" style={{ color: 'var(--text-muted)' }}>暂无 skill 配置</p>
      )}
      {toast && (
        <p className="text-[10px] mt-2 p-1.5 rounded-[var(--radius-sm)]" style={{
          backgroundColor: 'var(--bg-hover)',
          color: toast.startsWith('✓') ? 'var(--color-ai)' : '#e85d5d',
        }}>
          {toast}
        </p>
      )}
    </div>
  );
}
