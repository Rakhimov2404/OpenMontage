# Rakhimov ALMAZ bot — Yupay bilan ulash

Bot Free Fire olmoslarini sotadi va buyurtmani **reseller.yupay.uz** orqali avtomatik bajaradi.

## Qanday ishlaydi

1. Mijoz botda **💎 Almaz sotib olish** tugmasini bosadi, paketni tanlaydi va Free Fire ID'sini yozadi.
2. Bot karta raqamini ko'rsatadi. Mijoz pul o'tkazib, chek rasmini yuboradi.
3. Adminga chek va **✅ Tasdiqlash / 🚫 Rad etish** tugmalari keladi.
4. Admin tasdiqlasa, bot Yupay'ga buyurtma yuboradi. Pul Yupay balansingizdan yechiladi.
5. Yupay natijani vebhuk orqali yuboradi va bot mijozga "✅ Bajarildi" deb yozadi.

## O'rnatish (VPS server, Ubuntu)

```bash
sudo apt install -y python3 python3-venv
cd rakhimov_almaz_bot/bot
python3 -m venv venv && . venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
nano .env        # qiymatlarni to'ldiring
python bot.py
```

Doimiy ishlashi uchun `systemd` yoki `screen` orqali ishga tushiring.

## Yupay sozlamalari

1. **Yangi API kalit** yarating, eskisini (chatda ko'rinib qolganini) **Bekor qilish** tugmasi bilan o'chiring. Yangi kalitni faqat `.env` dagi `YUPAY_API_KEY` ga yozing.
2. **Ruxsat berilgan IP** ro'yxatiga serveringizning IP manzilini yozing (`curl ifconfig.me` buyrug'i ko'rsatadi).
3. **Vebhuklar** bo'limiga quyidagi manzilni yozing: `https://SIZNING-DOMEN/yupay/webhook`.
   Bot 8080-portda tinglaydi. Domen va HTTPS uchun nginx yoki Caddy orqali 8080-portga yo'naltiring.
4. Yupay **API hujjatini** oching va `.env` dagi `YUPAY_BASE_URL` va `YUPAY_PATH_*` qiymatlarini, shuningdek `YUPAY_PLAYER_FIELD` ni hujjatga moslang.
   ⚠️ Hozirgi qiymatlar taxminiy, chunki hujjat ko'rilmagan.

## Mahsulotlarni sozlash — `products.json`

- `price` — mijoz to'laydigan narx (so'm).
- `yupay_id` — Yupay'dagi mahsulot ID'si. Uni bilish uchun botga admin sifatida `/yupay_products` deb yozing.

Narxlarni Yupay narxi va dollar kursidan yuqori qilib qo'ying, aks holda zarar qilasiz.

## Admin buyruqlari

| Buyruq | Nima qiladi |
|---|---|
| `/balance` | Yupay balansini ko'rsatadi |
| `/yupay_products` | Yupay katalogi (ID'lar bilan) |
| `/check 15` | 15-buyurtma holatini Yupay'dan tekshiradi (vebhuk kelmasa) |

## Birinchi sinov

1. Yupay balansini kichik summaga to'ldiring.
2. `/balance` — kalit va IP to'g'ri ekanini tekshiradi.
3. `/yupay_products` — `products.json` ga ID'larni yozing va botni qayta ishga tushiring.
4. Eng arzon paketni (110 💎) o'zingizning Free Fire ID'ingizga sotib olib ko'ring.
