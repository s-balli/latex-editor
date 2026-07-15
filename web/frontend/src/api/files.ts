import { apiFetch } from './client';
import type { FileNode, InputNode } from '../types';

export function listFiles(path = ''): Promise<FileNode[]> {
  return apiFetch(`/files/list?path=${encodeURIComponent(path)}`);
}

export function readFile(path: string): Promise<{ content: string; path: string }> {
  return apiFetch(`/files/read?path=${encodeURIComponent(path)}`);
}

export function writeFile(path: string, content: string): Promise<{ success: boolean }> {
  return apiFetch('/files/write', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path, content }),
  });
}

export function deleteFile(path: string): Promise<{ success: boolean }> {
  return apiFetch(`/files/delete?path=${encodeURIComponent(path)}`, { method: 'DELETE' });
}

export function getInputTree(path: string): Promise<InputNode[]> {
  return apiFetch(`/files/inputs?path=${encodeURIComponent(path)}`);
}

export function detectEngine(path: string): Promise<{ engine: string }> {
  return apiFetch(`/files/detect-engine?path=${encodeURIComponent(path)}`);
}
