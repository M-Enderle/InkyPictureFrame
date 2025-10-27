from __future__ import annotations

import asyncio
import base64
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional
from uuid import uuid4

from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field, validator


@dataclass
class ImageItem:
    """Container for uploaded image data."""

    id: str
    filename: str
    content_type: str
    data: bytes
    uploaded_at: datetime
    offset_x: float = 0.0
    offset_y: float = 0.0


class SettingsModel(BaseModel):
    change_interval: int = Field(60, ge=5, le=3600)
    led_brightness: int = Field(50, ge=0, le=100)
    power_on: bool = True
    saturation: float = Field(0.5, ge=0.0, le=1.0)


class SettingsUpdate(BaseModel):
    change_interval: Optional[int] = Field(None, ge=5, le=3600)
    led_brightness: Optional[int] = Field(None, ge=0, le=100)
    power_on: Optional[bool] = None
    saturation: Optional[float] = Field(None, ge=0.0, le=1.0)


class QueueOrder(BaseModel):
    image_ids: List[str]

    @validator("image_ids")
    def ensure_unique(cls, value: List[str]) -> List[str]:
        if len(set(value)) != len(value):
            raise ValueError("queue order contains duplicates")
        return value


class QueueInsert(BaseModel):
    image_id: str
    index: Optional[int] = Field(None, ge=0)


class ImageTransform(BaseModel):
    offset_x: float = Field(0.0, ge=-1.0, le=1.0)
    offset_y: float = Field(0.0, ge=-1.0, le=1.0)


class ImageStub(BaseModel):
    id: str
    filename: str
    content_type: str
    uploaded_at: datetime
    image_url: str
    offset_x: float
    offset_y: float


class FramePayload(BaseModel):
    image_id: str
    filename: str
    content_type: str
    image_base64: str
    offset_x: float
    offset_y: float
    settings: SettingsModel
    queued: int
    generated_at: datetime


class StateSnapshot(BaseModel):
    current: Optional[ImageStub]
    queue: List[ImageStub]
    history: List[ImageStub]
    settings: SettingsModel


