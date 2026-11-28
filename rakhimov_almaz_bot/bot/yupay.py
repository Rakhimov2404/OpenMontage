"""Yupay reseller API bilan ishlash.

Ma'lum bo'lganlar (Yupay sozlamalar sahifasidan):
  * Har bir so'rovda:  Authorization: Bearer <API kalit>
  * Vebhuk imzosi:     X-Yupay-Key-Signature = HMAC-SHA256(API kalit, so'rov tanasi)

Endpoint yo'llari va javob maydonlari Yupay API hujjatiga qarab .env orqali
to'g'rilanadi (YUPAY_PATH_*). Javobdan ID va holatni olish uchun bir nechta
keng tarqalgan maydon nomlari tekshiriladi.
"""
import hashlib
import hmac
import logging

import aiohttp

import config

log = logging.getLogger("yupay")


class YupayError(Exception):
    pass


class YupayClient:
    def __init__(self):
        self._session: aiohttp.ClientSession | None = None

    async def _s(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                base_url=config.YUPAY_BASE_URL + "/",
                headers={
                    "Authorization": f"Bearer {config.YUPAY_API_KEY}",
                    "Accept": "application/json",
                },
                timeout=aiohttp.ClientTimeout(total=30),
            )
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    async def _request(self, method: str, path: str, **kw):
        s = await self._s()
        async with s.request(method, path.lstrip("/"), **kw) as r:
            try:
                data = await r.json(content_type=None)
            except Exception:
                data = {"raw": (await r.text())[:500]}
            if r.status >= 400:
                log.warning("Yupay %s %s -> %s %s", method, path, r.status, data)
                raise YupayError(f"HTTP {r.status}: {data}")
            return data

    async def balance(self):
        return await self._request("GET", config.YUPAY_PATH_BALANCE)

    async def products(self):
        return await self._request("GET", config.YUPAY_PATH_PRODUCTS)

    async def create_order(self, product_id: str, player_id: str, reference: str):
        """reference — bizning buyurtma raqami: bir buyurtma ikki marta yuborilmasligi uchun."""
        body = {
            "product_id": product_id,
            config.YUPAY_PLAYER_FIELD: player_id,
            "reference": reference,
        }
        return await self._request(
            "POST",
            config.YUPAY_PATH_CREATE_ORDER,
            json=body,
            headers={"Idempotency-Key": reference},
        )

    async def get_order(self, order_id: str):
        return await self._request("GET", config.YUPAY_PATH_ORDER.format(order_id=order_id))


def _unwrap(data):
    if isinstance(data, dict) and isinstance(data.get("data"), dict):
        return data["data"]
    return data if isinstance(data, dict) else {}


def extract_order_id(data) -> str | None:
    d = _unwrap(data)
    for k in ("id", "order_id", "orderId", "uuid"):
        if d.get(k):
            return str(d[k])
    if isinstance(d.get("order"), dict):
        return extract_order_id(d["order"])
    return None


def extract_status(data) -> str:
    d = _unwrap(data)
    if isinstance(d.get("order"), dict):
        d = d["order"]
    return str(d.get("status") or d.get("state") or "").lower()


def extract_reference(data) -> str | None:
    d = _unwrap(data)
    if isinstance(d.get("order"), dict):
        d = d["order"]
    for k in ("reference", "external_id", "externalId", "client_order_id"):
        if d.get(k):
            return str(d[k])
    return None


SUCCESS = {"completed", "success", "succeeded", "done", "delivered", "paid", "fulfilled"}
FAILED = {"failed", "error", "canceled", "cancelled", "rejected", "refunded"}


def verify_signature(raw_body: bytes, header_value: str | None) -> bool:
    if not header_value:
        return False
    sig = header_value.strip()
    if sig.lower().startswith("sha256="):
        sig = sig[7:]
    expected = hmac.new(config.YUPAY_API_KEY.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, sig.lower())
