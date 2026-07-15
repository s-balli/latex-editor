from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from web.backend.services import file_system

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from core.engine_detector import detect_engine as _detect_engine_auto

router = APIRouter()


class WriteRequest(BaseModel):
    path: str
    content: str


@router.get("/list")
def list_files(path: str = ""):
    try:
        return file_system.list_dir(path)
    except PermissionError as e:
        raise HTTPException(403, str(e))


@router.get("/read")
def read_file(path: str):
    try:
        content = file_system.read_file(path)
        return {"content": content, "path": path}
    except FileNotFoundError:
        raise HTTPException(404, "Dosya bulunamadı")
    except PermissionError as e:
        raise HTTPException(403, str(e))


@router.put("/write")
def write_file(req: WriteRequest):
    try:
        file_system.write_file(req.path, req.content)
        return {"success": True}
    except PermissionError as e:
        raise HTTPException(403, str(e))
    except ValueError as e:
        raise HTTPException(413, str(e))


@router.delete("/delete")
def delete_file(path: str):
    try:
        if file_system.delete_file(path):
            return {"success": True}
        raise HTTPException(404, "Dosya bulunamadı")
    except PermissionError as e:
        raise HTTPException(403, str(e))


@router.get("/inputs")
def get_inputs(path: str):
    try:
        return file_system.get_input_tree(path)
    except PermissionError as e:
        raise HTTPException(403, str(e))


@router.get("/detect-engine")
def detect_engine(path: str):
    try:
        abs_path = file_system.get_abs_path(path)
        engine = _detect_engine_auto(str(abs_path)) or "pdflatex"
        return {"engine": engine}
    except PermissionError as e:
        raise HTTPException(403, str(e))
