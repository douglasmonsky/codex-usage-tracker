export function normalizeSearchText(value: string): string {
  return value.trim().toLowerCase();
}

export function rowMatchesQuery(values: unknown[], query: string): boolean {
  const normalized = normalizeSearchText(query);
  if (!normalized) {
    return true;
  }

  return values.some(value => String(value ?? '').toLowerCase().includes(normalized));
}

export function uniqueSorted(values: string[]): string[] {
  return [...new Set(values.filter(Boolean))].sort((left, right) => left.localeCompare(right));
}
