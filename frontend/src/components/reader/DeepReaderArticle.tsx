/**
 * DeepReaderArticle — 清样正文区 (标题 / 元信息 / markdown 子集) 展示区块
 * (B5.6 拆分: 从 DeepReaderPage 抽出)
 *
 * DOM 结构与内联 style 逐字保留, 仅由容器传入标题/元信息/批注区间。
 */
import { Markdownish } from './DeepReaderMarkdown';
import type { BodyRange } from './deepReaderModel';

export function DeepReaderArticle({
  title,
  path,
  size,
  body,
  ranges,
  articleRef,
  onMouseUp,
}: {
  title: string;
  path: string | undefined;
  size: number | undefined;
  body: string;
  ranges: BodyRange[];
  articleRef: React.MutableRefObject<HTMLElement | null>;
  onMouseUp: () => void;
}) {
  return (
    <article
      ref={articleRef}
      className="ed-reader"
      onMouseUp={onMouseUp}
    >
      <h1>{title}</h1>
      <div className="ed-reader-meta">
        <span>{path}</span>
        {size ? <span>{(size / 1024).toFixed(1)} KB</span> : null}
      </div>
      <Markdownish body={body} ranges={ranges} />
    </article>
  );
}
