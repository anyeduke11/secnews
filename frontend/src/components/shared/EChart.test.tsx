/**
 * EChart 注册面完整性守卫 (v0.8.9 M-4).
 *
 * WHY 需要这个测试:
 *   echarts 改 tree-shaking 入口后, 未注册的 chart / component 不会报错于
 *   build 期, 只在**运行时**缺件 —— echarts dev 模式对缺失 series 断言
 *   "xxx does not exist", 生产模式则直接不渲染该 series。
 *   → 若将来新增图表类型却忘了在 shared/EChart.tsx 注册, 表现为「图表空白」,
 *   没有编译错误也没有既有测试失败, 属最难发现的一类回归。
 *
 * 本测试:
 *   ① 直接引用**生产注册面** (shared/EChart.tsx 导出的 echarts 实例),
 *      不另建注册 —— 否则测不到真实缺件;
 *   ② 用真实 echarts 实例跑三份生产 option, 断言 setOption 不抛错
 *      (缺注册的 series 会在 setOption 阶段触发 echarts 断言)。
 *
 * 覆盖的三份 option = 全仓实际使用 echarts 的三处 (缺一即视为新增图表未登记):
 *   MasteryGauge (gauge) · KnowledgeGraph (graph) · KnowledgeCompoundingDashboard (line + bar)
 *
 * renderer 说明: 生产用 CanvasRenderer, 但 jsdom 无 canvas 2d 实现, zrender 画布
 * 绘制会异步崩 (clearRect of null) —— 与注册面无关。故测试额外注册 SVGRenderer
 * 并以 'svg' 渲染; 断言的是 chart/component 注册面, 不是渲染后端。
 *
 * 断言方式说明 (为何捕获 console.error 而非 not.toThrow):
 *   echarts 遇到未注册的 series 时走 lib/model/global.js 的缺件分支 ——
 *   `error("Series gauge is used but not imported...")` 然后**静默跳过该 series**,
 *   既不抛异常也不产生任何 view (图表直接空白)。故必须捕获 console.error
 *   才能发现缺件; 只断言 not.toThrow 的测试在缺件时照样通过 (已消融验证)。
 */
import { describe, it, expect, vi } from 'vitest';
import { render } from '@testing-library/react';
import { echarts, EChart } from './EChart';
import { SVGRenderer } from 'echarts/renderers';
import type { EChartsType } from 'echarts';

// jsdom 无 canvas 2d → 测试用 SVG 渲染后端 (见文件头说明)
echarts.use([SVGRenderer]);

function makeInstance(): EChartsType {
  const el = document.createElement('div');
  el.style.width = '400px';
  el.style.height = '300px';
  document.body.appendChild(el);
  return echarts.init(el, undefined, { renderer: 'svg' });
}

/**
 * 跑一段 setOption, 返回期间 echarts 打到 console.error 的缺件消息。
 * 空数组 = 该 option 的所有 series/component 都已注册。
 */
function setOptionCapturingErrors(option: Record<string, unknown>): string[] {
  const errors: string[] = [];
  const spy = vi.spyOn(console, 'error').mockImplementation((...args: unknown[]) => {
    errors.push(args.map(String).join(' '));
  });
  const inst = makeInstance();
  try {
    inst.setOption(option);
  } finally {
    inst.dispose();
    spy.mockRestore();
  }
  return errors.filter((e) => /is used but not imported|does not exist|Unknown series/.test(e));
}

describe('EChart tree-shaking 注册面完整性', () => {
  it('gauge: MasteryGauge 的 option 无缺件 (缺注册 → "Series gauge is used but not imported")', () => {
    const errors = setOptionCapturingErrors({
      series: [{
        type: 'gauge',
        radius: '90%',
        min: 0,
        max: 100,
        progress: { show: true, width: 10 },
        pointer: { show: false },
        axisTick: { show: false },
        splitLine: { show: false },
        axisLabel: { show: false },
        detail: { valueAnimation: true, formatter: '{value}%' },
        data: [{ value: 42 }],
      }],
    });
    expect(errors).toEqual([]);
  });

  it('graph: KnowledgeGraph 的 force layout option 无缺件', () => {
    const errors = setOptionCapturingErrors({
      tooltip: { formatter: (p: any) => `${p.data?.name}` },
      series: [{
        type: 'graph',
        layout: 'force',
        roam: true,
        draggable: true,
        force: { repulsion: 100, edgeLength: 80, gravity: 0.1 },
        label: { show: true, position: 'right' },
        data: [{ id: 'n1', name: 'A', value: 3, symbolSize: 20 }],
        edges: [{ source: 'n1', target: 'n1' }],
      }],
    });
    expect(errors).toEqual([]);
  });

  it('line + bar: 复利仪表盘的 grid/tooltip/legend option 无缺件', () => {
    const trendErrors = setOptionCapturingErrors({
      grid: { top: 12, left: 32, right: 36, bottom: 30 },
      xAxis: { type: 'category', data: ['07-28', '07-29'] },
      yAxis: [
        { type: 'value' },
        { type: 'value', min: 0, max: 1 },
      ],
      tooltip: { trigger: 'axis' },
      legend: { bottom: 0, icon: 'roundRect' },
      series: [
        { type: 'line', name: '条目数', smooth: true, data: [5, 8] },
        { type: 'line', name: '平均掌握度', yAxisIndex: 1, smooth: true, data: [0.6, 0.7] },
      ],
    });
    expect(trendErrors).toEqual([]);

    const stageErrors = setOptionCapturingErrors({
      grid: { top: 4, left: 70, right: 16, bottom: 24 },
      xAxis: { type: 'value' },
      yAxis: { type: 'category', data: ['raw', 'refine'] },
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
      series: [{ type: 'bar', name: '条目数', barMaxWidth: 20, data: [3, 7] }],
    });
    expect(stageErrors).toEqual([]);
  });

  it('组件路径: EChart 渲染出容器并完成一次真实 init (不只 setOption)', () => {
    // WHY: setOption 断言只覆盖注册面; 这一条覆盖**组件接线** ——
    // 注入的实例是否真被 echarts-for-react/lib/core 接受 (注入错实例时
    // 组件会渲染空 div 而不报错, 属静默失效)。
    const errors: string[] = [];
    const spy = vi.spyOn(console, 'error').mockImplementation((...args: unknown[]) => {
      errors.push(args.map(String).join(' '));
    });
    try {
      const { container } = render(
        <EChart
          option={{ series: [{ type: 'gauge', data: [{ value: 42 }] }] }}
          style={{ height: '140px', width: '100%' }}
        />,
      );
      // 容器存在 = 组件已挂载并进入 echarts init 流程
      expect(container.querySelector('div')).not.toBeNull();
    } finally {
      spy.mockRestore();
    }
    expect(errors.filter((e) => /is used but not imported|does not exist/.test(e))).toEqual([]);
  });
});
