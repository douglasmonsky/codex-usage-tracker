import { describe, expect, it } from "vitest";
import type { CallRow } from "../../api/types";
import type { ExploreCallsPage } from "../../data/contracts/explore";
import { dedupeThreadCallPages } from "./threadCallLoading";

const call = (id: string): CallRow => ({ id }) as CallRow;
const page = (rows: CallRow[]): ExploreCallsPage => ({
  schema: "codex-usage-tracker-thread-calls-v1",
  rows,
  rowCount: rows.length,
  totalMatchedRows: 3,
  limit: 100,
  offset: 0,
  hasMore: false,
  nextOffset: null,
  rawContextIncluded: false,
  threadKey: "thread-alpha",
  filterOptions: { models: [], efforts: [] },
});

describe("thread call progressive loading", () => {
  it("deduplicates page boundaries by record id while preserving first-seen order", () => {
    expect(
      dedupeThreadCallPages(
        [page([call("a"), call("b")]), page([call("b"), call("c")])],
        [],
      ).map((row) => row.id),
    ).toEqual(["a", "b", "c"]);
  });

  it("uses snapshot calls only before focused pages arrive", () => {
    expect(
      dedupeThreadCallPages([], [call("snapshot")]).map((row) => row.id),
    ).toEqual(["snapshot"]);
    expect(
      dedupeThreadCallPages([page([call("live")])], [call("snapshot")]).map(
        (row) => row.id,
      ),
    ).toEqual(["live"]);
  });
});
