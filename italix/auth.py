"""Bearer-token authentication and role authorization for the local API."""

from __future__ import annotations

import hmac
import os
from dataclasses import dataclass

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer


_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class BearerAuthorizer:
    viewer_token: str
    operator_token: str

    @classmethod
    def from_environment(
        cls, viewer_token: str | None = None, operator_token: str | None = None
    ) -> "BearerAuthorizer":
        viewer = viewer_token or os.getenv("ITALIX_VIEWER_TOKEN", "")
        operator = operator_token or os.getenv("ITALIX_OPERATOR_TOKEN", "")
        if not viewer or not operator:
            raise RuntimeError(
                "ITALIX_VIEWER_TOKEN and ITALIX_OPERATOR_TOKEN must be configured"
            )
        if any(token != token.strip() or len(token) < 32 for token in (viewer, operator)):
            raise RuntimeError("ITALIX bearer tokens must be at least 32 characters without whitespace")
        if hmac.compare_digest(viewer, operator):
            raise RuntimeError("viewer and operator tokens must be different")
        return cls(viewer, operator)

    def _role(self, credentials: HTTPAuthorizationCredentials | None) -> str:
        if credentials is None or credentials.scheme.lower() != "bearer":
            raise HTTPException(
                status_code=401,
                detail="Bearer token required",
                headers={"WWW-Authenticate": "Bearer"},
            )
        supplied = credentials.credentials
        if hmac.compare_digest(supplied, self.operator_token):
            return "operator"
        if hmac.compare_digest(supplied, self.viewer_token):
            return "viewer"
        raise HTTPException(
            status_code=401,
            detail="Invalid bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    def require_viewer(
        self, credentials: HTTPAuthorizationCredentials | None = Depends(_bearer)
    ) -> str:
        return self._role(credentials)

    def require_operator(
        self, credentials: HTTPAuthorizationCredentials | None = Depends(_bearer)
    ) -> str:
        role = self._role(credentials)
        if role != "operator":
            raise HTTPException(status_code=403, detail="Operator role required")
        return role
