import type { EChartsCoreOption } from 'echarts/core';

export type VisualizationSelectionTarget = {
  seriesIndex: number;
  dataIndex: number;
  dataType?: 'edge' | 'node';
};

export type EChartsVisualizationModel = {
  option: EChartsCoreOption;
  targetByKey: Map<string, VisualizationSelectionTarget>;
  keyByTarget: Map<string, string>;
};
