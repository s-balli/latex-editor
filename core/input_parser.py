"""LaTeX \\input/\\include referanslarını özyinelemeli çözümle."""
import os
import re
from pathlib import Path
import logging

from core.latex_utils import strip_comments

_logger = logging.getLogger("latex_editor.input_parser")

_RE_INPUT = re.compile(r'\\(?:input|include)\s*\{([^}]+)\}')


def parse_inputs(content: str, base_dir: str, visited: set | None = None,
                 root_dir: str | None = None) -> list[dict]:
    r"""``\input``/``\include`` zincirini çözümle.

    ``root_dir`` ana belgenin dizinidir ve özyinelemede DEĞİŞMEZ: LaTeX
    yolları derleme dizinine göre çözer, çocuğun kendi dizinine göre değil.
    Eskiden çocuğa kendi dizini kök olarak veriliyordu; alt dizinli
    projelerde (``\input{bolumler/bolum1}``, bolum1 içinde
    ``\input{bolumler/bolum2}``) torun dosyalar hiç bulunamıyor, dosya
    ağacında görünmüyor, ``\label``'ları tamamlamaya gelmiyor ve Referans
    Denetimi olmayan "tanımsız \ref" uyduruyordu.
    """
    if visited is None:
        visited = set()
    if root_dir is None:
        root_dir = base_dir

    root_resolved = Path(root_dir).resolve()
    stripped = strip_comments(content)
    refs = []

    for match in _RE_INPUT.finditer(stripped):
        ref = match.group(1).strip()
        if not ref:
            continue
        if not os.path.splitext(ref)[1]:
            ref += '.tex'

        # Önce LaTeX uzlaşımı (köke göre); bulunamazsa çocuğa göre dene —
        # bazı projeler bölümleri kendi dizinlerine göre yazıyor.
        full_path = os.path.normpath(os.path.join(root_dir, ref))
        if not os.path.isfile(full_path):
            aday = os.path.normpath(os.path.join(base_dir, ref))
            if os.path.isfile(aday):
                full_path = aday
        # Path traversal koruması — kök dizine göre (çocuğa göre değil)
        try:
            Path(full_path).resolve().relative_to(root_resolved)
        except ValueError:
            _logger.warning("Path traversal engellendi: %s (kök: %s)", full_path, root_resolved)
            continue
        if full_path in visited or not os.path.isfile(full_path):
            continue
        visited.add(full_path)

        children = []
        try:
            with open(full_path, 'r', encoding='utf-8', errors='replace') as f:
                child_content = f.read()
            children = parse_inputs(child_content, os.path.dirname(full_path),
                                    visited, root_dir)
        except Exception as e:
            _logger.warning("Input dosyası okunamadı: %s (%s)", full_path, e)

        refs.append({
            'name': os.path.basename(full_path),
            'path': full_path,
            'children': children,
        })

    return refs


def group_by_directory(refs: list[dict], base_dir: str) -> list[dict]:
    """Düz dosya listesini dizin yapısına göre grupla."""
    result = []
    dir_groups: dict[str, list[dict]] = {}

    for ref in refs:
        rel = os.path.relpath(ref['path'], base_dir)
        parts = rel.split(os.sep)

        if len(parts) == 1:
            entry = {'name': ref['name'], 'path': ref['path']}
            if ref.get('children'):
                entry['children'] = group_by_directory(ref['children'], os.path.dirname(ref['path']))
            result.append(entry)
        else:
            first = parts[0]
            if first not in dir_groups:
                dir_groups[first] = []
            dir_groups[first].append(ref)

    for dir_name, dir_refs in sorted(dir_groups.items()):
        dir_path = os.path.join(base_dir, dir_name)
        result.append({
            'name': dir_name,
            'path': dir_path,
            'is_dir': True,
            'children': group_by_directory(dir_refs, dir_path),
        })

    return result
