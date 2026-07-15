import React, { useState, useEffect } from 'react';
import type { SkillConfig } from '../types';
import { SkillConfigDialog } from './SkillConfigDialog';

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
  const [configSkillId, setConfigSkillId] = useState<number | null>(null);

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
          // 状态指示器：disabled 优先级最高
          const dotColor = !s.enabled ? '#e85d5d' : s.secret_id != null ? '#5cb85c' : '#888899';
          const dotLabel = !s.enabled ? '已禁用' : s.secret_id != null ? '已绑定' : '未绑定';
          return (
            <button
              key={s.id}
              onClick={() => setConfigSkillId(s.id)}
              className="flex flex-col items-center justify-center gap-0.5 p-1.5 rounded-[var(--radius-sm)] text-[10px]"
              style={{
                backgroundColor: 'var(--bg-hover)',
                color: 'var(--text-primary)',
                cursor: 'pointer',
                border: '1px solid transparent',
              }}
              title={s.skill_name}
            >
              <span className="text-sm">{icon}</span>
              <span className="truncate w-full text-center">{label}</span>
              <span className="flex items-center gap-0.5 text-[8px]" style={{ color: 'var(--text-muted)' }}>
                <span style={{ display: 'inline-block', width: '6px', height: '6px', borderRadius: '50%', backgroundColor: dotColor }} />
                {dotLabel}
              </span>
            </button>
          );
        })}
      </div>
      {skills.length === 0 && (
        <p className="text-[10px] mt-1" style={{ color: 'var(--text-muted)' }}>暂无 skill 配置</p>
      )}
      <SkillConfigDialog
        skill_id={configSkillId}
        onClose={() => setConfigSkillId(null)}
        onSaved={() => {
          fetch('/api/knowledge/skills')
            .then(r => r.json())
            .then(data => setSkills(data.skills || []))
            .catch(() => {});
        }}
      />
    </div>
  );
}
