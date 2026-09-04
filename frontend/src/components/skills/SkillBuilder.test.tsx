/**
 * SkillBuilder.test.tsx — v0.8 Phase C C4 测试套件 (≥8 case).
 *
 * 覆盖意图 (why):
 * - 4 步向导基础渲染 (StepHeader / step indicator)
 * - Step 1 基本信息: id/name 输入 + 校验 (下一步禁用)
 * - Step 2 Schema: 字段增删 + C/D 类 prompt 显隐
 * - Step 3 Target: dry-run validate 调 /validate
 * - Step 4 复核: JSON 预览
 * - 保存提交: POST /api/skill-builder + 错误信封展示
 *
 * 测试策略: vi.mock('../../lib/api') 与 SkillStore 同款 (P3-2 错误信封已提取 message).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { SkillBuilder } from './SkillBuilder';
import { postJSON } from '../../lib/api';

vi.mock('../../lib/api', () => ({
  apiFetch: vi.fn(),
  postJSON: vi.fn(),
}));

const onBack = vi.fn();
const onCreated = vi.fn();

beforeEach(() => {
  vi.clearAllMocks();
  onBack.mockClear();
  onCreated.mockClear();
});

describe('SkillBuilder', () => {
  it('renders step indicator with 4 steps and starts at step 1', () => {
    render(<SkillBuilder onBack={onBack} onCreated={onCreated} />);
    // 4 个步骤头
    for (let i = 1; i <= 4; i += 1) {
      expect(screen.getByTestId(`wizard-step-${i}`)).toBeInTheDocument();
    }
    // Step 1 表单 (基本信息)
    expect(screen.getByLabelText('skill id')).toBeInTheDocument();
    expect(screen.getByLabelText('skill 显示名')).toBeInTheDocument();
  });

  it('Step 1 disables 下一步 when id or name is empty', () => {
    render(<SkillBuilder onBack={onBack} onCreated={onCreated} />);
    // id 空 + name 空 → 下一步 disabled
    const nextBtn = screen.getByRole('button', { name: '下一步' });
    expect(nextBtn).toBeDisabled();

    // 填 id
    fireEvent.change(screen.getByLabelText('skill id'), {
      target: { value: 'my-skill-1' },
    });
    expect(nextBtn).toBeDisabled();

    // 填 name
    fireEvent.change(screen.getByLabelText('skill 显示名'), {
      target: { value: '我的技能' },
    });
    expect(nextBtn).toBeEnabled();
  });

  it('advances to Step 2 and shows schema editors + C/D prompt reveal', () => {
    render(<SkillBuilder onBack={onBack} onCreated={onCreated} />);
    // 切到 C 类 (在 Step 1, 下一步之前)
    const typeSelect = document.getElementById(
      'skill-builder-type'
    ) as HTMLSelectElement | null;
    expect(typeSelect).toBeTruthy();
    if (typeSelect) {
      fireEvent.change(typeSelect, { target: { value: 'C' } });
    }
    // 填好 Step 1 → 下一步
    fireEvent.change(screen.getByLabelText('skill id'), {
      target: { value: 'my-skill' },
    });
    fireEvent.change(screen.getByLabelText('skill 显示名'), {
      target: { value: 'X' },
    });
    fireEvent.click(screen.getByRole('button', { name: '下一步' }));

    // Step 2 schema 编辑器 (input_schema / output_schema 两个)
    expect(screen.getByTestId('input_schema-add')).toBeInTheDocument();
    expect(screen.getByTestId('output_schema-add')).toBeInTheDocument();

    // C 类出现 prompt 模板输入
    expect(screen.getByLabelText('prompt 模板')).toBeInTheDocument();
  });

  it('Step 2 disables 下一步 for C/D without prompt_template', () => {
    render(<SkillBuilder onBack={onBack} onCreated={onCreated} />);
    // 选 C 类 (Step 1)
    const typeSelect = document.getElementById(
      'skill-builder-type'
    ) as HTMLSelectElement | null;
    if (typeSelect) {
      fireEvent.change(typeSelect, { target: { value: 'C' } });
    }
    fireEvent.change(screen.getByLabelText('skill id'), {
      target: { value: 'c-skill' },
    });
    fireEvent.change(screen.getByLabelText('skill 显示名'), { target: { value: 'y' } });
    fireEvent.click(screen.getByRole('button', { name: '下一步' }));

    // prompt_template 空 → 下一步 disabled
    expect(screen.getByRole('button', { name: '下一步' })).toBeDisabled();

    // 填 prompt → enabled
    fireEvent.change(screen.getByLabelText('prompt 模板'), {
      target: { value: '基于 {{ input.x }} 生成报告' },
    });
    expect(screen.getByRole('button', { name: '下一步' })).toBeEnabled();
  });

  it('Step 3 dry-run validate posts to /api/skill-builder/validate', async () => {
    vi.mocked(postJSON).mockResolvedValueOnce({ ok: true, errors: [] });
    render(<SkillBuilder onBack={onBack} onCreated={onCreated} />);

    // 填到 Step 3
    fireEvent.change(screen.getByLabelText('skill id'), {
      target: { value: 'my-skill' },
    });
    fireEvent.change(screen.getByLabelText('skill 显示名'), { target: { value: 'X' } });
    fireEvent.click(screen.getByRole('button', { name: '下一步' }));
    fireEvent.click(screen.getByRole('button', { name: '下一步' }));

    // Step 3: 填 target
    fireEvent.change(screen.getByLabelText('target_module'), {
      target: { value: 'backend.services.source_scheduler_service' },
    });
    fireEvent.change(screen.getByLabelText('target_class'), {
      target: { value: 'SourceSchedulerService' },
    });
    fireEvent.change(screen.getByLabelText('target_method'), {
      target: { value: 'get_status' },
    });

    fireEvent.click(screen.getByRole('button', { name: 'dry-run validate' }));

    await waitFor(() => {
      expect(postJSON).toHaveBeenCalledWith(
        '/api/skill-builder/validate',
        expect.objectContaining({ payload: expect.any(Object) })
      );
    });
  });

  it('Step 4 shows JSON preview of draft', () => {
    render(<SkillBuilder onBack={onBack} onCreated={onCreated} />);
    fireEvent.change(document.getElementById('skill-builder-id')!, {
      target: { value: 'demo-skill' },
    });
    fireEvent.change(document.getElementById('skill-builder-name')!, {
      target: { value: 'Demo' },
    });
    fireEvent.click(screen.getByRole('button', { name: '下一步' }));
    // Step 2 → Step 3
    fireEvent.click(screen.getByRole('button', { name: '下一步' }));
    // Step 3: 填 target 否则下一步 disabled
    fireEvent.change(screen.getByLabelText('target_module'), {
      target: { value: 'backend.services.source_scheduler_service' },
    });
    fireEvent.change(screen.getByLabelText('target_method'), {
      target: { value: 'get_status' },
    });
    fireEvent.click(screen.getByRole('button', { name: '下一步' }));

    // Step 4 复核
    const preview = screen.getByTestId('skill-builder-yaml-preview');
    expect(preview.textContent).toContain('demo-skill');
    expect(preview.textContent).toContain('Demo');
  });

  it('submit posts to /api/skill-builder and calls onCreated', async () => {
    vi.mocked(postJSON).mockResolvedValueOnce({ id: 'created-skill' });
    render(<SkillBuilder onBack={onBack} onCreated={onCreated} />);
    fireEvent.change(document.getElementById('skill-builder-id')!, {
      target: { value: 'created-skill' },
    });
    fireEvent.change(document.getElementById('skill-builder-name')!, {
      target: { value: 'X' },
    });
    fireEvent.click(screen.getByRole('button', { name: '下一步' }));
    fireEvent.click(screen.getByRole('button', { name: '下一步' }));
    fireEvent.change(screen.getByLabelText('target_module'), {
      target: { value: 'backend.services.source_scheduler_service' },
    });
    fireEvent.change(screen.getByLabelText('target_method'), {
      target: { value: 'get_status' },
    });
    fireEvent.click(screen.getByRole('button', { name: '下一步' }));

    fireEvent.click(screen.getByRole('button', { name: '保存' }));

    await waitFor(() => {
      expect(postJSON).toHaveBeenCalledWith(
        '/api/skill-builder',
        expect.objectContaining({ id: 'created-skill' })
      );
    });
    expect(onCreated).toHaveBeenCalledWith('created-skill');
  });

  it('submit shows error envelope inline (validate_failed → 422)', async () => {
    vi.mocked(postJSON).mockRejectedValueOnce(new Error('user skill validate failed: id 太短'));
    render(<SkillBuilder onBack={onBack} onCreated={onCreated} />);
    fireEvent.change(document.getElementById('skill-builder-id')!, {
      target: { value: 'broken' },
    });
    fireEvent.change(document.getElementById('skill-builder-name')!, {
      target: { value: 'X' },
    });
    fireEvent.click(screen.getByRole('button', { name: '下一步' }));
    fireEvent.click(screen.getByRole('button', { name: '下一步' }));
    fireEvent.change(screen.getByLabelText('target_module'), {
      target: { value: 'backend.services.source_scheduler_service' },
    });
    fireEvent.change(screen.getByLabelText('target_method'), {
      target: { value: 'get_status' },
    });
    fireEvent.click(screen.getByRole('button', { name: '下一步' }));
    fireEvent.click(screen.getByRole('button', { name: '保存' }));

    const alert = await screen.findByTestId('skill-builder-errors');
    expect(alert.textContent).toContain('id 太短');
  });

  it('schema editor: add + remove fields updates input_schema', () => {
    render(<SkillBuilder onBack={onBack} onCreated={onCreated} />);
    fireEvent.change(document.getElementById('skill-builder-id')!, {
      target: { value: 'abc' },
    });
    fireEvent.change(document.getElementById('skill-builder-name')!, { target: { value: 'b' } });
    fireEvent.click(screen.getByRole('button', { name: '下一步' }));

    // 添加一个字段 (input_schema)
    fireEvent.click(screen.getByTestId('input_schema-add'));
    expect(screen.getByTestId('input_schema-field-name')).toBeInTheDocument();

    // 删字段
    fireEvent.click(screen.getByTestId(/^remove-field-/));
    expect(
      screen.queryByTestId('input_schema-field-name')
    ).not.toBeInTheDocument();
  });
});