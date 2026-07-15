import { describe, expect, it } from 'vitest';

import { translateZhHansUiText, type CatalogTemplateTranslation } from './translate';

describe('Simplified Chinese React fallback translations', () => {
  it('uses the supplemental catalog for React-only interface text', () => {
    expect(translateZhHansUiText('Diagnostics Notebook')).toBe('诊断工作台');
    expect(translateZhHansUiText('The important changes first, with direct paths into supporting evidence.'))
      .toBe('优先展示重要变化，并可直接查看支撑证据。');
  });

  it('reuses translations from the canonical dashboard catalog', () => {
    const catalog = new Map([['Calls', '调用']]);
    expect(translateZhHansUiText('Calls', catalog)).toBe('调用');
  });

  it('formats dynamic React messages without changing their values', () => {
    expect(translateZhHansUiText('Loaded 250 of 1,000 available calls'))
      .toBe('已加载 250 / 1,000 次可用调用');
    expect(translateZhHansUiText('12 calls analyzed · 8 detail rows cached'))
      .toBe('已分析 12 次调用 · 已缓存 8 条详情记录');
    expect(translateZhHansUiText('All time analysis ready across 3,302 calls; 3,302 detail rows cached'))
      .toBe('全部时间范围分析已就绪，共 3,302 次调用；已缓存 3,302 条详情记录');
    expect(translateZhHansUiText('347.29M cached input tokens'))
      .toBe('347.29M 个缓存输入token');
    expect(translateZhHansUiText('3302 calls in the selected scope include 95 percent cached input reuse.'))
      .toBe('所选范围内的 3302 次调用中，缓存输入复用率为 95%。');
  });

  it('localizes compact visualization and signal labels', () => {
    expect(translateZhHansUiText('Day')).toBe('日期');
    expect(translateZhHansUiText('From')).toBe('来源');
    expect(translateZhHansUiText('FILTERS')).toBe('筛选');
    expect(translateZhHansUiText('Filters')).toBe('筛选');
    expect(translateZhHansUiText('PRICE')).toBe('定价');
    expect(translateZhHansUiText('CTX')).toBe('上下文');
    expect(translateZhHansUiText('blank')).toBe('未指定');
    expect(translateZhHansUiText('xhigh')).toBe('超高');
    expect(translateZhHansUiText('Jul 15, 10:19 PM · Call 1'))
      .toBe('7月15日 22:19 · 第 1 次调用');
    expect(translateZhHansUiText('234.45K at Jul 15, 10:30 PM'))
      .toBe('234.45K，发生于 7月15日 22:30');
    expect(translateZhHansUiText('xhigh x285, high x59')).toBe('超高 ×285、高 ×59');
    expect(translateZhHansUiText('1,485.81 credits (Official match)'))
      .toBe('1,485.81 点（官方精确匹配）');
    expect(translateZhHansUiText('Prev 25s')).toBe('距上次 25 秒');
    expect(translateZhHansUiText('Today: 2026-07-15 to 2026-07-15'))
      .toBe('今天：2026-07-15 至 2026-07-15');
    expect(translateZhHansUiText('Cache Risk')).toBe('缓存风险');
    expect(translateZhHansUiText('Pro observed')).toBe('Pro 观测值');
  });

  it('translates nested report findings', () => {
    expect(translateZhHansUiText('Cost Curves contains 10 plotted rows. 8 highest-cost loaded calls anchor this report. Estimates use the local pricing model.'))
      .toBe('成本曲线包含 10 条绘图记录。此报告以成本最高的 8 次已加载调用为核心，估算采用本地定价模型。');
  });

  it('covers the advanced investigation, limits, and cache workspaces', () => {
    expect(translateZhHansUiText('Root-cause workspace')).toBe('根因分析工作区');
    expect(translateZhHansUiText('Cache And Context Lab')).toBe('缓存与上下文实验室');
    expect(translateZhHansUiText('Weekly evidence first, rolling-window context second, and no claim beyond the loaded local data.'))
      .toBe('以每周证据为主、滚动窗口上下文为辅，结论不超出已加载的本地数据。');
  });

  it('localizes chart accessibility labels and contract errors', () => {
    expect(translateZhHansUiText('Tokens line chart')).toBe('token折线图');
    expect(translateZhHansUiText('Visualization contract error')).toBe('可视化定义错误');
    expect(translateZhHansUiText('must include at least one series')).toBe('必须至少包含一个数据系列');
  });

  it('hydrates canonical placeholder templates', () => {
    const templates: CatalogTemplateTranslation[] = [{
      pattern: /^Loaded (.+?) of (.+?) calls$/u,
      placeholders: ['loaded', 'total'],
      translatedTemplate: '已加载 {loaded}/{total} 次调用',
    }];
    expect(translateZhHansUiText('Loaded 3 of 9 calls', new Map(), templates))
      .toBe('已加载 3/9 次调用');
  });

  it('prefers precise React patterns over broad catalog templates', () => {
    const templates: CatalogTemplateTranslation[] = [{
      pattern: /^Showing (.+?) of (.+?) (.+)$/u,
      placeholders: ['shown', 'total', 'kind'],
      translatedTemplate: '{kind}：已显示 {shown}/{total}',
    }];
    expect(translateZhHansUiText('Showing 2 of 3 aggregate rows', new Map(), templates))
      .toBe('显示 2 / 3 条聚合记录');
  });

  it('leaves unknown data values unchanged', () => {
    expect(translateZhHansUiText('gpt-5.4')).toBe('gpt-5.4');
    expect(translateZhHansUiText('/Users/example/project')).toBe('/Users/example/project');
  });
});
