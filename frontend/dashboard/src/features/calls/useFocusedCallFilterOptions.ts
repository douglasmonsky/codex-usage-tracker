import { useEffect, useMemo, useState } from "react";

import type { CallRow } from "../../api/types";
import { uniqueSorted } from "../shared/filtering";

export function useFocusedCallFilterOptions({
  calls,
  effortOptions,
  focusedEffortOptions,
  focusedModelOptions,
  modelOptions,
  selectedEffort,
  selectedModel,
}: {
  calls: CallRow[];
  effortOptions: string[];
  focusedEffortOptions: string[];
  focusedModelOptions: string[];
  modelOptions: string[];
  selectedEffort: string;
  selectedModel: string;
}) {
  const [discovered, setDiscovered] = useState({
    models: [] as string[],
    efforts: [] as string[],
  });

  useEffect(() => {
    if (!calls.length) return;
    setDiscovered((current) => ({
      models: uniqueSorted([
        ...current.models,
        ...calls.map((call) => call.model),
      ]),
      efforts: uniqueSorted([
        ...current.efforts,
        ...calls.map((call) => call.effort),
      ]),
    }));
  }, [calls]);

  return {
    models: useMemo(
      () =>
        uniqueSorted([
          ...modelOptions,
          ...focusedModelOptions,
          ...discovered.models,
          ...(selectedModel === "all" ? [] : [selectedModel]),
        ]),
      [discovered.models, focusedModelOptions, modelOptions, selectedModel],
    ),
    efforts: useMemo(
      () =>
        uniqueSorted([
          ...effortOptions,
          ...focusedEffortOptions,
          ...discovered.efforts,
          ...(selectedEffort === "all" ? [] : [selectedEffort]),
        ]),
      [discovered.efforts, effortOptions, focusedEffortOptions, selectedEffort],
    ),
  };
}
