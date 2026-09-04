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


def group_by_directory(refs: list[dict], base_dir: str,
                       root_dir: str | None = None) -> list[dict]:
    r"""Düz dosya listesini dizin yapısına göre grupla.

    ``root_dir`` ana belgenin dizinidir ve ``parse_inputs``taki ile aynı
    anlamı taşır: yollar ONA göre çözülmüştür. Özyinelemede DEĞİŞMEZ.

    Eskiden bir dosyanın çocukları o dosyanın KENDİ dizinine göre gruplanıyordu.
    Yollar köke göre çözüldüğü için, alt dizindeki bir bölüm başka bir dizine
    ``\input`` ettiğinde ``relpath`` ``..`` ile başlıyor ve ağaca ``..`` adlı
    sahte bir klasör giriyordu (dosya ağacında ``📁 ..`` diye görünüyordu):

        bolumler/b1.tex içinde \input{ekler/ek1}  ->  bolumler > b1.tex > .. > ekler
        bolumler/b1.tex içinde \input{makrolar}   ->  bolumler > b1.tex > ..
    """
    if root_dir is None:
        root_dir = base_dir
    result = []
    dir_groups: dict[str, list[dict]] = {}

    for ref in refs:
        rel = os.path.relpath(ref['path'], base_dir)
        parts = rel.split(os.sep)

        if len(parts) == 1:
            entry = {'name': ref['name'], 'path': ref['path']}
            if ref.get('children'):
                # Çocuklar KÖKE göre gruplanıyor; parse_inputs onları köke göre
                # çözdü. (parts == 1 olduğu için dirname(ref['path']) zaten
                # base_dir'e eşitti, yani buradaki tek fark kök ile base_dir'in
                # ayrıştığı özyineleme dallarında ortaya çıkıyor.)
                entry['children'] = group_by_directory(
                    ref['children'], root_dir, root_dir)
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
            'children': group_by_directory(dir_refs, dir_path, root_dir),
        })

    return result
