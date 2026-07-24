import asyncio

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from web.backend.services import compiler, file_system

router = APIRouter()


class CompileRequest(BaseModel):
    path: str
    engine: str = "lualatex"


@router.post("")
def start_compile(req: CompileRequest):
    try:
        compile_id = compiler.start_compile(req.path, req.engine)
        return {"compile_id": compile_id}
    except RuntimeError as e:
        raise HTTPException(409, str(e))
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(422, str(e))


@router.websocket("/{compile_id}/ws")
async def compile_ws(ws: WebSocket, compile_id: str):
    await ws.accept()
    output_queue = asyncio.Queue()

    # Derleme bilgilerini al — son request'ten
    # Basit çözüm: query parametreleri ile
    # Ama WebSocket bağlantısında path/engine gerekli
    # Bunun yerine compiler state kullanılır
    try:
        # WebSocket accept sonrası ilk mesaj olarak path/engine bekle
        init = await ws.receive_json()
        rel_path = init["path"]
        engine = init.get("engine", "lualatex")

        # Derlemeyi başlat
        asyncio.create_task(compiler.run_compile(compile_id, rel_path, engine, output_queue))

        while True:
            msg = await output_queue.get()
            await ws.send_json(msg)
            if msg["type"] in ("result", "error"):
                break
    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await ws.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass


@router.post("/{compile_id}/stop")
def stop_compile(compile_id: str):
    compiler.stop_compile()
    return {"success": True}


@router.get("/pdf")
def get_pdf(path: str):
    """PDF dosyasını serve et."""
    abs_path = file_system.get_abs_path(path)
    if not abs_path.exists():
        raise HTTPException(404, "PDF bulunamadı")
    return {"path": str(abs_path), "exists": True}
