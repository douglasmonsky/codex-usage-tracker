export type ConstellationPosition = readonly [x: number, y: number, z: number];

export type UsageConstellationPoint = {
  cachedPercent: number;
  color: string;
  credits: number;
  effort: string;
  id: string;
  model: string;
  position: ConstellationPosition;
  recordId: string;
  size: number;
  thread: string;
  threadKey: string;
  timestamp: string;
  totalTokens: number;
  wastePressure: number;
};

export type UsageConstellationLink = {
  sourceIndex: number;
  targetIndex: number;
};

export type UsageConstellationLegendItem = {
  color: string;
  count: number;
  label: string;
};

export type UsageConstellationModel = {
  accessibleSummary: string;
  links: UsageConstellationLink[];
  points: UsageConstellationPoint[];
  legend: UsageConstellationLegendItem[];
  sampled: boolean;
  totalCalls: number;
};
