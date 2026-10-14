// KnowledgeImport — C2 (DEV-0195) Cubox 兜底导入交互测试 (CLI 导出 JSON / 本地目录)
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { KnowledgeImport } from './KnowledgeImport';

const CARD = {
  title: '导入卡',
  url: 'https://example.com/import-1',
  description: '正文',
  tags: ['t'],
  create_time: '2026-09-16T00:00:00+00:00',
};

function makeFetch() {
  return vi.fn((input: RequestInfo | URL, _init?: RequestInit) => {
    const url = String(input);
    if (url.includes('/api/knowledge/cubox/import-cards')) {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ imported: 1, new: 1, merged: 0, skipped: 0 }),
      } as Response);
    }
    if (url.includes('/api/knowledge/cubox/import-dir')) {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ dir: '/x', files: 2, cards: 3, imported: 3, new: 3, merged: 0, skipped: 0, errors: [] }),
      } as Response);
    }
    return Promise.resolve({ ok: true, json: () => Promise.resolve({}) } as Response);
  });
}

describe('KnowledgeImport — Cubox 兜底导入 (C2/DEV-0195)', () => {
  let fetchMock: ReturnType<typeof makeFetch>;
  beforeEach(() => {
    fetchMock = makeFetch();
    vi.stubGlobal('fetch', fetchMock);
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('Cubox 卡片含两个兜底入口 (CLI 导出 JSON / 本地目录)', () => {
    render(<KnowledgeImport />);
    expect(screen.getByTestId('cubox-cli-import')).toBeInTheDocument();
    expect(screen.getByTestId('cubox-dir-import')).toBeInTheDocument();
    expect(screen.getByLabelText('cubox 导出目录路径')).toBeInTheDocument();
  });

  it('CLI 导出 JSON 导入: 读取文件 → POST {cards} → 成功 toast', async () => {
    render(<KnowledgeImport />);
    const input = screen.getByTestId('cubox-cli-file') as HTMLInputElement;
    const file = new File([JSON.stringify([CARD])], 'export.json', { type: 'application/json' });
    fireEvent.change(input, { target: { files: [file] } });
    await waitFor(() => expect(screen.getByText(/已导入 1 条/)).toBeInTheDocument());
    const post = fetchMock.mock.calls.find(c => String(c[0]).includes('/cubox/import-cards'));
    expect(post).toBeTruthy();
    expect(JSON.parse((post![1] as unknown as { body: string }).body).cards.length).toBe(1);
  });

  it('本地目录导入: 输入路径 → POST {path} → 成功 toast', async () => {
    render(<KnowledgeImport />);
    fireEvent.change(screen.getByLabelText('cubox 导出目录路径'), {
      target: { value: '/Users/me/cubox-export' },
    });
    fireEvent.click(screen.getByTestId('cubox-dir-import'));
    await waitFor(() => expect(screen.getByText(/目录导入完成: 3 卡 → 入库 3 条（新建 3 · 合并 0）/)).toBeInTheDocument());
    const post = fetchMock.mock.calls.find(c => String(c[0]).includes('/cubox/import-dir'));
    expect(JSON.parse((post![1] as unknown as { body: string }).body).path).toBe('/Users/me/cubox-export');
  });

  it('形状不符的 JSON → 显式错误 toast, 不发请求', async () => {
    render(<KnowledgeImport />);
    const input = screen.getByTestId('cubox-cli-file') as HTMLInputElement;
    const file = new File([JSON.stringify({ foo: 1 })], 'bad.json', { type: 'application/json' });
    fireEvent.change(input, { target: { files: [file] } });
    await waitFor(() => expect(screen.getByText(/文件形状不符/)).toBeInTheDocument());
    expect(fetchMock.mock.calls.some(c => String(c[0]).includes('/cubox/import-cards'))).toBe(false);
  });
});
