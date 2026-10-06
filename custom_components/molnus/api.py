"""Async API-klient för Molnus (inofficiellt API, härlett från Android-appen v4.1.25)."""
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Awaitable, Callable, Optional

import aiohttp

from .const import API_BASE, WS_URL

_LOGGER = logging.getLogger(__name__)

WS_BACKOFF_MIN = 2
WS_BACKOFF_MAX = 30


class MolnusError(Exception):
    """Basfel för Molnus."""


class MolnusAuthError(MolnusError):
    """Inloggning misslyckades."""


class MolnusConnectionError(MolnusError):
    """Nätverks- eller serverfel."""


def _parse_iso_to_dt(iso: Optional[str]) -> Optional[datetime]:
    """Tolerant ISO -> datetime parser. Hanterar trailing Z."""
    if not iso or not isinstance(iso, str):
        return None
    try:
        return datetime.fromisoformat(iso[:-1] + "+00:00" if iso.endswith("Z") else iso)
    except ValueError:
        try:
            return datetime.fromisoformat(iso.split(".")[0].replace("Z", ""))
        except ValueError:
            return None


def _first(d: dict, *keys: str) -> Any:
    """Första icke-tomma värdet bland nycklarna (API:t blandar versaler/gemener)."""
    for k in keys:
        v = d.get(k)
        if v not in (None, ""):
            return v
    return None


@dataclass
class ImagePrediction:
    label: Optional[str]
    accuracy: Optional[float]

    @staticmethod
    def from_json(j: dict) -> "ImagePrediction":
        return ImagePrediction(label=_first(j, "label", "Label"), accuracy=_first(j, "accuracy", "Accuracy"))


@dataclass
class ImageItem:
    id: Optional[str]
    camera_id: Optional[str]
    capture_date: Optional[datetime]
    url: Optional[str]
    thumbnail_url: Optional[str]
    predictions: list[ImagePrediction] = field(default_factory=list)

    @staticmethod
    def from_json(j: dict) -> "ImageItem":
        preds_raw = _first(j, "ImagePredictions", "imagePredictions", "predictions") or []
        image_id = j.get("id")
        return ImageItem(
            id=str(image_id) if image_id is not None else None,
            camera_id=_first(j, "CameraId", "cameraId"),
            capture_date=_parse_iso_to_dt(j.get("captureDate")),
            url=j.get("url"),
            thumbnail_url=j.get("thumbnailUrl"),
            predictions=[ImagePrediction.from_json(p) for p in preds_raw if isinstance(p, dict)],
        )

    @property
    def top_prediction(self) -> Optional[ImagePrediction]:
        scored = [p for p in self.predictions if p.label]
        if not scored:
            return None
        return max(scored, key=lambda p: p.accuracy or 0)


@dataclass
class Camera:
    id: str
    name: str
    shared: bool = False
    imei: Optional[str] = None
    model: Optional[str] = None
    status: dict = field(default_factory=dict)  # Signal, Battery, TempC m.m. (strängar)

    @staticmethod
    def from_json(j: dict, *, shared: bool = False) -> Optional["Camera"]:
        # Delade kameror kan ligga nästlade under "camera"
        inner = j.get("camera") if isinstance(j.get("camera"), dict) else j
        cam_id = _first(inner, "id", "Id") or _first(j, "CameraId", "cameraId")
        if not cam_id:
            return None
        model = inner.get("cameraModel")
        status = inner.get("status")
        if isinstance(status, str):
            try:
                status = json.loads(status)
            except ValueError:
                status = {}
        return Camera(
            id=str(cam_id),
            name=str(_first(inner, "description", "name", "cameraDescription", "cameraImei") or cam_id),
            shared=shared,
            imei=_first(inner, "cameraImei", "imei"),
            model=_first(model, "modelName") if isinstance(model, dict) else None,
            status=status if isinstance(status, dict) else {},
        )


