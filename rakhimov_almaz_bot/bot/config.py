import json
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _req(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f".env faylda {name} to'ldirilmagan")
    return value


BOT_TOKEN = _req("BOT_TOKEN")
ADMIN_IDS = {int(x) for x in os.getenv("ADMIN_IDS", "").replace(" ", "").split(",") if x}
PAY_CARD = os.getenv("PAY_CARD", "")
PAY_CARD_OWNER = os.getenv("PAY_CARD_OWNER", "")

YUPAY_API_KEY = _req("YUPAY_API_KEY")
YUPAY_BASE_URL = os.getenv("YUPAY_BASE_URL", "https://reseller.yupay.uz/api/v1").rstrip("/")
YUPAY_PATH_BALANCE = os.getenv("YUPAY_PATH_BALANCE", "/balance")
YUPAY_PATH_PRODUCTS = os.getenv("YUPAY_PATH_PRODUCTS", "/products")
YUPAY_PATH_CREATE_ORDER = os.getenv("YUPAY_PATH_CREATE_ORDER", "/orders")
YUPAY_PATH_ORDER = os.getenv("YUPAY_PATH_ORDER", "/orders/{order_id}")
YUPAY_PLAYER_FIELD = os.getenv("YUPAY_PLAYER_FIELD", "player_id")

WEBHOOK_HOST = os.getenv("WEBHOOK_HOST", "0.0.0.0")
WEBHOOK_PORT = int(os.getenv("WEBHOOK_PORT", "8080"))
WEBHOOK_PATH = os.getenv("WEBHOOK_PATH", "/yupay/webhook")

DB_PATH = BASE_DIR / "orders.db"


def load_products() -> dict:
    with open(BASE_DIR / "products.json", encoding="utf-8") as f:
        data = json.load(f)
    items = {}
    for cat in data["categories"]:
        for item in cat["items"]:
            items[item["key"]] = item
    return {"categories": data["categories"], "items": items}
