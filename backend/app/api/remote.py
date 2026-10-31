"""Remote control between one person's devices: see what another device is playing, play/pause,
skip, seek, change its volume, and move the queue from one device to another.

Each open muzplayer tab is a device. It listens on an event stream (server-sent events: plain
HTTP, so it passes proxies that don't forward WebSockets) and reports its player state with POSTs;
commands from another device of the same person are passed on through that stream.

The devices live in this process's memory: that works because the server runs one worker
(entrypoint.sh, uvicorn --workers 1). Everything touching them is async, on the event loop.
"""

import asyncio
import json
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ..models import User
from ..security import api_error, current_user

router = APIRouter()

HEARTBEAT = 15  # seconds: a proxy closes an idle stream (nginx after 60 s)
SILENT_AFTER = 90  # seconds without a report: a page the phone suspended (its socket may stay open)
MAX_DEVICES = 12  # per person
MAX_PAYLOAD = 512 * 1024  # a state or command, as JSON (a queue moved between devices)
COMMANDS = ("toggle", "play", "pause", "next", "prev", "seek", "volume", "play_tracks", "handoff")


@dataclass(eq=False)
class Device:
    id: str
    name: str
    queue: asyncio.Queue = field(default_factory=lambda: asyncio.Queue(maxsize=100))
    state: dict | None = None
    state_at: float = 0.0  # server time of the state (positions move on from there while playing)
    seen: float = field(default_factory=time.time)  # its last report (it sends one at least every 30 s)


_devices: dict[int, dict[str, Device]] = {}  # user id -> device id -> device


def _send(device: Device, message: dict) -> None:
    try:
        device.queue.put_nowait(message)
    except asyncio.QueueFull:  # a stalled stream: it reconnects and gets the list again
        pass


def _broadcast(user_id: int) -> None:
    """Every device of the person gets the current list (each leaves itself out)."""
    devices = _devices.get(user_id, {})
    listing = [{"id": d.id, "name": d.name, "state": d.state, "state_at": d.state_at} for d in devices.values()]
    for d in devices.values():
        _send(d, {"type": "devices", "now": time.time(), "list": listing})


def _check_id(value: str) -> str:
    if not (8 <= len(value) <= 64) or not all(c.isalnum() or c in "-_" for c in value):
        raise api_error(422, "validation")
    return value


@router.get("/remote/events")
async def events(
    device: str = Query(min_length=8, max_length=64),
    name: str = Query("", max_length=60),
    user: User = Depends(current_user),
):
    """This device's event stream: device lists and commands, as server-sent events."""
    device_id = _check_id(device)
    devices = _devices.setdefault(user.id, {})
    old = devices.get(device_id)
    if old is None and len(devices) >= MAX_DEVICES:
        raise api_error(429, "too_many_devices")
    me = Device(device_id, name.strip() or "?", state=old.state if old else None, state_at=old.state_at if old else 0.0)
    if old is not None:
        _send(old, {"type": "replaced"})  # the same tab reconnected: the old stream ends
    devices[device_id] = me
    _broadcast(user.id)

    async def stream() -> AsyncIterator[str]:
        try:
            yield "retry: 3000\n\n"
            while True:
                try:
                    message = await asyncio.wait_for(me.queue.get(), HEARTBEAT)
                except TimeoutError:
                    if time.time() - me.seen > SILENT_AFTER:
                        return
                    yield ": ping\n\n"
                    continue
                if message.get("type") == "replaced":
                    return
                yield f"data: {json.dumps(message, ensure_ascii=False)}\n\n"
        finally:
            mine = _devices.get(user.id, {})
            if mine.get(device_id) is me:
                del mine[device_id]
                if not mine:
                    _devices.pop(user.id, None)
                _broadcast(user.id)

    headers = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    return StreamingResponse(stream(), media_type="text/event-stream", headers=headers)


class StateIn(BaseModel):
    device: str = Field(min_length=8, max_length=64)
    state: dict[str, Any] | None


@router.post("/remote/state", status_code=204)
async def report_state(body: StateIn, user: User = Depends(current_user)):
    """What this device is playing now (track, playing, position, volume, ...)."""
    me = _devices.get(user.id, {}).get(body.device)
    if me is None:
        raise api_error(404, "not_found")  # not listening (yet): nothing to tell anyone
    if len(json.dumps(body.state)) > MAX_PAYLOAD:
        raise api_error(413, "too_large")
    me.state, me.state_at = body.state, time.time()
    me.seen = me.state_at
    _broadcast(user.id)


class CommandIn(BaseModel):
    device: str = Field(min_length=8, max_length=64)  # the sender
    to: str = Field(min_length=8, max_length=64)
    cmd: Literal[COMMANDS]  # type: ignore[valid-type]
    arg: Any = None


@router.post("/remote/command", status_code=204)
async def command(body: CommandIn, user: User = Depends(current_user)):
    """Passes a command on to another device of the same person."""
    target = _devices.get(user.id, {}).get(body.to)
    if target is None:
        raise api_error(404, "device_gone")
    if len(json.dumps(body.arg)) > MAX_PAYLOAD:
        raise api_error(413, "too_large")
    _send(target, {"type": "command", "from": body.device, "cmd": body.cmd, "arg": body.arg})
