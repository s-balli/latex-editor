export function startCompile(path: string, engine: string): Promise<{ compile_id: string }> {
  return fetch('/api/compile', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path, engine }),
  }).then(r => r.json());
}

export function stopCompile(compileId: string): Promise<{ success: boolean }> {
  return fetch(`/api/compile/${compileId}/stop`, { method: 'POST' }).then(r => r.json());
}

export function getPdfUrl(path: string): string {
  return `/api/pdf?path=${encodeURIComponent(path)}`;
}
