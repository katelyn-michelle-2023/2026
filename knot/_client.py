"""
Shared Knot API auth helpers.
Knot uses HTTP Basic Auth: base64(client_id:secret).
"""

import base64

import httpx

from config import KNOT_BASE_URL, KNOT_CLIENT_ID, KNOT_SECRET


def _auth_header() -> str:
    credentials = f"{KNOT_CLIENT_ID}:{KNOT_SECRET}"
    encoded = base64.b64encode(credentials.encode()).decode()
    return f"Basic {encoded}"


def knot_client(timeout: float = 30.0) -> httpx.AsyncClient:
    """Return an async HTTP client pre-configured for the Knot API."""
    return httpx.AsyncClient(
        base_url=KNOT_BASE_URL,
        headers={
            "Authorization": _auth_header(),
            "Content-Type": "application/json",
        },
        timeout=timeout,
    )


async def create_session(session_type: str, external_user_id: str) -> str:
    """
    Create a Knot session for the given product type and user.
    Returns the session string to pass into the frontend SDK.
    """
    async with knot_client() as client:
        resp = await client.post(
            "/session/create",
            json={"type": session_type, "external_user_id": external_user_id},
        )
        resp.raise_for_status()
        return resp.json()["session"]
