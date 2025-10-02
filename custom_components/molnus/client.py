# custom_components/molnus/client.py
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional
import httpx

class MolnusAuthError(Exception):
    """Raised when authentication fails."""

def _parse_iso(dt: Optional[str]) -> Optional[datetime]:
    if not dt:
        return None
    if dt.endswith("Z"):
        dt = dt[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(dt)
    except Exception:
        return None

@dataclass
class SimplePrediction:
    label: Optional[str]
    accuracy: Optional[int]

    @classmethod
    def from_dict(cls, src: Dict[str, Any]) -> "SimplePrediction":
        return cls(
            label=src.get("label"),
            accuracy=src.get("accuracy"),
        )

@dataclass
class SimpleImage:
    id: Optional[int]
    captureDate: Optional[datetime]
    url: Optional[str]
    predictions: List[SimplePrediction]

    @classmethod
    def from_dict(cls, src: Dict[str, Any]) -> "SimpleImage":
        preds = [SimplePrediction.from_dict(p) for p in src.get("ImagePredictions", [])]
        return cls(
            id=src.get("id"),
            captureDate=_parse_iso(src.get("captureDate")),
            url=src.get("url"),
            predictions=preds,
        )

@dataclass
class ImagesResponseSimple:
    success: bool
    images: List[SimpleImage]
    hasMore: bool

    @classmethod
    def from_dict(cls, src: Dict[str, Any]) -> "ImagesResponseSimple":
        imgs = [SimpleImage.from_dict(i) for i in src.get("images", [])]
        return cls(
            success=bool(src.get("success", False)),
            images=imgs,
            hasMore=bool(src.get("hasMore", False)),
        )

class MolnusClient:
    """Enkel async-klient för Molnus (login + get_images)."""

    def __init__(self, email: str, password: str, headers: Optional[Dict[str, str]] = None):
        self.email = email
        self.password = password
        self._client = httpx.AsyncClient(timeout=20.0)
        self._token: Optional[str] = None
        self._headers: Dict[str, str] = headers or {
            "accept": "application/json, text/plain, */*",
            "content-type": "application/json",
            "origin": "https://molnus.com",
            "user-agent": "HomeAssistantMolnusIntegration/0.1"
        }

    async def close(self) -> None:
        await self._client.aclose()

    async def login(self) -> None:
        payload = {"email": self.email, "password": self.password}
        resp = await self._client.post("https://molnus.com/auth/token", json=payload, headers=self._headers)
        if resp.status_code >= 400:
            raise MolnusAuthError(f"Login failed: {resp.status_code} {resp.text}")
        data = resp.json()
        token = data.get("access_token") or data.get("token") or data.get("accessToken")
        if not token:
            raise MolnusAuthError("No access_token found in response")
        self._token = token

    async def _ensure_auth(self) -> None:
        if not self._token:
            await self.login()

    async def get_images(
        self,
        camera_id: str,
        offset: int = 0,
        limit: int = 50,
        wildlife_required: bool = False,
    ) -> ImagesResponseSimple:
        """Hämta bilder och returnera förenklade dataklasser (captureDate, url, label, accuracy)."""
        await self._ensure_auth()
        params = {
            "CameraId": camera_id,
            "offset": str(offset),
            "limit": str(limit),
            "wildlifeRequired": "true" if wildlife_required else "false",
        }
        headers = {**self._headers, "Authorization": f"Bearer {self._token}", "accept": "application/json, text/plain, */*"}
        resp = await self._client.get("https://molnus.com/images/get", params=params, headers=headers)

        if resp.status_code == 401:
            # försök logga in igen en gång
            await self.login()
            headers["Authorization"] = f"Bearer {self._token}"
            resp = await self._client.get("https://molnus.com/images/get", params=params, headers=headers)

        resp.raise_for_status()
        data = resp.json()
        return ImagesResponseSimple.from_dict(data)
