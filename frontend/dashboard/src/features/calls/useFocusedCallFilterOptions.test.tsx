import { renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { CallRow } from "../../api/types";
import { useFocusedCallFilterOptions } from "./useFocusedCallFilterOptions";

const call = (model: string, effort: string) =>
  ({
    id: `${model}-${effort}`,
    model,
    effort,
  }) as CallRow;

describe("useFocusedCallFilterOptions", () => {
  it("discovers and retains options returned by focused call pages", () => {
    const { result, rerender } = renderHook(
      ({ calls }) =>
        useFocusedCallFilterOptions({
          calls,
          modelOptions: [],
          effortOptions: [],
          focusedModelOptions: ["gpt-older-page"],
          focusedEffortOptions: ["medium"],
          selectedModel: "all",
          selectedEffort: "all",
        }),
      { initialProps: { calls: [call("gpt-5.6-luna", "max")] } },
    );

    expect(result.current).toEqual({
      models: ["gpt-5.6-luna", "gpt-older-page"],
      efforts: ["max", "medium"],
    });

    rerender({ calls: [call("gpt-5.6-sol", "high")] });

    expect(result.current).toEqual({
      models: ["gpt-5.6-luna", "gpt-5.6-sol", "gpt-older-page"],
      efforts: ["high", "max", "medium"],
    });
  });
});
