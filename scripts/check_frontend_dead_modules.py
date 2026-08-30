"""从路由入口做 import 传递闭包, 找出真正不可达的前端源文件 (只读分析)。

两个曾经导致误判的坑, 本脚本已修:
  1. resolve() 必须 .resolve() 归一化 "..", 否则跨目录引用与 rglob 的规范路径
     永不相等 (曾把 117 个在用文件判成死码)。
  2. 入口提取必须支持**目录导入** (`import('../components/sync')` → index.tsx),
     否则整棵 sync/ 子树会被误判不可达。
"""
import re
import pathlib

SRC = pathlib.Path('frontend/src').resolve()
IMP = re.compile(r"""(?:from|import)\s+(?:[\w{},*\s]+\s+from\s+)?['"]([^'"]+)['"]""")
DYN = re.compile(r"""import\(\s*['"]([^'"]+)['"]""")


def resolve(spec, frm):
    if spec.startswith('.'):
        base = (frm.parent / spec).resolve()
    elif spec.startswith('@/'):
        base = (SRC / spec[2:]).resolve()
    else:
        return None
    for cand in (base.with_suffix('.tsx'), base.with_suffix('.ts'),
                 base / 'index.tsx', base / 'index.ts'):
        if cand.is_file():
            return cand.resolve()
    return None


def closure(roots):
    seen, stack = set(), list(roots)
    while stack:
        f = stack.pop()
        if f in seen:
            continue
        seen.add(f)
        try:
            text = f.read_text(encoding='utf-8')
        except Exception:
            continue
        specs = IMP.findall(text) + DYN.findall(text)
        for spec in specs:
            if spec.endswith('.css') or spec.startswith(('react', 'vitest', '@testing')):
                continue
            r = resolve(spec, f)
            if r:
                stack.append(r)
    return seen


roots = {SRC / 'App.tsx', SRC / 'main.tsx'}
# routes/ 全部文件 + 测试配置入口 (vitest setup 不是应用代码, 但绝不能被当死码)
for f in (SRC / 'routes').glob('*.ts*'):
    if '.test.' not in f.name:
        roots.add(f.resolve())
li = (SRC / 'routes/lazy-imports.ts').read_text(encoding='utf-8')
for spec in DYN.findall(li):
    r = resolve(spec, SRC / 'routes/lazy-imports.ts')
    if r:
        roots.add(r)

live = closure(roots)
allsrc = {f.resolve() for f in SRC.rglob('*.ts*')
          if '.test.' not in f.name and not str(f).startswith('test/')}
# vitest setup / 类型声明入口视为常驻
allsrc -= {p.resolve() for p in (SRC / 'test').rglob('*.ts*')}

dead = sorted(allsrc - live)
print(f'入口 {len(roots)} | 源文件 {len(allsrc)} | 可达 {len(live & allsrc)} | 不可达 {len(dead)}\n')
for f in dead:
    print('  ', f.relative_to(SRC))
