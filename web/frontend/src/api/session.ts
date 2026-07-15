import { apiFetch } from './client';
import type { SessionData } from '../types';

export function loadSession(): Promise<SessionData> {
  return apiFetch('/session');
}

export function saveSession(data: SessionData): Promise<{ success: boolean }> {
  return apiFetch('/session', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
}
