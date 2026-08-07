import asyncio
import datetime
import json
import os
from contextlib import suppress
from pathlib import Path
from types import TracebackType
from typing import Any

import uvicorn
import watchfiles
from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from service_framework.telemetry.routes import router


class AppLifespan:
    def __init__(self) -> None:
        self._task: asyncio.Task[None] | None = None

    async def __aenter__(self) -> None:
        self._task = asyncio.create_task(watch_state_changes())
        return None

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._task is None:
            return
        self._task.cancel()
        with suppress(asyncio.CancelledError):
            await self._task

    def __call__(self, app: FastAPI) -> "AppLifespan":
        return self


app = FastAPI(title="SFW Telemetry Service", lifespan=AppLifespan())
app.include_router(router)

active_connections: set[WebSocket] = set()


@app.websocket("/api/v1/ws/telemetry")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_connections.add(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        active_connections.remove(websocket)


async def watch_state_changes():
    xdg_data = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
    state_dir = xdg_data / "sfw" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)

    async for changes in watchfiles.awatch(state_dir):  # type: ignore[reportUnknownVariableType]
        for _change_type, filepath_str in changes:
            filepath = Path(filepath_str)
            if filepath.suffix != ".json" or filepath.name.startswith("."):
                continue

            service_name = filepath.stem
            payload: dict[str, Any] = {}
            if filepath.exists():
                try:
                    with open(filepath, encoding="utf-8") as f:
                        payload = json.load(f)
                except Exception:
                    continue

            event: dict[str, Any] = {
                "event": "STATE_CHANGE",
                "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
                "service": service_name,
                "data": payload,
            }

            dead_conns: set[WebSocket] = set()
            for conn in active_connections:
                try:
                    await conn.send_json(event)
                except Exception:
                    dead_conns.add(conn)

            for conn in dead_conns:
                active_connections.remove(conn)


def main():
    uvicorn.run("service_framework.telemetry.daemon:app", host="127.0.0.1", port=8765, reload=False)


if __name__ == "__main__":
    main()
