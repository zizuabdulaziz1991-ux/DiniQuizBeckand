# DiniQuiz — Backend

DiniQuiz dini bilgi yarışmasının REST API'si. **Python / Django / Django REST Framework / PostgreSQL** ile geliştirilmiştir. Hem web (Vue.js) hem de ileride yapılacak mobil uygulama bu API'yi kullanır.

> Ürün kuralları, puanlama ve tasarım detayları için: **DiniQuiz Proje Dokümanı**

---

## Özellikler

- 5 kategori × 20 soru (çoktan seçmeli, 4 şık)
- Kayıt/giriş yok; quiz oturumu `token` ile korunur
- Soru başına 15 sn süre, **sunucu tarafında** takip edilir
- Puan **sunucuda** hesaplanır (doğru: 100 + 0–50 hız bonusu)
- Doğru şık, cevap verilene kadar istemciye gönderilmez
- Genel ve kategori bazlı Top 10 skor tablosu
- Soru yönetimi için Django Admin
- JSON dosyalarından soru yükleme komutu
- OpenAPI / Swagger dokümantasyonu

---

## Teknolojiler

| | |
|---|---|
| Dil | Python 3.12 |
| Framework | Django 5.x, Django REST Framework |
| Veritabanı | PostgreSQL 16 |
| API dokümanı | drf-spectacular |
| Diğer | django-cors-headers, django-environ, gunicorn |
| Test | pytest, pytest-django, factory-boy |
| Kod kalitesi | ruff, black |

---

## Klasör Yapısı

```
diniquiz-backend/
├── config/                 # Django proje ayarları
│   ├── settings/
│   │   ├── base.py
│   │   ├── dev.py
│   │   └── prod.py
│   ├── urls.py
│   └── wsgi.py
├── quiz/                   # Ana uygulama
│   ├── models.py           # Category, Question, Choice, QuizSession, SessionAnswer
│   ├── serializers.py
│   ├── views.py
│   ├── urls.py
│   ├── services/
│   │   ├── scoring.py      # Puan hesaplama
│   │   └── session.py      # Oturum akışı (soru verme, cevap alma, bitirme)
│   ├── permissions.py      # X-Session-Token doğrulaması
│   ├── throttles.py
│   ├── validators.py       # İsim doğrulama, kelime filtresi
│   ├── admin.py
│   ├── management/commands/
│   │   ├── load_questions.py
│   │   └── expire_sessions.py
│   └── tests/
├── fixtures/questions/     # Kategori başına soru JSON dosyaları
│   ├── genel-islami-ilimler.json
│   ├── siyer.json
│   ├── islam-tarihi.json
│   ├── sahabe-hayati.json
│   └── kuran.json
├── docker-compose.yml      # Yerel PostgreSQL
├── requirements/
│   ├── base.txt
│   └── dev.txt
├── .env.example
├── manage.py
└── README.md
```

---

## Kurulum

### 1. Gereksinimler

- Python 3.12+
- Docker ve Docker Compose (yerel PostgreSQL için) **veya** kurulu bir PostgreSQL 16

### 2. Repoyu klonla

```bash
git clone <repo-url> diniquiz-backend
cd diniquiz-backend
```

### 3. Sanal ortam ve bağımlılıklar

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements/dev.txt
```

### 4. Ortam değişkenleri

```bash
cp .env.example .env
```

`.env` örneği:

```env
DJANGO_SETTINGS_MODULE=config.settings.dev
SECRET_KEY=degistir-bunu-uzun-rastgele-bir-anahtar
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

DATABASE_URL=postgres://diniquiz:diniquiz@localhost:5432/diniquiz

CORS_ALLOWED_ORIGINS=http://localhost:5173

QUIZ_QUESTION_COUNT=20
QUIZ_TIME_LIMIT_SECONDS=15
QUIZ_GRACE_MS=1000
QUIZ_SESSION_TTL_MINUTES=60
```

### 5. PostgreSQL'i başlat

```bash
docker compose up -d db
```

`docker-compose.yml`:

```yaml
services:
  db:
    image: postgres:16
    environment:
      POSTGRES_DB: diniquiz
      POSTGRES_USER: diniquiz
      POSTGRES_PASSWORD: diniquiz
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
volumes:
  pgdata:
```

### 6. Veritabanı, admin kullanıcısı ve sorular

```bash
python manage.py migrate
python manage.py createsuperuser
python manage.py load_questions fixtures/questions/ --approve
```

### 7. Sunucuyu çalıştır

```bash
python manage.py runserver
```

| Adres | İçerik |
|---|---|
| http://localhost:8000/api/v1/ | API |
| http://localhost:8000/api/docs/ | Swagger arayüzü |
| http://localhost:8000/api/schema/ | OpenAPI şeması |
| http://localhost:8000/yonetim/ | Django Admin |

---

## API Özeti

Tüm uç noktalar `/api/v1/` altındadır. Oturuma ait isteklerde `X-Session-Token` başlığı zorunludur.

| Metot | Uç nokta | Açıklama |
|---|---|---|
| GET | `/categories/` | Kategorileri listeler |
| POST | `/sessions/` | Yeni quiz başlatır → `session_id`, `token` |
| GET | `/sessions/{id}/current/` | Sıradaki soruyu ve kalan süreyi verir (doğru şık yok) |
| POST | `/sessions/{id}/answer/` | Cevabı gönderir → doğru mu, puan, doğru şık |
| GET | `/sessions/{id}/result/` | Toplam puan ve istatistikler |
| POST | `/sessions/{id}/name/` | Quiz sonunda oyuncu adını kaydeder |
| GET | `/leaderboard/?category=<slug>` | Top 10 (kategori verilmezse genel) |

### Örnek akış

```bash
# 1) Quiz başlat
curl -X POST http://localhost:8000/api/v1/sessions/ \
  -H "Content-Type: application/json" \
  -d '{"category": "siyer", "platform": "web"}'

