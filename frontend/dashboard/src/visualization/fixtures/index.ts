export * from './analyticalExamples';
export * from './operationalExamples';
export * from './stateExamples';

import { allowanceChangePointSpec, tokenFlowSpec } from './analyticalExamples';
import { cacheFrontierSpec, evidenceLedgerSpec, threadLifecycleSpec, wasteMatrixSpec } from './operationalExamples';

export const visualizationExampleSpecs = [
  allowanceChangePointSpec,
  tokenFlowSpec,
  cacheFrontierSpec,
  threadLifecycleSpec,
  wasteMatrixSpec,
  evidenceLedgerSpec,
];
