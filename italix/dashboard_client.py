"""Typed-enough HTTP client used by the Streamlit dashboard."""

from __future__ import annotations

import os
from typing import Any

import httpx


class DashboardAPIError(RuntimeError):
    pass


class DashboardClient:
    def __init__(self, base_url: str, timeout: float = 1800, token: str | None = None):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.token = token or os.getenv("ITALIX_OPERATOR_TOKEN", "")

    def request(self, method: str, path: str, **kwargs) -> Any:
        if path.startswith("/v1/"):
            if not self.token:
                raise DashboardAPIError("ITALIX operator authentication is not configured")
            headers = dict(kwargs.pop("headers", {}) or {})
            headers["Authorization"] = f"Bearer {self.token}"
            kwargs["headers"] = headers
        try:
            response = httpx.request(
                method, f"{self.base_url}{path}", timeout=self.timeout, **kwargs
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            try:
                detail = exc.response.json().get("detail", exc.response.text)
            except ValueError:
                detail = exc.response.text
            raise DashboardAPIError(str(detail)) from exc
        except httpx.HTTPError as exc:
            raise DashboardAPIError(f"Gateway unavailable: {exc}") from exc
        return response.json()

    def get(self, path: str, **params) -> Any:
        return self.request("GET", path, params=params or None)

    def post(self, path: str, payload: dict | None = None) -> Any:
        return self.request("POST", path, json=payload)
