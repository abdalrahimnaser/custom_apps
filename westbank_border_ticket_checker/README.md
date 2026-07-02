# مراقب تذاكر JETT VIP

يفحص موقع JETT VIP بشكل مستمر بحثاً عن تذاكر متاحة لجسر الملك حسين (الخدمة B).

## التثبيت

```bash
cd westbank_border_ticket_checker
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## تشغيل الواجهة

```bash
python app.py
```

افتح **http://127.0.0.1:5050** — واجهة عربية لاختيار التواريخ، بدء المراقبة، واستقبال التنبيهات.

## النشر على Render

1. ارفع المشروع إلى GitHub
2. أنشئ **Web Service** على [Render](https://render.com) واربط المستودع
3. يقرأ `render.yaml` تلقائياً، أو عيّن:
   - **Build:** `./build.sh`
   - **Start:** `gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 120`
4. فعّل تيليغرام من الواجهة أو عبر `TELEGRAM_BOT_TOKEN` و `TELEGRAM_CHAT_ID`

**ملاحظة:** الخطة المجانية تتوقف عند الخمول — للمراقبة المستمرة استخدم خطة مدفوعة.

## سطر الأوامر

```bash
python checker.py
python checker.py --once
python checker.py --start 2026-07-11 --end 2026-07-18 --interval 300
```

## الإشعارات

- تيليغرام (من الواجهة أو متغيرات البيئة)
- صوت في المتصفح عند ظهور تذاكر

## الموقع المُراقَب

| الموقع | الرابط | الخدمة |
|--------|--------|--------|
| JETT VIP | https://www.jett.com.jo/ar/book?from=16&to=41 | VIP / الخدمة B |

يُرسل تنبيه في كل فحص يجد فيه تذاكر (بدون إزالة التكرار).
