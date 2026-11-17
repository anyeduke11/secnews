/**
 * EChart — tree-shaken ECharts 入口（唯一允许 import echarts 的地方）。
 *
 * WHY 不用 `echarts-for-react` 默认导出:
 *   默认入口 `echarts-for-react` 硬编码 `import * as echarts from 'echarts'`
 *   → 全量 echarts (含 map/3D/所有 chart 类型) 进入 vendor chunk,
 *   gzip 后 ~384KB = 生产包体积的 52% (M-4 指标的主要贡献者)。
 *   `echarts-for-react/lib/core` 不引全量 echarts, 允许注入自定义实例,
 *   于是这里用 echarts 官方 tree-shaking 入口 (`echarts/core` + 按需 `use()`)
 *   只注册本项目实际用到的 chart / component / renderer。
 *
 * 注册面 = 全仓实际用到的集合 (加新图必须同步这里, 否则运行时缺件):
 *   charts     : gauge (MasteryGauge) · graph (KnowledgeGraph) · line/bar (复利仪表盘)
 *   components : grid · tooltip · legend (复利仪表盘) · tooltip (KnowledgeGraph)
 *   renderer   : CanvasRenderer
 *
 * 改这里的注册面时, 必须同步验证:
 *   npx tsc --noEmit && npx vitest run && npx vite build --logLevel error
 *   并确认 dist gzip 总量 (M-4 指标) 未回升。
 */
import ReactEChartsCore from 'echarts-for-react/lib/core';
import * as echarts from 'echarts/core';
import { BarChart, GaugeChart, GraphChart, LineChart } from 'echarts/charts';
import {
  GridComponent,
  LegendComponent,
  TitleComponent,
  TooltipComponent,
} from 'echarts/components';
import { LabelLayout } from 'echarts/features';
import { CanvasRenderer } from 'echarts/renderers';

echarts.use([
  // charts
  BarChart,
  GaugeChart,
  GraphChart,
  LineChart,
  // components
  GridComponent,
  LegendComponent,
  TitleComponent,
  TooltipComponent,
  // features
  LabelLayout,
  // renderer
  CanvasRenderer,
]);

/**
 * 已注册的 tree-shaken echarts 实例 (导出供注册面完整性守卫测试引用 ——
 * 守卫必须测**生产这份注册面**, 不能另建一套注册, 否则测不到真实缺件)。
 */
export { echarts };

export type EChartProps = React.ComponentProps<typeof ReactEChartsCore>;

/**
 * 极薄封装: 注入 tree-shaken echarts 实例, 其余 props 透传给 core 组件。
 */
export function EChart(props: EChartProps) {
  return <ReactEChartsCore echarts={echarts} {...props} />;
}

export default EChart;