class MolnusApi:
    """Klient för REST + WebSocket. Använder HA:s delade aiohttp-session."""

    def __init__(self, session: aiohttp.ClientSession, email: str, password: str) -> None:
        self._session = session
        self._email = email
        self._password = password
        self._token: Optional[str] = None
        self._login_lock = asyncio.Lock()
        # Sätts när Molnus avvisar lösenordet. Stoppar fler inloggningsförsök (risk för kontospärr)
        # tills användaren loggat in igen via reauth, som skapar en ny klient.
        self._auth_failed = False

    @property
    def token(self) -> Optional[str]:
        return self._token

    async def login(self) -> None:
        try:
            async with self._session.post(
                f"{API_BASE}/auth/token",
                json={"email": self._email, "password": self._password},
                timeout=aiohttp.ClientTimeout(total=20),
            ) as resp:
                if resp.status in (400, 401, 403):
                    self._auth_failed = True
                    raise MolnusAuthError("unauthorized")
                if resp.status >= 400:
                    raise MolnusConnectionError(f"login HTTP {resp.status}")
                data = await resp.json(content_type=None)
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            raise MolnusConnectionError(str(exc)) from exc
        except ValueError as exc:  # t.ex. underhållssida i stället för JSON
            raise MolnusConnectionError("invalid_json") from exc

        token = (data.get("token") or {}).get("accessToken") if isinstance(data, dict) else None
        if not token:
            raise MolnusAuthError("no_token")
        self._token = token

    async def _relogin(self, stale_token: Optional[str]) -> None:
        async with self._login_lock:
            if self._auth_failed:
                raise MolnusAuthError("unauthorized")
            if self._token == stale_token:  # ingen annan hann logga in under tiden
                await self.login()

    async def _get(self, path: str, params: Optional[dict] = None) -> Any:
        if not self._token:
            await self._relogin(None)
        for attempt in (1, 2):
            used_token = self._token
            try:
                async with self._session.get(
                    f"{API_BASE}{path}",
                    params=params,
                    headers={"Authorization": f"Bearer {used_token}"},
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    if resp.status == 401 and attempt == 1:
                        await self._relogin(used_token)
                        continue
                    if resp.status == 401:
                        raise MolnusAuthError("unauthorized")
                    if resp.status >= 400:
                        raise MolnusConnectionError(f"GET {path} HTTP {resp.status}")
                    return await resp.json(content_type=None)
            except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                raise MolnusConnectionError(str(exc)) from exc
            except ValueError as exc:
                raise MolnusConnectionError(f"GET {path}: invalid_json") from exc
        raise MolnusConnectionError("unreachable")

    async def get_cameras(self) -> list[Camera]:
        """Egna + delade kameror."""
        own = await self._get("/cameras/images")
        cameras: dict[str, Camera] = {}
        for item in (own or {}).get("cameras") or []:
            if isinstance(item, dict) and (cam := Camera.from_json(item)):
                cameras[cam.id] = cam
        # Logga bara antal: rå JSON innehåller IMEI och delande användares e-post
        _LOGGER.debug("Molnus: %d egna kameror", len(cameras))

        try:
            shared = await self._get("/cameras/share/list")
        except MolnusConnectionError:
            _LOGGER.warning("Molnus: kunde inte hämta delade kameror", exc_info=True)
            shared = {}
        for item in (shared or {}).get("sharedCameras") or []:
            if isinstance(item, dict) and (cam := Camera.from_json(item, shared=True)):
                cameras.setdefault(cam.id, cam)
        _LOGGER.debug("Molnus: %d kameror totalt inkl. delade", len(cameras))
        return list(cameras.values())

    async def get_images(self, camera_id: str, limit: int = 10) -> list[ImageItem]:
        """Senaste bilderna, nyast först."""
        data = await self._get(
            "/images",
            {"cameraId": camera_id, "offset": 0, "limit": limit},
        )
        raw = _first(data, "images", "Images") if isinstance(data, dict) else None
        images = [ImageItem.from_json(i) for i in raw or [] if isinstance(i, dict)]
        images.sort(key=lambda i: i.capture_date.timestamp() if i.capture_date else 0, reverse=True)
        return images

    async def listen(
        self,
        on_image_upload: Callable[[Optional[str]], Awaitable[None]],
        on_reconnected: Callable[[], Awaitable[None]],
        on_auth_failed: Callable[[], None],
    ) -> None:
        """Lyssna på WebSocket tills tasken avbryts eller inloggningen slutar fungera."""
        backoff = WS_BACKOFF_MIN
        accepted_before = False
        while True:
            token = self._token
            try:
                if not token:
                    await self._relogin(None)
                    token = self._token
                async with self._session.ws_connect(f"{WS_URL}?token={token}", heartbeat=30) as ws:
                    async for msg in ws:
                        if msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                            break
                        if msg.type != aiohttp.WSMsgType.TEXT:
                            continue
                        msg_type, camera_id = self._parse_ws_message(msg.data)
                        if msg_type == "ACCEPTED":
                            # Nollställ backoff först när servern godkänt anslutningen, annars kan
                            # en server som stänger direkt ge en ny anslutning var 2:a sekund
                            backoff = WS_BACKOFF_MIN
                            if accepted_before:
                                await on_reconnected()  # hämta bilder som kom medan vi var nere
                            accepted_before = True
                        elif msg_type == "ImageUpload":
                            await on_image_upload(camera_id)
                    if ws.close_code == 4001:  # token ogiltig
                        await self._relogin(token)
            except asyncio.CancelledError:
                raise
            except MolnusAuthError:
                _LOGGER.warning("Molnus: inloggningen fungerar inte längre, WebSocket stoppas tills du loggat in igen")
                on_auth_failed()
                return
            except Exception as exc:  # noqa: BLE001 - lyssnaren får aldrig dö
                # Logga inte själva felet: aiohttp-fel kan innehålla URL:en med token
                _LOGGER.debug("Molnus: WebSocket fel: %s", type(exc).__name__)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, WS_BACKOFF_MAX)

    @staticmethod
    def _parse_ws_message(raw: str) -> tuple[Optional[str], Optional[str]]:
        """Returnerar (typ, kamera-id) där typ är "ACCEPTED", "ImageUpload" eller None."""
        try:
            msg = json.loads(raw)
        except ValueError:
            return None, None
        if not isinstance(msg, dict):
            return None, None
        if msg.get("type") == "ACCEPTED":
            return "ACCEPTED", None
        data = msg.get("data")
        if msg.get("type") != "NOTIFICATION" or not isinstance(data, dict):
            return None, None
        ntype = (data.get("notificationType") or {}).get("name") or str(data.get("groupKey") or "").split(":")[0]
        if ntype != "ImageUpload":
            return None, None
        payload = data.get("payload")
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except ValueError:
                payload = {}
        camera_id = _first(payload, "cameraId", "CameraId") if isinstance(payload, dict) else None
        return "ImageUpload", str(camera_id) if camera_id else None
