export const trackerVisualizationThemeName = 'codex-usage-tracker';

export const trackerVisualizationPalette = {
  canvas: '#f6f7f9',
  panel: '#ffffff',
  ink: '#18202a',
  mutedInk: '#5c6675',
  line: '#d9dee7',
  lineStrong: '#aeb7c5',
  selection: '#2f6fed',
  selectionSoft: '#9db9f6',
  positive: '#16866b',
  caution: '#9a5900',
  risk: '#c84652',
  context: '#7651c9',
} as const;

export const trackerVisualizationTheme = {
  color: [
    trackerVisualizationPalette.selection,
    trackerVisualizationPalette.positive,
    trackerVisualizationPalette.context,
    trackerVisualizationPalette.caution,
    trackerVisualizationPalette.risk,
    trackerVisualizationPalette.mutedInk,
  ],
  backgroundColor: 'transparent',
  textStyle: {
    color: trackerVisualizationPalette.ink,
    fontFamily: 'system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
  },
  categoryAxis: {
    axisLine: { lineStyle: { color: trackerVisualizationPalette.lineStrong } },
    axisTick: { show: false },
    axisLabel: { color: trackerVisualizationPalette.mutedInk },
    splitLine: { show: false },
  },
  valueAxis: {
    axisLine: { show: false },
    axisTick: { show: false },
    axisLabel: { color: trackerVisualizationPalette.mutedInk },
    splitLine: { lineStyle: { color: trackerVisualizationPalette.line, type: 'dashed' } },
  },
  timeAxis: {
    axisLine: { lineStyle: { color: trackerVisualizationPalette.lineStrong } },
    axisTick: { show: false },
    axisLabel: { color: trackerVisualizationPalette.mutedInk },
    splitLine: { show: false },
  },
  legend: { textStyle: { color: trackerVisualizationPalette.mutedInk } },
  tooltip: {
    backgroundColor: trackerVisualizationPalette.ink,
    borderWidth: 0,
    textStyle: { color: trackerVisualizationPalette.panel },
  },
};
