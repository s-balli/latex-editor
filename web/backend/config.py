import os
from pathlib import Path

# Repo root (web/backend/ → web/ → repo root)
REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# derle.sh yolu
DERLE_SH = str(REPO_ROOT / "core" / "derle.sh")

# Çalışma alanı — varsayılan: repo root (proje klasörü)
WORKSPACE_ROOT = Path(os.environ.get("LATEX_WORKSPACE", str(REPO_ROOT))).resolve()

# Host/port
HOST = "0.0.0.0"
PORT = 8000

# Uzantı filtresi (dosya ağacı için)
EXTENSIONS = {".tex", ".cls", ".sty", ".bib"}
