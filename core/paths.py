"""Platform path dönüşümleri — Windows/WSL köprüsü."""

import re


def windows_to_wsl(windows_path: str) -> str:
    """C:\\Users\\... -> /mnt/c/Users/..."""
    p = windows_path.replace("\\", "/")
    if len(p) >= 2 and p[1] == ":":
        return f"/mnt/{p[0].lower()}{p[2:]}"
    return p


def wsl_to_windows(wsl_path: str) -> str:
    """/mnt/c/Users/... -> C:\\Users\\..."""
    m = re.match(r'^/mnt/([a-zA-Z])(/.*)$', wsl_path)
    if m:
        win_path = m.group(2).replace('/', '\\')
        return f"{m.group(1).upper()}:{win_path}"
    return wsl_path
