import os
from pathlib import Path

from web.backend.config import WORKSPACE_ROOT, EXTENSIONS

import sys
sys.path.insert(0, str(WORKSPACE_ROOT))
from core.input_parser import parse_inputs, group_by_directory

_SKIP_DIRS = {
    "node_modules", "__pycache__", ".git", ".svn",
    "build", "dist", ".venv", "venv", ".env",
    ".mypy_cache", ".pytest_cache", "pytorch-env",
}
_MAX_DEPTH = 5
_MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB


def _resolve(path: str) -> Path:
    """Verilen yolu WORKSPACE_ROOT altında çözümle, path traversal engelle."""
    resolved = (WORKSPACE_ROOT / path).resolve()
    try:
        resolved.relative_to(WORKSPACE_ROOT)
    except ValueError:
        raise PermissionError(f"Yol çalışma alanı dışında: {path}")
    return resolved


def list_dir(rel_path: str) -> list[dict]:
    """Dizin içeriğini recursive listele."""
    root = _resolve(rel_path)
    if not root.is_dir():
        return []
    return _scan(root)


def _scan(dir_path: Path, depth: int = 0) -> list[dict]:
    if depth > _MAX_DEPTH:
        return []
    entries = []
    try:
        items = sorted(os.listdir(dir_path))
    except PermissionError:
        return []

    for name in items:
        if name.startswith('.'):
            continue
        full = dir_path / name
        if full.is_dir():
            if name in _SKIP_DIRS:
                continue
            entries.append({
                "name": name,
                "type": "dir",
                "path": str(full.relative_to(WORKSPACE_ROOT)),
                "children": _scan(full, depth + 1),
            })
        elif full.is_file():
            ext = full.suffix.lower()
            if ext in EXTENSIONS:
                entries.append({
                    "name": name,
                    "type": "file",
                    "path": str(full.relative_to(WORKSPACE_ROOT)),
                })
    return entries


def read_file(rel_path: str) -> str:
    """Dosya içeriğini oku (UTF-8)."""
    path = _resolve(rel_path)
    if not path.is_file():
        raise FileNotFoundError(path)
    return path.read_text(encoding="utf-8", errors="replace")


def write_file(rel_path: str, content: str) -> bool:
    """Dosya kaydet."""
    if len(content) > _MAX_FILE_SIZE:
        raise ValueError(f"Dosya boyutu sınırı aşıldı (maks {_MAX_FILE_SIZE // 1024 // 1024}MB)")
    path = _resolve(rel_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return True


def delete_file(rel_path: str) -> bool:
    """Dosya sil."""
    path = _resolve(rel_path)
    if path.is_file():
        path.unlink()
        return True
    return False


def get_abs_path(rel_path: str) -> Path:
    """Mutlak yol al (validation ile)."""
    return _resolve(rel_path)


def get_input_tree(rel_path: str) -> list[dict]:
    """Dosyanın \\input/\\include bağımlılık ağacını döndür."""
    abs_path = _resolve(rel_path)
    if not abs_path.is_file():
        return []
    content = abs_path.read_text(encoding='utf-8', errors='replace')
    refs = parse_inputs(content, str(abs_path.parent))
    refs = group_by_directory(refs, str(abs_path.parent))
    return _to_relative(refs)


def _to_relative(refs: list[dict]) -> list[dict]:
    """Mutlak yolları workspace'e göreli yap."""
    result = []
    for ref in refs:
        try:
            rel = str(Path(ref['path']).relative_to(WORKSPACE_ROOT))
        except ValueError:
            rel = ref['path']
        entry = {
            'name': ref['name'],
            'path': rel,
            'children': _to_relative(ref.get('children', [])),
        }
        if ref.get('is_dir'):
            entry['is_dir'] = True
        result.append(entry)
    return result
