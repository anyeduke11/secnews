/**
 * chunk_attrib.mjs — 首屏 chunk 逐字节归因（sourcemap VLQ 解码）
 *
 * 用途: 把某个 chunk 的产物字节按「源文件」归因, 回答"钱花在哪"。
 *   node perf/chunk_attrib.mjs                # 归因首屏 3 chunk
 *   node perf/chunk_attrib.mjs <chunkFileName> # 归因指定 chunk
 *
 * 口径: raw = 未压缩字节; gzip = 该源文件独立 gzip 后的近似体积。
 *   ⚠️ gzip 列是「独立压缩」近似值, 不是 chunk 内真实占比 (gzip 对重复文本
 *      几乎免费, 见 DEV-0396 结论), 决策请以 raw 列为准。
 *
 * 需先构建带 sourcemap:
 *   npx vite build --sourcemap
 */
import { readFileSync, readdirSync, existsSync } from 'node:fs'
import { gzipSync } from 'node:zlib'
import { join } from 'node:path'

const DIST = new URL('../dist/', import.meta.url).pathname
const ASSETS = join(DIST, 'assets')

const B64 = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/'

/** sourcemap mappings 段 → { sourceIdx, genLine, genCol } 列表 */
function decodeMappings(mappings) {
  const out = []
  let sourceIdx = 0
  let srcLine = 0
  let srcCol = 0
  let genLine = 0
  let genCol = 0

  for (const seg of mappings.split(';')) {
    if (seg) {
      const fields = seg.split(',')
      genCol = 0
      for (const f of fields) {
        const [v, s, l, o] = decodeVLQ(f)
        genCol += v
        if (s !== undefined) {
          sourceIdx += s
          srcLine += l
          srcCol += o
          out.push({ sourceIdx, genLine, genCol })
        }
      }
    }
    genLine++
  }
  return out
}

function decodeVLQ(str) {
  const res = []
  let shift = 0
  let value = 0
  for (const ch of str) {
    const digit = B64.indexOf(ch)
    if (digit === -1) throw new Error(`bad base64 char: ${ch}`)
    const cont = digit & 32
    value += (digit & 31) << shift
    if (cont) {
      shift += 5
    } else {
      const neg = value & 1
      value >>= 1
      res.push(neg ? (value === 0 ? -0x80000000 : -value) : value)
      value = 0
      shift = 0
    }
  }
  return res
}

/** chunk 内容 → { 源文件: raw 字节 } */
function attributeChunk(chunkFile) {
  const code = readFileSync(join(ASSETS, chunkFile), 'utf8')
  const mapFile = chunkFile + '.map'
  if (!existsSync(join(ASSETS, mapFile))) {
    throw new Error(`缺 sourcemap: ${mapFile} —— 先跑 npx vite build --sourcemap`)
  }
  const map = JSON.parse(readFileSync(join(ASSETS, mapFile), 'utf8'))
  const segs = decodeMappings(map.mappings)
  const lines = code.split('\n')

  // ⚠️ 产物已 minify: 整块常只有 1–3 行, **行级归因无效**（会把整 chunk
  // 记给第一个 source）。必须按 genCol 区间切: 同一行内, 一个 segment 从
  // 它的 genCol 起, 到下一个 segment 的 genCol 止, 都属于它的 source。
  const byLine = new Map()
  for (const s of segs) {
    if (!byLine.has(s.genLine)) byLine.set(s.genLine, [])
    byLine.get(s.genLine).push(s)
  }

  const bySource = new Map()
  for (const [genLine, lineSegs] of byLine) {
    const line = lines[genLine] ?? ''
    lineSegs.sort((a, b) => a.genCol - b.genCol)
    for (let i = 0; i < lineSegs.length; i++) {
      const cur = lineSegs[i]
      const next = lineSegs[i + 1]
      const start = cur.genCol
      const end = next ? next.genCol : line.length
      const raw = Math.max(0, end - start)
      const src = map.sources[cur.sourceIdx] ?? '(unknown)'
      bySource.set(src, (bySource.get(src) ?? 0) + raw)
    }
  }
  return bySource
}

function gzipSize(text) {
  return gzipSync(Buffer.from(text), { level: 6 }).length
}

function fmt(n) {
  return String(n).padStart(8)
}

// ---- 主流程 ----
const all = readdirSync(ASSETS)
const target = process.argv[2]
  ? [process.argv[2]]
  : (() => {
      const html = readFileSync(join(DIST, 'index.html'), 'utf8')
      const entry = all.find((f) => html.includes(f) && /^index-.*\.js$/.test(f))
      const react = all.find((f) => /^vendor-react-.*\.js$/.test(f))
      const home = all.find((f) => /^SentinelHomePage-.*\.js$/.test(f))
      return [entry, react, home].filter(Boolean)
    })()

for (const chunk of target) {
  const bySource = attributeChunk(chunk)
  const total = [...bySource.values()].reduce((a, b) => a + b, 0)
  const rows = [...bySource.entries()].sort((a, b) => b[1] - a[1])
  console.log(`\n════ ${chunk}  raw 归因 (总 ${total} B) ════`)
  console.log(`${fmt('raw')}${fmt('gzip~')}${fmt('%')}  source`)
  for (const [src, raw] of rows) {
    if (raw < 200) continue
    const pct = ((raw / total) * 100).toFixed(1)
    console.log(`${fmt(raw)}${fmt(gzipSize(src))}${fmt(pct + '%')}  ${src}`)
  }
  console.log(`\n  chunk 文件 gzip 实测: ${gzipSize(readFileSync(join(ASSETS, chunk), 'utf8'))} B`)
}
