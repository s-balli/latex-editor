import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from web.backend.routers import files, compile, session, synctex
from web.backend.services import file_system

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from core.version import VERSION


def create_app() -> FastAPI:
    app = FastAPI(title="LaTeX Editor Web", version=VERSION)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(files.router, prefix="/api/files", tags=["files"])
    app.include_router(compile.router, prefix="/api/compile", tags=["compile"])
    app.include_router(session.router, prefix="/api/session", tags=["session"])
    app.include_router(synctex.router, prefix="/api/synctex", tags=["synctex"])

    @app.get("/api/version")
    def get_version():
        return {"version": VERSION}

    @app.get("/api/pdf")
    def serve_pdf(path: str, download: bool = False):
        abs_path = file_system.get_abs_path(path)
        if not abs_path.exists():
            from fastapi import HTTPException
            raise HTTPException(404, "PDF bulunamadı")
        if download:
            return FileResponse(str(abs_path), media_type="application/pdf", filename=abs_path.name)
        return FileResponse(str(abs_path), media_type="application/pdf")

    return app