# 2) Soruyu al
curl http://localhost:8000/api/v1/sessions/<SESSION_ID>/current/ \
  -H "X-Session-Token: <TOKEN>"

# 3) Cevapla (süre dolduysa "choice_id": null)
curl -X POST http://localhost:8000/api/v1/sessions/<SESSION_ID>/answer/ \
  -H "Content-Type: application/json" \
  -H "X-Session-Token: <TOKEN>" \
  -d '{"question_id": 57, "choice_id": 222}'

# 4) 20 soru bitince isim kaydet
curl -X POST http://localhost:8000/api/v1/sessions/<SESSION_ID>/name/ \
  -H "Content-Type: application/json" \
  -H "X-Session-Token: <TOKEN>" \
  -d '{"player_name": "Ahmet"}'

# 5) Skor tablosu
curl "http://localhost:8000/api/v1/leaderboard/?category=siyer"
```

Tam istek/yanıt örnekleri proje dokümanının **8. bölümünde** ve Swagger arayüzündedir.

---

## İş Kuralları (Backend'in Garanti Ettikleri)

1. **Süre:** Soru ilk kez `current/` ile istendiğinde `current_served_at` kaydedilir. Cevap, `15 sn + 1 sn tolerans` içinde gelmezse "boş" sayılır. Aynı soru tekrar istenirse süre sıfırlanmaz.
2. **Sıra:** Sadece `current_index`'teki soruya cevap kabul edilir. Farklı `question_id` → `400`.
3. **Tek cevap:** Bir soruya ikinci cevap → `409`.
4. **Gizlilik:** `Choice.is_correct` sadece `answer/` yanıtında, cevap kaydedildikten sonra döner.
5. **Puan:** `100 + round(kalan_sn / 15 × 50)` (sadece doğru cevapta). Hesaplama `quiz/services/scoring.py` içindedir.
6. **Bitiş:** 20. cevaptan sonra oturum `finished` olur. İsim sadece bir kez yazılabilir.
7. **Süresi dolan oturumlar:** 60 dakika boyunca tamamlanmayan oturumlar `expire_sessions` komutuyla `expired` yapılır (cron ile çalıştırılmalı).
8. **Onay:** `is_approved = False` olan sorular oturumlara dahil edilmez.

---

## Soru Yükleme

```bash
# Klasördeki tüm JSON dosyalarını yükle
python manage.py load_questions fixtures/questions/

# Tek dosya, toplu onay ile
python manage.py load_questions fixtures/questions/siyer.json --approve

# Yüklemeden sadece doğrula
python manage.py load_questions fixtures/questions/ --dry-run
```

JSON formatı:

```json
{
  "category": "siyer",
  "questions": [
    {
      "text": "Peygamber Efendimiz'e (s.a.v.) ilk vahiy hangi mağarada gelmiştir?",
      "choices": ["Sevr", "Hira", "Uhud", "Kuba"],
      "correct": 1,
      "explanation": "İlk vahiy Nur Dağı'ndaki Hira Mağarası'nda gelmiştir.",
      "source": "Alak Suresi 1-5",
      "difficulty": 1
    }
  ]
}
```

Komut şunları kontrol eder: 4 şık olması, `correct` değerinin geçerli olması, kategorinin var olması, aynı soru metninin tekrar eklenmemesi.

> Dini içerik olduğu için sorular yayına alınmadan önce yetkin bir kişi tarafından kontrol edilmeli ve `source` alanı doldurulmalıdır.

---

## Testler

```bash
pytest
pytest --cov=quiz --cov-report=term-missing
```

Mutlaka test edilmesi gerekenler:

- Oturum açma ve 20 sorunun rastgele seçilmesi
- `current/` yanıtında doğru şık bilgisinin **olmaması**
- Süre aşımında cevabın boş sayılması (zaman `freezegun` ile dondurularak)
- Sayfa yenilemede sürenin sıfırlanmaması
- Soru atlama / aynı soruya iki cevap girişimleri
- Puan formülü (0 sn, 7,5 sn, 15 sn, 16+ sn)
- İsim doğrulama ve tek seferlik kayıt
- Skor tablosu sıralaması ve eşitlik durumu

---

## Kod Kalitesi

```bash
ruff check .
black .
```

---

## Üretim (Production) Notları

- `DJANGO_SETTINGS_MODULE=config.settings.prod`, `DEBUG=False`
- `SECRET_KEY` ve `DATABASE_URL` ortam değişkeninden gelir, repoya yazılmaz
- `ALLOWED_HOSTS` ve `CORS_ALLOWED_ORIGINS` sadece gerçek alan adlarını içerir
- `python manage.py collectstatic` (admin için statik dosyalar, WhiteNoise önerilir)
- Uygulama sunucusu: `gunicorn config.wsgi:application --workers 3`
- HTTPS zorunlu (`SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`)
- `expire_sessions` komutu için zamanlanmış görev (ör. 15 dakikada bir)
- PostgreSQL için düzenli yedekleme

---

## Mobil Uyumluluk

- API durumsuzdur (stateless); çerez kullanılmaz, sadece `X-Session-Token` başlığı.
- Kırıcı değişiklikler `/api/v2/` altında yapılır; `/api/v1/` geriye dönük uyumlu kalır.
- `POST /sessions/` isteğindeki `platform` alanı `web`, `android` veya `ios` olabilir.

---

## İlgili Repo

- **diniquiz-frontend** — Vue.js web arayüzü