class StateManager:
    """Simple in-memory state holder for the web UI."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._images: Dict[str, ImageItem] = {}
        self._queue: List[str] = []
        self._history: List[str] = []
        self._current_id: Optional[str] = None
        self._settings = SettingsModel()

    async def snapshot(self) -> StateSnapshot:
        async with self._lock:
            current = self._serialize_image(self._current_id)
            queue = [
                serialized
                for image_id in self._queue
                if (serialized := self._serialize_image(image_id)) is not None
            ]
            history = [
                serialized
                for image_id in self._history
                if (serialized := self._serialize_image(image_id)) is not None
            ]
            return StateSnapshot(
                current=current,
                queue=queue,
                history=history,
                settings=self._settings.copy(),
            )

    async def add_images(self, files: List[UploadFile]) -> List[ImageItem]:
        items: List[ImageItem] = []
        for file in files:
            data = await file.read()
            await file.close()
            if not data:
                raise HTTPException(status_code=400, detail=f"{file.filename} is empty")
            if file.content_type is None or not file.content_type.startswith("image/"):
                raise HTTPException(status_code=415, detail=f"{file.filename} is not an image")
            item = ImageItem(
                id=uuid4().hex,
                filename=file.filename,
                content_type=file.content_type,
                data=data,
                uploaded_at=datetime.now(timezone.utc),
                offset_x=0.0,
                offset_y=0.0,
            )
            items.append(item)

        async with self._lock:
            for item in items:
                self._images[item.id] = item
                if self._current_id is None:
                    self._current_id = item.id
                else:
                    self._queue.append(item.id)
        return items

    async def remove_from_queue(self, image_id: str) -> None:
        async with self._lock:
            if image_id not in self._queue:
                raise HTTPException(status_code=404, detail="Image not found in queue")
            self._queue = [item for item in self._queue if item != image_id]

    async def reorder_queue(self, order: List[str]) -> None:
        async with self._lock:
            if set(order) != set(self._queue):
                raise HTTPException(status_code=400, detail="Queue order does not match current queue")
            self._queue = order

    async def insert_into_queue(self, image_id: str, index: Optional[int]) -> None:
        async with self._lock:
            if image_id not in self._images:
                raise HTTPException(status_code=404, detail="Image not found")
            target_index = len(self._queue) if index is None else max(0, min(index, len(self._queue)))
            if image_id in self._history:
                self._history = [item for item in self._history if item != image_id]
            if image_id in self._queue:
                self._queue = [item for item in self._queue if item != image_id]
                target_index = max(0, min(target_index, len(self._queue)))
            self._queue.insert(target_index, image_id)

    async def move_to_history(self, image_id: str, index: Optional[int]) -> None:
        async with self._lock:
            if image_id not in self._images:
                raise HTTPException(status_code=404, detail="Image not found")
            if image_id == self._current_id:
                raise HTTPException(status_code=400, detail="Cannot move currently displayed image")
            if image_id in self._queue:
                self._queue = [item for item in self._queue if item != image_id]
            self._history = [item for item in self._history if item != image_id]
            target_index = 0 if index is None else max(0, min(index, len(self._history)))
            self._history.insert(target_index, image_id)
            self._history = self._history[:120]

    async def update_transform(self, image_id: str, transform: ImageTransform) -> ImageStub:
        async with self._lock:
            item = self._images.get(image_id)
            if not item:
                raise HTTPException(status_code=404, detail="Image not found")
            item.offset_x = transform.offset_x
            item.offset_y = transform.offset_y
            return self._serialize_image(image_id)

    async def update_settings(self, update: SettingsUpdate) -> SettingsModel:
        async with self._lock:
            for field, value in update.dict(exclude_unset=True).items():
                setattr(self._settings, field, value)
            return self._settings.copy()

    async def get_image(self, image_id: str) -> ImageItem:
        async with self._lock:
            item = self._images.get(image_id)
        if not item:
            raise HTTPException(status_code=404, detail="Image not found")
        return item

    async def frame_current(self) -> FramePayload:
        async with self._lock:
            self._ensure_current_locked()
            if not self._current_id:
                raise HTTPException(status_code=404, detail="No image available")
            current = self._images[self._current_id]
            payload = FramePayload(
                image_id=current.id,
                filename=current.filename,
                content_type=current.content_type,
                image_base64=base64.b64encode(current.data).decode("ascii"),
                offset_x=current.offset_x,
                offset_y=current.offset_y,
                settings=self._settings.copy(),
                queued=len(self._queue),
                generated_at=datetime.now(timezone.utc),
            )
            return payload

    async def frame_advance(self) -> FramePayload:
        async with self._lock:
            self._ensure_current_locked()
            if not self._current_id:
                raise HTTPException(status_code=404, detail="No image available")
            sequence = [self._current_id] + list(self._queue)
            if not sequence:
                raise HTTPException(status_code=404, detail="No image available")

            if len(sequence) == 1:
                next_id = sequence[0]
                self._queue = []
            else:
                self._history.insert(0, self._current_id)
                self._history = self._history[:120]
                next_id = sequence[1]
                self._queue = sequence[2:] + [sequence[0]]

            if next_id not in self._images:
                raise HTTPException(status_code=500, detail="Next image missing")

            self._current_id = next_id
            current = self._images[next_id]
            return FramePayload(
                image_id=current.id,
                filename=current.filename,
                content_type=current.content_type,
                image_base64=base64.b64encode(current.data).decode("ascii"),
                offset_x=current.offset_x,
                offset_y=current.offset_y,
                settings=self._settings.copy(),
                queued=len(self._queue),
                generated_at=datetime.now(timezone.utc),
            )

    def _serialize_image(self, image_id: Optional[str]) -> Optional[ImageStub]:
        if not image_id:
            return None
        item = self._images.get(image_id)
        if not item:
            return None
        return ImageStub(
            id=item.id,
            filename=item.filename,
            content_type=item.content_type,
            uploaded_at=item.uploaded_at,
            image_url=f"/api/images/{item.id}",
            offset_x=item.offset_x,
            offset_y=item.offset_y,
        )

    def _ensure_current_locked(self) -> None:
        if self._current_id is None and self._queue:
            self._current_id = self._queue.pop(0)


def get_manager() -> StateManager:
    return manager


manager = StateManager()


def create_app() -> FastAPI:
    app = FastAPI(title="Inky Frame Web UI", version="0.1.0")

    static_dir = Path(__file__).parent / "static"
    templates_dir = Path(__file__).parent / "templates"

    app.mount("/static", StaticFiles(directory=static_dir), name="static")
    templates = Jinja2Templates(directory=str(templates_dir))

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request) -> HTMLResponse:
        return templates.TemplateResponse("index.html", {"request": request})

    @app.get("/api/state", response_model=StateSnapshot)
    async def api_state(manager: StateManager = Depends(get_manager)) -> StateSnapshot:
        return await manager.snapshot()

    @app.post("/api/upload")
    async def api_upload(
        files: List[UploadFile] = File(...),
        manager: StateManager = Depends(get_manager),
    ) -> Dict[str, List[Dict[str, str]]]:
        items = await manager.add_images(files)
        return {
            "added": [
                {
                    "id": item.id,
                    "filename": item.filename,
                    "image_url": f"/api/images/{item.id}",
                }
                for item in items
            ]
        }

    @app.delete("/api/queue/{image_id}", status_code=204)
    async def api_queue_remove(image_id: str, manager: StateManager = Depends(get_manager)) -> Response:
        await manager.remove_from_queue(image_id)
        return Response(status_code=204)

    @app.post("/api/queue/reorder", status_code=204)
    async def api_queue_reorder(
        payload: QueueOrder,
        manager: StateManager = Depends(get_manager),
    ) -> Response:
        await manager.reorder_queue(payload.image_ids)
        return Response(status_code=204)

    @app.post("/api/queue/insert", status_code=204)
    async def api_queue_insert(
        payload: QueueInsert,
        manager: StateManager = Depends(get_manager),
    ) -> Response:
        await manager.insert_into_queue(payload.image_id, payload.index)
        return Response(status_code=204)

    @app.post("/api/history/insert", status_code=204)
    async def api_history_insert(
        payload: QueueInsert,
        manager: StateManager = Depends(get_manager),
    ) -> Response:
        await manager.move_to_history(payload.image_id, payload.index)
        return Response(status_code=204)

    @app.post("/api/settings", response_model=SettingsModel)
    async def api_settings(
        update: SettingsUpdate,
        manager: StateManager = Depends(get_manager),
    ) -> SettingsModel:
        return await manager.update_settings(update)

    @app.get("/api/images/{image_id}")
    async def api_image(image_id: str, manager: StateManager = Depends(get_manager)) -> Response:
        item = await manager.get_image(image_id)
        return Response(content=item.data, media_type=item.content_type)

    @app.get("/api/frame/current", response_model=FramePayload)
    async def api_frame_current(manager: StateManager = Depends(get_manager)) -> FramePayload:
        return await manager.frame_current()

    @app.post("/api/frame/advance", response_model=FramePayload)
    async def api_frame_advance(manager: StateManager = Depends(get_manager)) -> FramePayload:
        return await manager.frame_advance()

    @app.put("/api/images/{image_id}/transform", response_model=ImageStub)
    async def api_image_transform(
        image_id: str,
        payload: ImageTransform,
        manager: StateManager = Depends(get_manager),
    ) -> ImageStub:
        return await manager.update_transform(image_id, payload)

    return app


app = create_app()
