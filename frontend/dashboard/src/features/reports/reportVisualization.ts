import type { BarDatum, CallRow, DashboardModel, Series } from '../../api/types';
import {
  visualizationSpecSchema,
  type CartesianSeriesSpec,
  type CartesianVisualizationSpecV1,
  type VisualizationRecord,
  type VisualizationTableColumn,
  type VisualizationUnit,
} from '../../visualization';
import {
  reportBarData,
  reportDetails,
  reportKey,
  reportLineSeries,
  type ReportView,
} from './reportModel';

type ReportVisualizationMetadata = {
  generatedAt: string;
  historyScope: 'active' | 'all';
  source: string;
  sourceRevision: string;
};

export function buildReportVisualizationSpec(
  report: ReportView | undefined,
  model: DashboardModel,
  calls: CallRow[],
  metadata: ReportVisualizationMetadata,
): CartesianVisualizationSpecV1 {
  const details = reportDetails(report, calls);
  const unit = visualizationUnit(details.chartLabel);
  const barData = reportBarData(report, model, calls);
  const visual = barData
    ? barVisualization(barData.bars, unit, details.chartLabel, barData.labelsAreUiText)
    : lineVisualization(reportLineSeries(report, model), unit, details.chartLabel);
  const title = report?.title ?? 'Selected report';
  const visualizationTitle = `${details.eyebrow} evidence`;

  return {
    schema: visualizationSpecSchema,
    id: `report-${reportKey(report)}`,
    title: visualizationTitle,
    description: details.selection,
    state: visual.rows.length
      ? { kind: 'ready' }
      : { kind: 'empty', message: `No loaded aggregate data is available for ${title}.` },
    scope: {
      label: `${metadata.source} · ${details.selection}`,
      rowCount: visual.rows.length,
      historyScope: metadata.historyScope,
    },
    freshness: {
      generatedAt: metadata.generatedAt,
      sourceRevision: metadata.sourceRevision,
    },
    caveats: [details.caveat, 'Raw context is available only through an explicitly linked Call Investigator record.'],
    accessibility: {
      summary: visual.rows.length
        ? `${title} contains ${visual.rows.length} plotted rows. ${details.finding}`
        : `No plotted rows are available for ${title}.`,
      details: [details.method, details.caveat],
      keyboardInstructions: 'Use left and right arrow keys to inspect chart values, or switch to the table for exact values.',
    },
    table: {
      caption: `${title} report data`,
      columns: visual.columns,
      defaultSort: { field: 'label', direction: 'asc' },
    },
    interactions: {
      selection: { keyField: 'id', labelField: 'label' },
      ...(barData ? {} : {
        zoom: {
          axis: 'x' as const,
          startPercent: visual.rows.length > 12 ? Math.round(100 - (12 / visual.rows.length) * 100) : 0,
          endPercent: 100,
        },
        brush: { axis: 'x' as const },
      }),
    },
    kind: 'cartesian',
    data: { rows: visual.rows },
    axes: {
      x: { field: 'label', label: barData ? 'Category' : 'Observed period', type: 'category' },
      y: { field: visual.series[0]?.yField ?? 'value', label: details.chartLabel, type: 'number', unit },
    },
    series: visual.series,
  };
}

function barVisualization(
  bars: BarDatum[],
  unit: VisualizationUnit,
  label: string,
  labelsAreUiText: boolean,
) {
  const rows: VisualizationRecord[] = bars.map((bar, index) => ({
    id: `bar-${index}`,
    label: bar.label,
    value: bar.value,
  }));
  return {
    rows,
    columns: [
      {
        field: 'label',
        label: 'Category',
        type: 'category' as const,
        align: 'left' as const,
        localizeValues: labelsAreUiText,
      },
      { field: 'value', label, type: 'number' as const, unit, align: 'right' as const },
    ],
    series: [{
      id: 'report-values',
      label,
      mark: 'bar' as const,
      xField: 'label',
      yField: 'value',
      color: '#2f6fed',
    }],
  };
}

function lineVisualization(series: Series[], unit: VisualizationUnit, fallbackLabel: string) {
  const rowsByLabel = new Map<string, Record<string, string | number>>();
  const chartSeries: CartesianSeriesSpec[] = [];
  const columns: VisualizationTableColumn[] = [
    { field: 'label', label: 'Observed period', type: 'category', align: 'left' },
  ];

  series.forEach((entry, seriesIndex) => {
    const valueField = `value_${seriesIndex}`;
    const lowField = `low_${seriesIndex}`;
    const highField = `high_${seriesIndex}`;
    const hasInterval = entry.points.some(point => Number.isFinite(point.low) && Number.isFinite(point.high));
    columns.push({ field: valueField, label: entry.label || fallbackLabel, type: 'number', unit, align: 'right' });
    if (hasInterval) {
      columns.push(
        { field: lowField, label: `${entry.label} low`, type: 'number', unit, align: 'right' },
        { field: highField, label: `${entry.label} high`, type: 'number', unit, align: 'right' },
      );
    }
    entry.points.forEach((point, pointIndex) => {
      const key = point.label || `Point ${pointIndex + 1}`;
      const row = rowsByLabel.get(key) ?? { id: `point-${rowsByLabel.size}`, label: key };
      row[valueField] = point.value;
      if (hasInterval && Number.isFinite(point.low) && Number.isFinite(point.high)) {
        row[lowField] = Number(point.low);
        row[highField] = Number(point.high);
      }
      rowsByLabel.set(key, row);
    });
    chartSeries.push({
      id: entry.id || `series-${seriesIndex}`,
      label: entry.label || fallbackLabel,
      mark: 'line',
      xField: 'label',
      yField: valueField,
      color: entry.color,
      smooth: false,
      ...(hasInterval ? { lowerField: lowField, upperField: highField } : {}),
    });
  });

  return { rows: [...rowsByLabel.values()], columns, series: chartSeries };
}

function visualizationUnit(label: string): VisualizationUnit {
  if (label === 'USD') return 'usd';
  if (label === 'Calls') return 'count';
  if (label === 'Percent') return 'percent';
  return 'credits';
}
