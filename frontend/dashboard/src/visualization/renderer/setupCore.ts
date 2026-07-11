import { init, registerTheme, use, type EChartsType } from 'echarts/core';
import { SVGRenderer } from 'echarts/renderers';

import { trackerVisualizationTheme, trackerVisualizationThemeName } from './theme';

use([SVGRenderer]);
registerTheme(trackerVisualizationThemeName, trackerVisualizationTheme);

export { init, trackerVisualizationThemeName };
export type { EChartsType };
