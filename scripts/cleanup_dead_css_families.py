"""删除本次 #5 组件清理所遗留的死 CSS 家族 (index.css)。

只删「其 TSX 消费者刚在本轮被删除、因此可证明由本次改动造成孤儿」的选择器;
不清理 .delay-* —— grep className 模板拼接后发现唯一动态家族是
`HotspotCard.tsx:33` 的 `delay-${i}`, .stagger-enter / .animate-* 均无拼接证据,
故 .stagger-enter 可删而 .delay-* 保留。也不清理 --layer-* 令牌与 .layer-card /
.editorial-input / .agihunt-card-star (哨兵六屏仍在用)。

选择器清单由 check_frontend_dead_modules 的同批删除结果人工圈定。
"""
from __future__ import annotations

import pathlib
import re
import sys

CSS = pathlib.Path('frontend/src/index.css')

# 本轮删除的组件所遗留的样式家族
DROP_PREFIXES = (
    'lead-story',          # LeadStory.tsx
    'hotspot-grid',        # HotspotGrid.tsx
    'stats-bar',           # StatsPanel.tsx (含 .stats-bars / .stats-bar-row ...)
    'cluster-badge',       # 聚类徽章 (旧 Feed)
    'flow-action',         # 跨层操作按钮 (旧 LayerCard/action)
    'loading-skeleton',    # LoadingSkeleton.tsx
    'empty-state',         # 旧空态 (现役空态用别的类)
    'cat-pill',            # CategoryNav.tsx
    'time-toggle',         # 旧时间切换
    'stat-card',           # 旧统计卡
    'accent-bar',          # 装饰条
    'corner-brackets',     # 装饰角
    'tech-divider',        # 旧分隔线
    'tech-drawer',         # 旧抽屉
    'editorial-divider',   # 旧分隔线
    'editorial-select',    # 旧下拉 (注意: .editorial-input 已因 URL 导入复活, 不删)
    'masthead-title',      # 旧报头 (Header.tsx 已删)
    'nav-group',           # 旧导航分组
    'pulse-dot',           # 旧脉冲点
    'btn-accent',          # 旧按钮变体
    'layer-dot',           # 旧三层点标
    'layer-header-accent', # layout/LayerHeader.tsx
    'layer-section-gap',   # 旧三层间距
    'section-gap',         # 旧间距工具
    # 不含 'feed-' —— 零引用清单只有 .feed-actions; .feed-row/.feed-title 被活组件
    #   KnowledgeFavoritesView.tsx:132,145 使用, 前缀匹配会过度删除 (实测踩过)。
    'stagger-enter',       # 无引用且无模板拼接证据 (拼接只有 .delay-*)
)
# 特例: 这些子元素属于 .agihunt-card-* 家族, 其基类与 -star 仍被哨兵首页使用
AGIHUNT_DROP = (
    'agihunt-card-grid', 'agihunt-card-header', 'agihunt-card-badge',
    'agihunt-card-time', 'agihunt-card-title', 'agihunt-card-summary',
    'agihunt-card-footer', 'agihunt-card-meta', 'agihunt-card-source',
    'agihunt-card-actions', 'agihunt-card-link',
)

PROTECT = ('agihunt-card', 'agihunt-card-star', 'editorial-input', 'editorial-badge',
           'layer-card', 'card-base', 'sticky-header')


def main() -> int:
    if not CSS.is_file():
        print('index.css 不存在', file=sys.stderr)
        return 2
    before = CSS.read_text(encoding='utf-8')
    drop = set(DROP_PREFIXES) | set(AGIHUNT_DROP)

    # 状态/修饰类不算"活的证据": 否则基类被删后 .x.active 会作为悬空规则留下
    # (实测漏网: .cat-pill.active, .time-toggle button.active)
    modifiers = {
        'active', 'open', 'disabled', 'checked', 'expanded', 'on', 'off',
        'warm', 'dead', 'ok', 'big', 'small', 'compact', 'is-open', 'no-hover',
    }

    def dead_selector(sel: str) -> bool:
        names = [
            n for n in re.findall(r'\.([a-zA-Z][a-zA-Z0-9_-]*)', sel)
            if n not in modifiers
        ]
        if not names:
            return False
        for n in names:
            if n in PROTECT:
                return False
            if not any(n == d or n.startswith(d) for d in drop):
                return False
        return True

    # `selector { body }`; body 不含花括号即可 —— @media 内的子规则会被当独立块捕获。
    block_re = re.compile(r'(?P<sel>[^{}@;/]+?)\{(?P<body>[^{}]*)\}', re.S)
    removed: list[str] = []

    def repl(m: re.Match) -> str:
        sel = m.group('sel')
        if dead_selector(sel):
            removed.append(' '.join(sel.split()))
            return ''
        return m.group(0)

    text = block_re.sub(repl, before)
    text = re.sub(r'@media[^{}]*\{\s*\}', '', text)   # 被掏空的 @media 壳
    text = re.sub(r'\n{3,}', '\n\n', text)

    if '--apply' in sys.argv:
        CSS.write_text(text, encoding='utf-8')
    print(f'移除规则块: {len(removed)} 条 | 行数 {len(before.splitlines())} -> {len(text.splitlines())}')
    for s in removed[:10]:
        print('   -', s[:78])
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
