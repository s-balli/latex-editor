"""LaTeX dışa aktarma — pandoc ile format dönüşümü."""

import os
import shlex
import shutil
import subprocess
import sys

from core.log import get_logger

_logger = get_logger("exporter")

FORMATS = {
    "DOCX":     ".docx",
    "HTML":     ".html",
    "Markdown": ".md",
    "Plain Text": ".txt",
}

PLATFORM = sys.platform


def pandoc_available() -> bool:
    if PLATFORM == "win32":
        return shutil.which("pandoc") is not None or _wsl_pandoc_available()
    return shutil.which("pandoc") is not None


def _wsl_pandoc_available() -> bool:
    try:
        r = subprocess.run(
            ["wsl", "-e", "which", "pandoc"],
            capture_output=True, text=True, timeout=5,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
        )
        return r.returncode == 0
    except Exception:
        return False


def export(tex_path: str, dest_path: str) -> tuple[bool, str]:
    """pandoc ile .tex → hedef format.

    Dönüş: (başarılı_mı, hata_mesajı)
    """
    if not os.path.exists(tex_path):
        return False, "Kaynak dosya bulunamadı"

    if PLATFORM == "win32":
        ok, err = _export_wsl(tex_path, dest_path)
    else:
        ok, err = _export_native(tex_path, dest_path)

    if ok and dest_path.endswith(".md"):
        _fix_md_image_paths(tex_path, dest_path)

    return ok, err


def _fix_md_image_paths(tex_path: str, md_path: str):
    r"""Markdown'daki göreceli resim yollarını .tex dizinine göre mutlak yap.

    \graphicspath{{media/Bolum1/}} gibi LaTeX yol tanımlarını da hesaba katar.
    """
    tex_dir = os.path.dirname(os.path.abspath(tex_path))
    graphics_paths = _extract_graphics_paths(tex_path)

    try:
        with open(md_path, "r", encoding="utf-8") as f:
            content = f.read()

        import re

        def _replace(m):
            alt = m.group(1)
            path = m.group(2)
            if os.path.isabs(path) or path.startswith(("http://", "https://")):
                return f"![{alt}]({path})"
            # Önce graphicspath öneki (varsa), sonra .tex dizinine göre mutlak yap.
            rel = (graphics_paths[0] + path) if graphics_paths else path
            abs_path = os.path.normpath(os.path.join(tex_dir, rel)).replace(os.sep, '/')
            return f"![{alt}]({abs_path})"

        # {width="70%"} gibi pandoc niteliklerini kaldır
        content = re.sub(r'\{[^}]*width[^}]*\}', '', content)
        content = re.sub(r'!\[([^\]]*)\]\(([^)]+)\)', _replace, content)

        with open(md_path, "w", encoding="utf-8") as f:
            f.write(content)
    except Exception as e:
        _logger.warning("MD resim yolu düzeltme başarısız: %s", e)


def _extract_graphics_paths(tex_path: str) -> list[str]:
    r"""\graphicspath{{dir1/}{dir2/}} içindeki yolları çıkar."""
    import re
    try:
        with open(tex_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        paths = []
        for m in re.finditer(r'\\graphicspath\s*\{(.+)\}', content):
            for inner in re.finditer(r'\{([^}]+)\}', m.group(1)):
                paths.append(inner.group(1))
        return paths
    except Exception:
        return []


def _pandoc_args(tex_path: str, dest_path: str) -> list[str]:
    """Format'a göre pandoc argümanlarını oluştur."""
    work_dir = os.path.dirname(os.path.abspath(tex_path))
    args = ["pandoc", tex_path, "-o", dest_path, f"--resource-path={work_dir}"]
    ext = os.path.splitext(dest_path)[1].lower()
    if ext == ".html":
        args += ["--standalone", "--embed-resources"]
    return args


def _export_native(tex_path: str, dest_path: str) -> tuple[bool, str]:
    work_dir = os.path.dirname(os.path.abspath(tex_path))
    try:
        r = subprocess.run(
            _pandoc_args(tex_path, dest_path),
            capture_output=True, text=True, timeout=30,
            cwd=work_dir,
        )
        if r.returncode != 0:
            _logger.warning("Export başarısız (native): %s → %s — %s", tex_path, dest_path, r.stderr)
            return False, r.stderr.strip() or "Dışa aktarma başarısız"
        return True, ""
    except subprocess.TimeoutExpired:
        return False, "İşlem zaman aşımına uğradı"
    except FileNotFoundError:
        return False, "pandoc bulunamadı — lütfen kurun (apt install pandoc)"
    except Exception as e:
        return False, str(e)


def _export_wsl(tex_path: str, dest_path: str) -> tuple[bool, str]:
    from core.paths import windows_to_wsl

    wsl_tex = windows_to_wsl(tex_path)
    wsl_dir = os.path.dirname(wsl_tex)
    tmp_dest = f"/tmp/export_{os.path.basename(dest_path)}"

    # pandoc argümanlarını oluştur
    pandoc_cmd = ["pandoc", wsl_tex, "-o", tmp_dest, f"--resource-path={wsl_dir}"]
    ext = os.path.splitext(dest_path)[1].lower()
    if ext == ".html":
        pandoc_cmd += ["--standalone", "--embed-resources"]

    try:
        quoted = " ".join(shlex.quote(a) for a in pandoc_cmd)
        r = subprocess.run(
            ["wsl", "-e", "bash", "-c",
             f"cd {shlex.quote(wsl_dir)} && {quoted}"],
            capture_output=True, text=True, timeout=30,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
        )
        if r.returncode != 0:
            _logger.warning("Export başarısız (WSL): %s → %s — %s", tex_path, dest_path, r.stderr)
            return False, r.stderr.strip() or "Dışa aktarma başarısız"

        # Çıktıyı WSL'den Windows'a kopyala
        r2 = subprocess.run(
            ["wsl", "-e", "cp", tmp_dest, windows_to_wsl(dest_path)],
            capture_output=True, text=True, timeout=10,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
        )
        if r2.returncode != 0:
            # cp başarısız — WSL'den okuyup Python ile yaz
            r3 = subprocess.run(
                ["wsl", "-e", "cat", tmp_dest],
                capture_output=True, timeout=10,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
            )
            if r3.returncode == 0:
                with open(dest_path, "wb") as f:
                    f.write(r3.stdout)
            else:
                return False, "Çıktı dosyası kopyalanamadı"

        return True, ""
    except subprocess.TimeoutExpired:
        return False, "İşlem zaman aşımına uğradı"
    except Exception as e:
        return False, str(e)
    finally:
        subprocess.run(
            ["wsl", "-e", "rm", "-f", tmp_dest],
            capture_output=True, timeout=5,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
        )
