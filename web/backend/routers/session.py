import json
from pathlib import Path
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

_SESSION_FILE = Path(__file__).resolve().parent.parent / "session.json"

router = APIRouter()


class SessionData(BaseModel):
    open_tabs: list[str] = []
    active_tab: int = -1
    engine: str = "lualatex"


@router.get("")
def load_session():
    if not _SESSION_FILE.exists():
        return SessionData().model_dump()
    try:
        data = json.loads(_SESSION_FILE.read_text())
        return data
    except Exception:
        return SessionData().model_dump()


@router.post("")
def save_session(session: SessionData):
    _SESSION_FILE.write_text(session.model_dump_json(indent=2), encoding="utf-8")
    return {"success": True}
