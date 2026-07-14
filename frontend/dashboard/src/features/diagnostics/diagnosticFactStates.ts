import type {
  DiagnosticFactCallsResult,
  DiagnosticFactSourceKey,
  DiagnosticFactsPayload,
} from '../../api/diagnostics';

export type FactLoadState =
  | { status: 'idle'; message: string }
  | { status: 'loading'; message: string }
  | { status: 'loaded'; payload: DiagnosticFactsPayload }
  | { status: 'error'; message: string };

export type FactCallsState =
  | { status: 'idle'; message: string }
  | { status: 'loading'; message: string }
  | { status: 'loaded'; result: DiagnosticFactCallsResult }
  | { status: 'appending'; result: DiagnosticFactCallsResult }
  | { status: 'error'; message: string; result?: DiagnosticFactCallsResult };

export type FactSourcePanelState = {
  key: DiagnosticFactSourceKey;
  label: string;
  title: string;
  state: FactLoadState;
};
