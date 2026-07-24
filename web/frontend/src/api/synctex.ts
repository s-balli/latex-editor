import { apiFetch } from './client';

export interface ForwardResult {
  page: number;
  x: number;
  y: number;
  left: number;
  width: number;
  height: number;
}

export interface ReverseResult {
  file_path: string;
  line: number;
  col: number;
}

/** Editör satırı → PDF konumu (synctex view). */
export function forwardSearch(
  tex_path: string,
  line: number,
  col: number,
  pdf_path: string,
): Promise<ForwardResult> {
  return apiFetch('/synctex/forward', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ tex_path, line, col, pdf_path }),
  });
}

/** PDF tıklaması → kaynak dosya + satır (synctex edit). */
export function reverseSearch(
  page: number,
  x: number,
  y: number,
  pdf_path: string,
): Promise<ReverseResult> {
  return apiFetch('/synctex/reverse', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ page, x, y, pdf_path }),
  });
}
