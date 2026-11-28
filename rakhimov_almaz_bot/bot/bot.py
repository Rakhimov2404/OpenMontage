"""Rakhimov ALMAZ bot — Free Fire olmoslarini Yupay orqali avtomatik yetkazish.

Jarayon:
  1. Mijoz paketni tanlaydi va Free Fire ID'sini yozadi.
  2. Kartaga pul o'tkazib, chek rasmini yuboradi.
  3. Admin chekni tasdiqlaydi -> bot Yupay'ga buyurtma yuboradi.
  4. Yupay vebhuk orqali natijani yuboradi -> bot mijozga xabar beradi.
"""
import asyncio
import html
import json
import logging

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup,
                           KeyboardButton, Message, ReplyKeyboardMarkup)
from aiohttp import web

import config
import db
import yupay

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("bot")

PRODUCTS = config.load_products()
client = yupay.YupayClient()
router = Router()

BTN_BUY = "💎 Almaz sotib olish"
BTN_ORDERS = "📦 Buyurtmalarim"
BTN_HELP = "☎️ Yordam"

STATUS_UZ = {
    "awaiting_payment": "⏳ To'lov kutilmoqda",
    "payment_sent": "🧾 Chek tekshirilmoqda",
    "processing": "⚙️ Bajarilmoqda",
    "completed": "✅ Bajarildi",
    "failed": "❌ Xatolik (admin bog'lanadi)",
    "rejected": "🚫 Rad etildi",
}


class Buy(StatesGroup):
    player_id = State()
    receipt = State()


def money(x: int) -> str:
    return f"{x:,}".replace(",", " ") + " so'm"


def main_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=BTN_BUY)], [KeyboardButton(text=BTN_ORDERS), KeyboardButton(text=BTN_HELP)]],
        resize_keyboard=True,
    )


def is_admin(uid: int) -> bool:
    return uid in config.ADMIN_IDS


async def notify_admins(bot: Bot, text: str, **kw):
    for aid in config.ADMIN_IDS:
        try:
            await bot.send_message(aid, text, **kw)
        except Exception as e:  # admin botni bloklagan bo'lishi mumkin
            log.warning("admin %s ga yuborilmadi: %s", aid, e)


# ---------------- Mijoz qismi ----------------

@router.message(CommandStart())
async def start(m: Message, state: FSMContext):
    await state.clear()
    await m.answer(
        "💎 <b>RAKHIMOV ALMAZ BOT</b>\n\n"
        "🔥 Free Fire olmoslari — arzon va tez\n"
        "⚡ Tezkor yetkazib berish\n"
        "🛡 Ishonchli xizmat\n\n"
        "Pastdagi tugmalardan foydalaning 👇",
        reply_markup=main_kb(),
    )


@router.message(F.text == BTN_HELP)
async def help_(m: Message):
    await m.answer("Savollar bo'yicha adminga yozing. Buyurtma raqamingizni ham yuboring.")


@router.message(F.text == BTN_BUY)
async def buy(m: Message, state: FSMContext):
    await state.clear()
    kb = [[InlineKeyboardButton(text=c["title"], callback_data=f"cat:{i}")]
          for i, c in enumerate(PRODUCTS["categories"])]
    await m.answer("Bo'limni tanlang 👇", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))


