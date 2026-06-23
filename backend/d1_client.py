"""Cloudflare D1 HTTP API 用戶端。"""

from __future__ import annotations

import os
from typing import Any

import httpx

from backend.cloudflare_config import d1_enabled

_API_BASE = "https://api.cloudflare.com/client/v4"


class D1Error(RuntimeError):
    pass


class D1Client:
    def __init__(
        self,
        account_id: str,
        database_id: str,
        api_token: str,
    ) -> None:
        self.account_id = account_id
        self.database_id = database_id
        self.api_token = api_token

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
        }

    @staticmethod
    def _bind_params(params: tuple[Any, ...] | list[Any] | None) -> list[Any] | None:
        if not params:
            return None
        bound: list[Any] = []
        for value in params:
            if value is None:
                bound.append(None)
            elif isinstance(value, bool):
                bound.append(1 if value else 0)
            else:
                bound.append(value)
        return bound

    async def query(self, sql: str, params: tuple[Any, ...] | list[Any] | None = None) -> dict:
        url = f"{_API_BASE}/accounts/{self.account_id}/d1/database/{self.database_id}/query"
        payload: dict[str, Any] = {"sql": sql}
        bound = self._bind_params(params)
        if bound is not None:
            payload["params"] = bound

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, headers=self._headers(), json=payload)
            data = response.json()

        if not response.is_success or not data.get("success"):
            errors = data.get("errors") or [{"message": response.text}]
            message = "; ".join(str(item.get("message", item)) for item in errors)
            raise D1Error(message)

        results = data.get("result") or []
        if not results:
            return {"results": [], "meta": {}}
        return results[0]

    async def fetchall(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        payload = await self.query(sql, params)
        rows = payload.get("results") or []
        return [dict(row) for row in rows]

    async def fetchone(self, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
        rows = await self.fetchall(sql, params)
        return rows[0] if rows else None

    async def execute(self, sql: str, params: tuple[Any, ...] = ()) -> tuple[int, int]:
        payload = await self.query(sql, params)
        meta = payload.get("meta") or {}
        return int(meta.get("last_row_id") or 0), int(meta.get("changes") or 0)

    async def executescript(self, sql: str) -> None:
        statements = [part.strip() for part in sql.split(";") if part.strip()]
        for statement in statements:
            await self.query(statement)


_client: D1Client | None = None


def get_d1_client() -> D1Client:
    global _client
    if _client is None:
        if not d1_enabled():
            raise D1Error("D1 未設定，請填入 CF_ACCOUNT_ID、CF_API_TOKEN、CF_D1_DATABASE_ID")
        _client = D1Client(
            account_id=os.environ["CF_ACCOUNT_ID"].strip(),
            database_id=os.environ["CF_D1_DATABASE_ID"].strip(),
            api_token=os.environ["CF_API_TOKEN"].strip(),
        )
    return _client
