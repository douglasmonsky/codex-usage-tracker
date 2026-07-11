import { SegmentedControl } from '../../design';

export type ExploreWorkspaceId = 'calls' | 'threads' | 'tools' | 'files';

const options: ReadonlyArray<{ value: ExploreWorkspaceId; label: string }> = [
  { value: 'calls', label: 'Calls' },
  { value: 'threads', label: 'Threads' },
  { value: 'tools', label: 'Tools' },
  { value: 'files', label: 'Files' },
];

export function ExploreWorkspaceSwitcher({
  current,
  onValueChange,
}: {
  current: ExploreWorkspaceId;
  onValueChange: (workspace: ExploreWorkspaceId) => void;
}) {
  return (
    <SegmentedControl
      label="Explore workspace"
      options={options}
      value={current}
      onValueChange={onValueChange}
    />
  );
}

export function exploreWorkspaceFromSearch(search = window.location.search): Exclude<ExploreWorkspaceId, 'threads'> {
  const workspace = new URLSearchParams(search).get('explore');
  return workspace === 'tools' || workspace === 'files' ? workspace : 'calls';
}

export function exploreWorkspaceUrl(
  workspace: Exclude<ExploreWorkspaceId, 'threads'>,
  href = window.location.href,
): URL {
  const url = new URL(href);
  url.searchParams.set('view', 'calls');
  if (workspace === 'calls') url.searchParams.delete('explore');
  else url.searchParams.set('explore', workspace);
  return url;
}