@router.callback_query(F.data.startswith("cat:"))
async def category(c: CallbackQuery):
    cat = PRODUCTS["categories"][int(c.data.split(":")[1])]
    kb = [[InlineKeyboardButton(text=f"{it['name']} — {money(it['price'])}", callback_data=f"item:{it['key']}")]
          for it in cat["items"]]
    kb.append([InlineKeyboardButton(text="⬅️ Orqaga", callback_data="back")])
    await c.message.edit_text(f"{cat['title']}\nKerakli paketni tanlang 👇",
                              reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await c.answer()


@router.callback_query(F.data == "back")
async def back(c: CallbackQuery):
    kb = [[InlineKeyboardButton(text=cat["title"], callback_data=f"cat:{i}")]
          for i, cat in enumerate(PRODUCTS["categories"])]
    await c.message.edit_text("Bo'limni tanlang 👇", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await c.answer()


@router.callback_query(F.data.startswith("item:"))
async def item(c: CallbackQuery, state: FSMContext):
    key = c.data.split(":", 1)[1]
    product = PRODUCTS["items"].get(key)
    if not product:
        return await c.answer("Mahsulot topilmadi", show_alert=True)
    await state.set_state(Buy.player_id)
    await state.update_data(product_key=key)
    await c.message.answer(
        f"Siz tanladingiz: <b>{product['name']}</b> — {money(product['price'])}\n\n"
        "🆔 Free Fire <b>ID</b> raqamingizni yozing (faqat raqamlar):"
    )
    await c.answer()


@router.message(Buy.player_id)
async def got_player_id(m: Message, state: FSMContext):
    pid = (m.text or "").strip().replace(" ", "")
    if not pid.isdigit() or not 5 <= len(pid) <= 13:
        return await m.answer("❗ ID noto'g'ri. Faqat raqam yozing, masalan: 123456789")
    data = await state.get_data()
    product = PRODUCTS["items"][data["product_key"]]
    order_id = db.create_order(m.from_user.id, m.from_user.username, product, pid)
    await state.set_state(Buy.receipt)
    await state.update_data(order_id=order_id)
    await m.answer(
        f"🧾 Buyurtma <b>#{order_id}</b>\n"
        f"📦 {product['name']}\n🆔 ID: <code>{pid}</code>\n💰 {money(product['price'])}\n\n"
        f"💳 Shu kartaga to'lang:\n<code>{config.PAY_CARD}</code>\n{html.escape(config.PAY_CARD_OWNER)}\n\n"
        "To'lovdan so'ng <b>chek rasmini</b> shu yerga yuboring 📸"
    )


@router.message(Buy.receipt, F.photo | F.document)
async def got_receipt(m: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    order_id = data["order_id"]
    if not db.set_status_if(order_id, "awaiting_payment", "payment_sent"):
        await state.clear()
        return await m.answer("Bu buyurtma uchun chek allaqachon yuborilgan.")
    await state.clear()
    o = db.get(order_id)
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"ok:{order_id}"),
        InlineKeyboardButton(text="🚫 Rad etish", callback_data=f"no:{order_id}"),
    ]])
    caption = (f"🆕 Buyurtma <b>#{order_id}</b>\n"
               f"👤 {html.escape(m.from_user.full_name)} (@{m.from_user.username or '-'}, <code>{m.from_user.id}</code>)\n"
               f"📦 {o['product_name']}\n🆔 FF ID: <code>{o['player_id']}</code>\n💰 {money(o['price'])}")
    for aid in config.ADMIN_IDS:
        try:
            await m.copy_to(aid)
            await bot.send_message(aid, caption, reply_markup=kb)
        except Exception as e:
            log.warning("admin %s ga chek yuborilmadi: %s", aid, e)
    await m.answer("✅ Chek qabul qilindi. Admin tekshirgach olmoslar avtomatik tushadi.", reply_markup=main_kb())


@router.message(Buy.receipt)
async def receipt_wrong(m: Message):
    await m.answer("📸 Iltimos, to'lov chekining rasmini yuboring.")


@router.message(F.text == BTN_ORDERS)
async def my_orders(m: Message):
    rows = db.user_orders(m.from_user.id)
    if not rows:
        return await m.answer("Sizda hali buyurtma yo'q.")
    lines = [f"#{r['id']} · {r['product_name']} · {STATUS_UZ.get(r['status'], r['status'])}" for r in rows]
    await m.answer("📦 Oxirgi buyurtmalaringiz:\n\n" + "\n".join(lines))


# ---------------- Admin qismi ----------------

@router.callback_query(F.data.startswith("no:"))
async def reject(c: CallbackQuery, bot: Bot):
    if not is_admin(c.from_user.id):
        return await c.answer()
    order_id = int(c.data.split(":")[1])
    if not db.set_status_if(order_id, "payment_sent", "rejected"):
        return await c.answer("Bu buyurtma allaqachon ko'rib chiqilgan", show_alert=True)
    o = db.get(order_id)
    await bot.send_message(o["user_id"], f"🚫 Buyurtma #{order_id} rad etildi. Savol bo'lsa adminga yozing.")
    await c.message.edit_text(c.message.html_text + "\n\n🚫 Rad etildi")
    await c.answer()


@router.callback_query(F.data.startswith("ok:"))
async def approve(c: CallbackQuery, bot: Bot):
    if not is_admin(c.from_user.id):
        return await c.answer()
    order_id = int(c.data.split(":")[1])
    # Ikki marta bosilsa ham Yupay'ga faqat bir marta yuboriladi
    if not db.set_status_if(order_id, "payment_sent", "processing"):
        return await c.answer("Bu buyurtma allaqachon ko'rib chiqilgan", show_alert=True)
    o = db.get(order_id)
    product = PRODUCTS["items"].get(o["product_key"])
    await c.answer("Yupay'ga yuborilmoqda…")
    try:
        resp = await client.create_order(product["yupay_id"], o["player_id"], reference=f"RA-{order_id}")
    except Exception as e:
        db.update(order_id, status="failed", note=str(e)[:500])
        await c.message.edit_text(c.message.html_text + f"\n\n❌ Yupay xatosi:\n<code>{html.escape(str(e)[:300])}</code>")
        await bot.send_message(o["user_id"], f"⚠️ Buyurtma #{order_id} bo'yicha texnik muammo. Admin tez orada bog'lanadi.")
        return
    yid = yupay.extract_order_id(resp)
    status = yupay.extract_status(resp)
    db.update(order_id, yupay_order_id=yid)
    await c.message.edit_text(c.message.html_text + f"\n\n⚙️ Yupay'ga yuborildi (ID: <code>{yid}</code>)")
    if status in yupay.SUCCESS:
        await finish(bot, order_id, ok=True)
    elif status in yupay.FAILED:
        await finish(bot, order_id, ok=False, note=json.dumps(resp)[:500])
    else:
        await bot.send_message(o["user_id"], f"⚙️ Buyurtma #{order_id} bajarilmoqda. Tez orada olmoslar tushadi!")


