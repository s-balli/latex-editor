import asyncio
import re
import sys
import uuid
from pathlib import Path
from typing import Optional

from web.backend.config import DERLE_SH
from web.backend.services import file_system

# core/ modüllerini import et
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent / "core"))
from log_parser import parse_output
from engine_detector import can_compile as _can_compile

# Aktif derleme
_current_process: Optional[asyncio.subprocess.Process] = None
_current_compile_id: Optional[str] = None


def start_compile(rel_path: str, engine: str = "lualatex") -> str:
    global _current_compile_id
    if _current_compile_id is not None:
        raise RuntimeError("Zaten bir derleme çalışıyor")

    abs_path = file_system.get_abs_path(rel_path)
    if not abs_path.exists():
        raise FileNotFoundError(f"Dosya bulunamadı: {abs_path}")

    ok, msg = _can_compile(str(abs_path))
    if not ok:
        raise ValueError(msg)

    compile_id = uuid.uuid4().hex[:8]
    _current_compile_id = compile_id
    return compile_id


async def run_compile(compile_id: str, rel_path: str, engine: str, output_queue: asyncio.Queue):
    global _current_process, _current_compile_id

    abs_path = file_system.get_abs_path(rel_path)
    abs_dir = abs_path.parent

    cmd = ["bash", DERLE_SH, str(abs_path)]
    if engine == "pdflatex":
        cmd.append("--pdflatex")

    try:
        _current_process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=str(abs_dir),
        )

        # stdout'u satır satır oku
        output_lines = []
        while True:
            line = await _current_process.stdout.readline()
            if not line:
                break
            text = line.decode("utf-8", errors="replace")
            output_lines.append(text)
            await output_queue.put({"type": "output", "line": text})

        await _current_process.wait()

        # Sonuç parse et
        raw_output = "".join(output_lines)
        clean_output = re.sub(r'\x1b\[[0-9;]*m', '', raw_output)
        result = parse_output(clean_output, str(abs_path))

        # PDF yolunu belirle — derle.sh her motor (lualatex/pdflatex) için
        # <isim>.pdf üretir (desktop/core/compiler.py ile aynı).
        name = abs_path.stem
        pdf_name = f"{name}.pdf"
        pdf_path = abs_dir / pdf_name
        result.pdf_path = str(pdf_path) if pdf_path.exists() else ""
        result.success = pdf_path.exists()

        result_dict = {
            "success": result.success,
            "pdf_path": result.pdf_path,
            "errors": [
                {"line_number": e.line_number, "message": e.message, "file_path": e.file_path}
                for e in result.errors
            ],
            "warnings": [
                {"line_number": w.line_number, "message": w.message, "warning_type": w.warning_type, "file_path": w.file_path if hasattr(w, 'file_path') else rel_path}
                for w in result.warnings
            ],
            "suggestions": [
                {"message": s.message, "install_command": s.install_command}
                for s in result.suggestions
            ],
            "raw_output": raw_output,
        }

        await output_queue.put({"type": "result", "data": result_dict})
    except Exception as e:
        await output_queue.put({"type": "error", "message": str(e)})
    finally:
        _current_process = None
        _current_compile_id = None


def stop_compile():
    global _current_process, _current_compile_id
    if _current_process and _current_process.returncode is None:
        _current_process.kill()
    _current_process = None
    _current_compile_id = None
