"""SyncTeX router — ileri/geri arama endpoint'leri."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from web.backend.services import synctex, file_system

router = APIRouter()


class ForwardRequest(BaseModel):
    tex_path: str   # workspace-relative (aktif sekme)
    line: int
    col: int = 0
    pdf_path: str   # mutlak (derleme sonucu)


class ReverseRequest(BaseModel):
    page: int
    x: float
    y: float
    pdf_path: str   # mutlak


@router.post("/forward")
def forward(req: ForwardRequest):
    """Editör satırı → PDF konumu."""
    try:
        tex_abs = file_system.get_abs_path(req.tex_path)
        pdf_abs = file_system.get_abs_path(req.pdf_path)
    except PermissionError:
        raise HTTPException(403, "Yol çalışma alanı dışında")
    result = synctex.forward_search(str(tex_abs), req.line, req.col, str(pdf_abs))
    if not result:
        raise HTTPException(404, "SyncTeX eşleşme bulunamadı")
    return {
        "page": result.page,
        "x": result.x,
        "y": result.y,
        "left": result.left,
        "width": result.width,
        "height": result.height,
    }


@router.post("/reverse")
def reverse(req: ReverseRequest):
    """PDF tıklaması → kaynak dosya + satır."""
    try:
        pdf_abs = file_system.get_abs_path(req.pdf_path)
    except PermissionError:
        raise HTTPException(403, "Yol çalışma alanı dışında")
    result = synctex.reverse_search(req.page, req.x, req.y, str(pdf_abs))
    if not result:
        raise HTTPException(404, "SyncTeX eşleşme bulunamadı")
    return {"file_path": result.file_path, "line": result.line, "col": result.col}