async def finish(bot: Bot, order_id: int, ok: bool, note: str | None = None):
    o = db.get(order_id)
    if o["status"] in ("completed", "failed"):
        return  # allaqachon yakunlangan (vebhuk qayta kelgan bo'lishi mumkin)
    if ok:
        db.update(order_id, status="completed")
        await bot.send_message(o["user_id"],
                               f"✅ Buyurtma #{order_id} bajarildi!\n📦 {o['product_name']} → ID <code>{o['player_id']}</code>\n"
                               "Xaridingiz uchun rahmat 💎")
        await notify_admins(bot, f"✅ #{order_id} bajarildi")
    else:
        db.update(order_id, status="failed", note=note)
        await bot.send_message(o["user_id"], f"⚠️ Buyurtma #{order_id} bajarilmadi. Admin siz bilan bog'lanadi.")
        await notify_admins(bot, f"❌ #{order_id} Yupay'da bajarilmadi:\n<code>{html.escape(note or '')}</code>")


@router.message(Command("balance"))
async def balance(m: Message):
    if not is_admin(m.from_user.id):
        return
    try:
        data = await client.balance()
        await m.answer(f"💰 Yupay balans:\n<code>{html.escape(json.dumps(data, ensure_ascii=False)[:3500])}</code>")
    except Exception as e:
        await m.answer(f"❌ {html.escape(str(e)[:500])}")


@router.message(Command("yupay_products"))
async def yupay_products(m: Message):
    """products.json dagi yupay_id larni to'ldirish uchun Yupay katalogini ko'rsatadi."""
    if not is_admin(m.from_user.id):
        return
    try:
        data = await client.products()
        text = json.dumps(data, ensure_ascii=False, indent=1)
        for i in range(0, min(len(text), 12000), 3500):
            await m.answer(f"<code>{html.escape(text[i:i + 3500])}</code>")
    except Exception as e:
        await m.answer(f"❌ {html.escape(str(e)[:500])}")


@router.message(Command("check"))
async def check(m: Message, bot: Bot):
    """/check 15 — buyurtma holatini Yupay'dan qo'lda tekshirish (vebhuk kelmasa)."""
    if not is_admin(m.from_user.id):
        return
    parts = (m.text or "").split()
    if len(parts) != 2 or not parts[1].isdigit():
        return await m.answer("Foydalanish: /check <buyurtma raqami>")
    o = db.get(int(parts[1]))
    if not o or not o["yupay_order_id"]:
        return await m.answer("Buyurtma topilmadi yoki Yupay'ga yuborilmagan.")
    try:
        data = await client.get_order(o["yupay_order_id"])
    except Exception as e:
        return await m.answer(f"❌ {html.escape(str(e)[:500])}")
    status = yupay.extract_status(data)
    await m.answer(f"#{o['id']} Yupay holati: <b>{html.escape(status or '?')}</b>")
    if status in yupay.SUCCESS:
        await finish(bot, o["id"], ok=True)
    elif status in yupay.FAILED:
        await finish(bot, o["id"], ok=False, note=json.dumps(data)[:500])


# ---------------- Yupay vebhuk ----------------

def make_webhook_app(bot: Bot) -> web.Application:
    async def handle(request: web.Request):
        raw = await request.read()
        if not yupay.verify_signature(raw, request.headers.get("X-Yupay-Key-Signature")):
            log.warning("Vebhuk imzosi noto'g'ri, rad etildi")
            return web.Response(status=401, text="bad signature")
        try:
            payload = json.loads(raw or b"{}")
        except ValueError:
            return web.Response(status=400, text="bad json")
        log.info("Yupay vebhuk: %s", payload)

        order = None
        yid = yupay.extract_order_id(payload)
        if yid:
            order = db.get_by_yupay(yid)
        ref = yupay.extract_reference(payload)
        if not order and ref and ref.startswith("RA-") and ref[3:].isdigit():
            order = db.get(int(ref[3:]))
        if not order:
            return web.Response(text="ok")  # depozit vebhuki yoki bizga tegishli bo'lmagan buyurtma

        status = yupay.extract_status(payload)
        if status in yupay.SUCCESS:
            await finish(bot, order["id"], ok=True)
        elif status in yupay.FAILED:
            await finish(bot, order["id"], ok=False, note=json.dumps(payload)[:500])
        return web.Response(text="ok")

    app = web.Application()
    app.router.add_post(config.WEBHOOK_PATH, handle)
    return app


async def main():
    db.init()
    bot = Bot(config.BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
    dp = Dispatcher()
    dp.include_router(router)

    runner = web.AppRunner(make_webhook_app(bot))
    await runner.setup()
    await web.TCPSite(runner, config.WEBHOOK_HOST, config.WEBHOOK_PORT).start()
    log.info("Yupay vebhuk: http://%s:%s%s", config.WEBHOOK_HOST, config.WEBHOOK_PORT, config.WEBHOOK_PATH)

    try:
        await dp.start_polling(bot)
    finally:
        await client.close()
        await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
