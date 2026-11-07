# DiniQuiz — Proje Dokümanı

**Sürüm:** 1.0  
**Tarih:** Kasım 2026  
**Durum:** Taslak / Geliştirmeye hazır

---

## 1. Projenin Amacı

DiniQuiz, gençlere yönelik, hızlı ve eğlenceli bir **dini bilgi yarışması** uygulamasıdır. Kullanıcı bir kategori seçer, soruları tek tek ve süre baskısı altında cevaplar, quiz sonunda puanını görür ve adını girerek **Top 10 skor tablosuna** girmeye çalışır.

Temel ilkeler:

- **Kayıt yok, hesap yok.** Kullanıcı uygulamayı açar ve hemen oynar.
- **Hız.** Her soru için **15 saniye** süre vardır.
- **Odak.** Her ekranda yalnızca **bir soru** gösterilir; soru cevaplanmadan (veya süre dolmadan) sonraki soru görülemez.
- **Rekabet.** Quiz sonunda puan hesaplanır, isim sorulur, skor tablosunda ilk 10 gösterilir.

---

## 2. Kapsam

### 2.1 Kapsam dahilinde (v1)

| Özellik | Açıklama |
|---|---|
| 5 kategori | Genel İslami İlimler, Siyer, İslam Tarihi, Sahabe Hayatı, Kur'an |
| Kategori başına 20 soru | Toplam 100 soru, çoktan seçmeli (4 şık) |
| Tek soru / tek ekran | Geri dönme ve ileri atlama yok |
| 15 sn süre | Süre dolarsa soru boş sayılır ve otomatik geçilir |
| Puan hesaplama | Doğru cevap + hız bonusu, sunucu tarafında hesaplanır |
| İsim girişi | Quiz bitince sorulur, hesap oluşturmaz |
| Skor tablosu | Top 10 (genel ve kategori bazlı) |
| Ayrı repolar | `diniquiz-backend` (Django) ve `diniquiz-frontend` (Vue.js) |
| Mobil uyumlu API | Aynı API ileride mobil uygulama tarafından kullanılacak |

### 2.2 Kapsam dışında (v1)

- Kayıt olma, giriş yapma, şifre, profil
- Sosyal medya ile giriş
- Kullanıcının geçmiş oyunlarını görmesi
- Çok oyunculu / canlı yarışma
- Yönetim için ayrı bir panel (soru yönetimi Django Admin ile yapılır)

---

## 3. Kategoriler

| # | Kategori | Slug | Soru sayısı | Kapsam örneği |
|---|---|---|---|---|
| 1 | Genel İslami İlimler | `genel-islami-ilimler` | 20 | İman ve İslam'ın şartları, ibadetler, fıkıh, hadis usulü temelleri |
| 2 | Siyer | `siyer` | 20 | Peygamber Efendimiz'in (s.a.v.) hayatı: doğum, vahiy, hicret, gazveler, veda |
| 3 | İslam Tarihi | `islam-tarihi` | 20 | Dört Halife dönemi, Emeviler, Abbasiler, Endülüs, Selçuklu, Osmanlı |
| 4 | Sahabe Hayatı | `sahabe-hayati` | 20 | Aşere-i Mübeşşere, ensar ve muhacirler, önemli sahabe hanımlar |
| 5 | Kur'an | `kuran` | 20 | Sureler, ayet sayıları, nüzul, Mekki/Medeni sureler, kıssalar |

> **İçerik güvenilirliği:** Dini içerik olduğu için tüm sorular ve cevaplar, yayına alınmadan önce ilahiyat alanında yetkin bir kişi (hoca / ilahiyatçı) tarafından kontrol edilmelidir. Her soru kaydında `kaynak` (source) alanı tutulur ve `onaylandi` (is_approved) işaretlenmeyen sorular oyunda gösterilmez.

---

## 4. Kullanıcı Akışı

```
[Ana Ekran]
   │  "Başla"
   ▼
[Kategori Seçimi] ── 5 kategori kartı
   │  kategori seç
   ▼
[Soru Ekranı 1/20] ── 15 sn sayaç, 4 şık
   │  şık seç  ─veya─  süre dolar
   ▼
[Geri bildirim] ── doğru/yanlış rengi, doğru şık gösterilir (~1,5 sn)
   │  otomatik geçiş
   ▼
[Soru Ekranı 2/20] ... [Soru Ekranı 20/20]
   │
   ▼
[Sonuç Ekranı] ── toplam puan, doğru/yanlış/boş sayısı
   │
   ▼
[İsim Girişi] ── "Adın ne?" (2–20 karakter)
   │  kaydet
   ▼
[Skor Tablosu] ── Top 10, kullanıcının sırası vurgulanır
   │
   └── "Tekrar Oyna" / "Başka Kategori"
```

### 4.1 Kurallar

1. Quiz başladığında 20 soru **rastgele sırayla** gelir; şıkların sırası da karıştırılır.
2. Kullanıcı bir şıkkı seçtiği anda cevap kilitlenir; değiştirilemez.
3. Süre dolarsa cevap **boş** sayılır (0 puan) ve doğru şık gösterilir.
4. Önceki soruya geri dönülemez; tarayıcıda "geri" yapılsa da sunucu sadece sıradaki soruyu verir.
5. Sayfa yenilenirse quiz kaldığı yerden devam eder, **süre sıfırlanmaz** (süre sunucuda tutulur).
6. Quiz yarıda bırakılırsa skor tablosuna girmez. Yarım kalan oturumlar 1 saat sonra geçersiz sayılır.
7. İsim girmek isteğe bağlıdır; "Geç" diyen kullanıcının puanı tabloya yazılmaz.

---

## 5. Puanlama

Puan **tamamen sunucuda** hesaplanır; frontend puan göndermez, sadece seçilen şıkkı gönderir.

| Durum | Puan |
|---|---|
| Doğru cevap | **100 taban puan + hız bonusu (0–50)** |
| Yanlış cevap | 0 |
| Süre doldu / boş | 0 |

**Hız bonusu:**

```
geçen_süre   = cevap_zamanı − sorunun_sunulduğu_zaman   (saniye)
kalan_süre   = max(0, 15 − geçen_süre)
hız_bonusu   = round(kalan_süre / 15 × 50)
soru_puanı   = 100 + hız_bonusu       (sadece doğruysa)
```

- Bir quizde en yüksek puan: 20 × 150 = **3000**.
- Ağ gecikmesi için **1 saniye tolerans** vardır: 16 saniyeden sonra gelen cevap "süre doldu" sayılır.
- **Eşitlik durumunda** skor tablosunda quizi daha önce bitiren üstte yer alır.

---

## 6. Sistem Mimarisi

```
┌────────────────────┐        ┌────────────────────┐
│  Vue.js Web (SPA)  │        │ Mobil Uygulama (v2) │
│ diniquiz-frontend  │        │  (aynı API'yi kullanır)
└─────────┬──────────┘        └─────────┬──────────┘
          │   HTTPS / JSON  (REST, /api/v1)
          ▼                             ▼
┌───────────────────────────────────────────────┐
│     Django + Django REST Framework (API)      │
│              diniquiz-backend                 │
│  quiz uygulaması · skor tablosu · Django Admin│
└───────────────────────┬───────────────────────┘
                        ▼
              ┌──────────────────┐
              │    PostgreSQL    │
              └──────────────────┘
```

### 6.1 Teknoloji Seçimleri

| Katman | Teknoloji |
|---|---|
| Backend | Python 3.12, Django 5.x, Django REST Framework |
| Veritabanı | PostgreSQL 16 |
| API dokümantasyonu | drf-spectacular (OpenAPI 3 / Swagger) |
| Diğer backend | django-cors-headers, django-environ, gunicorn |
| Frontend | Vue 3 (Composition API), Vite, TypeScript |
| Frontend yardımcıları | Vue Router, Pinia, Axios |
| Stil | Tailwind CSS (özel renk paleti ile) |
| Yerel geliştirme | Docker Compose (PostgreSQL) |
| Test | pytest + pytest-django (backend), Vitest (frontend) |

### 6.2 Repolar

| Repo | İçerik |
|---|---|
| `diniquiz-backend` | Django projesi, API, veri modeli, admin, soru yükleme komutu |
| `diniquiz-frontend` | Vue.js SPA, ekranlar, tema, API istemcisi |

İki repo birbirinden bağımsız sürümlenir ve dağıtılır. Aralarındaki tek sözleşme, **Bölüm 8'deki API**'dir.

---

## 7. Veri Modeli

```
Category 1 ── * Question 1 ── * Choice
                   │
QuizSession 1 ── * SessionAnswer * ── 1 Question
```

### 7.1 Category (Kategori)

| Alan | Tip | Not |
|---|---|---|
| id | int (PK) | |
| name | varchar(100) | "Siyer" |
| slug | varchar(100), unique | "siyer" |
| description | text | Kart üzerindeki kısa açıklama |
| color | varchar(7) | Kategori rengi, ör. `#FF8A3D` |
| icon | varchar(50) | İkon adı |
| order | int | Sıralama |
| is_active | bool | |

### 7.2 Question (Soru)

| Alan | Tip | Not |
|---|---|---|
| id | int (PK) | |
| category | FK → Category | |
| text | text | Soru metni |
| arabic_text | text, boş olabilir | Ayet/hadis metni gerekiyorsa |
| explanation | text, boş olabilir | Cevaptan sonra gösterilebilecek kısa açıklama |
| source | varchar(255) | Kaynak (kitap, ayet no, hadis kaynağı) |
| difficulty | smallint | 1 kolay, 2 orta, 3 zor |
| is_approved | bool | Onaylanmamış soru oyunda çıkmaz |
| created_at / updated_at | timestamp | |

### 7.3 Choice (Şık)

| Alan | Tip | Not |
|---|---|---|
| id | int (PK) | |
| question | FK → Question | |
| text | varchar(255) | |
| is_correct | bool | Her soruda **tam olarak 1** doğru şık (model doğrulaması ile) |

### 7.4 QuizSession (Quiz Oturumu)

| Alan | Tip | Not |
|---|---|---|
| id | UUID (PK) | |
| token | varchar(64) | Oturumu başlatan istemciye verilen gizli anahtar |
| category | FK → Category | |
| question_order | JSON (int listesi) | Bu oturuma çekilen 20 sorunun sırası |
| current_index | smallint | Sıradaki soru (0–19) |
| current_served_at | timestamp, boş olabilir | Mevcut sorunun gösterildiği an |
| score | int | Toplam puan |
| correct_count / wrong_count / empty_count | smallint | |
| status | enum | `active`, `finished`, `expired` |
| player_name | varchar(20), boş olabilir | Quiz sonunda girilen isim |
| started_at / finished_at | timestamp | |
| client_platform | varchar(20) | `web`, `android`, `ios` |

### 7.5 SessionAnswer (Verilen Cevap)

| Alan | Tip | Not |
|---|---|---|
| id | int (PK) | |
| session | FK → QuizSession | |
| question | FK → Question | |
| choice | FK → Choice, boş olabilir | Boş = süre doldu |
| is_correct | bool | |
| elapsed_ms | int | Cevap süresi |
| points | smallint | |
| answered_at | timestamp | |

Kısıt: `(session, question)` benzersizdir; aynı soruya iki kez cevap verilemez.

### 7.6 Skor tablosu

Ayrı tablo yoktur. Skor tablosu, `status = finished` ve `player_name` dolu olan oturumlardan sorgulanır:

```sql
SELECT player_name, score, category_id, finished_at
FROM quiz_quizsession
WHERE status = 'finished' AND player_name IS NOT NULL
  [AND category_id = :kategori]
ORDER BY score DESC, finished_at ASC
LIMIT 10;
```

Performans için `(status, score DESC, finished_at)` ve `(category_id, status, score DESC)` üzerinde indeks oluşturulur.

---

## 8. API Sözleşmesi (v1)

**Temel adres:** `/api/v1/`  
**Format:** JSON, UTF-8  
**Kimlik doğrulama:** Yok. Quiz işlemleri, oturum açılırken verilen `token` ile korunur ve `X-Session-Token` başlığında gönderilir.

### 8.1 Kategorileri listele

`GET /api/v1/categories/`

```json
[
  {
    "id": 1,
    "name": "Siyer",
    "slug": "siyer",
    "description": "Peygamber Efendimiz'in hayatı",
    "color": "#FF8A3D",
    "icon": "moon-star",
    "question_count": 20
  }
]
```

### 8.2 Quiz başlat

`POST /api/v1/sessions/`

```json
// istek
{ "category": "siyer", "platform": "web" }

// yanıt 201
{
  "session_id": "6f1c...-uuid",
  "token": "b2f9e1...",
  "category": "siyer",
  "total_questions": 20,
  "time_limit_seconds": 15
}
```

### 8.3 Sıradaki soruyu al

`GET /api/v1/sessions/{session_id}/current/`  
Başlık: `X-Session-Token: <token>`

```json
{
  "index": 3,
  "total": 20,
  "question": {
    "id": 57,
    "text": "Hicret hangi yılda gerçekleşmiştir?",
    "arabic_text": null,
    "choices": [
      { "id": 221, "text": "610" },
      { "id": 222, "text": "622" },
      { "id": 223, "text": "630" },
      { "id": 224, "text": "632" }
    ]
  },
  "remaining_ms": 15000,
  "score": 420
}
```

- **Doğru şık bilgisi asla bu yanıtta yer almaz.**
- Soru ilk kez istendiğinde `current_served_at` kaydedilir. Aynı soru tekrar istenirse (sayfa yenileme) süre sıfırlanmaz, `remaining_ms` kalan süreyi döner.
- Quiz bittiyse `409` ve `{"status": "finished"}` döner.

### 8.4 Cevap gönder

`POST /api/v1/sessions/{session_id}/answer/`  
Başlık: `X-Session-Token: <token>`

```json
// istek (süre dolduysa choice_id: null)
{ "question_id": 57, "choice_id": 222 }

// yanıt 200
{
  "is_correct": true,
  "correct_choice_id": 222,
  "points": 138,
  "total_score": 558,
  "explanation": "Hicret, miladi 622 yılında gerçekleşmiştir.",
  "is_last": false
}
```

Hatalar:
- `400` — `question_id` mevcut soruyla eşleşmiyor (atlama/geri dönme girişimi)
- `409` — bu soru zaten cevaplandı
- `403` — token geçersiz
- `410` — oturum süresi doldu

### 8.5 Sonucu al

`GET /api/v1/sessions/{session_id}/result/`

```json
{
  "score": 2340,
  "correct_count": 16,
  "wrong_count": 3,
  "empty_count": 1,
  "max_score": 3000,
  "rank_preview": 4
}
```

`rank_preview`: Bu puanla skor tablosunda kaçıncı sırada olunacağı (isim girmeye teşvik için).

### 8.6 İsim kaydet

`POST /api/v1/sessions/{session_id}/name/`

```json
// istek
{ "player_name": "Ahmet" }

// yanıt 200
{ "rank": 4, "in_top_10": true }
```

- Sadece `finished` durumdaki oturuma, **bir kez** isim yazılabilir.
- İsim: 2–20 karakter, baştaki/sondaki boşluklar silinir, Türkçe karakterlere izin verilir, uygunsuz kelime filtresi uygulanır.

### 8.7 Skor tablosu

`GET /api/v1/leaderboard/?category=siyer&limit=10`

```json
{
  "category": "siyer",
  "entries": [
    { "rank": 1, "player_name": "Zeynep", "score": 2890, "finished_at": "2026-11-08T10:12:00Z" },
    { "rank": 2, "player_name": "Yusuf",  "score": 2755, "finished_at": "2026-11-08T09:40:00Z" }
  ]
}
```

- `category` verilmezse tüm kategorilerin genel Top 10'u döner.
- `limit` en fazla 10'dur.

---

## 9. Güvenlik ve Hile Önleme

| Risk | Önlem |
|---|---|
| Doğru cevabı API'den okumak | Doğru şık, cevap gönderilene kadar istemciye hiç gönderilmez |
| Süreyi uzatmak | Süre sunucuda (`current_served_at`) tutulur; frontend sayacı sadece görseldir |
| Soru atlamak / geri dönmek | Sunucu sadece `current_index`'teki soruya cevap kabul eder |
| Sahte puan göndermek | Puan sadece sunucuda hesaplanır |
| Başkasının oturumuna müdahale | Her oturum için rastgele `token`, `X-Session-Token` başlığı ile doğrulanır |
| Spam / bot | DRF throttling: IP başına oturum açma (ör. 30/saat), cevap (ör. 120/dk) |
| Uygunsuz isimler | Uzunluk sınırı + kelime filtresi + admin panelinden isim silme |
| XSS | İsimler frontend'de metin olarak basılır (`v-html` kullanılmaz) |
| Yetkisiz admin erişimi | Admin yolu varsayılandan farklı (`/yonetim/`), güçlü şifre, üretimde `DEBUG=False` |

---

## 10. Arayüz Tasarım Rehberi

**Hedef kitle:** Gençler. **Ton:** Canlı, enerjik, modern, samimi. **Çok koyu tema kullanılmaz;** açık zemin üzerinde canlı renkler tercih edilir.

### 10.1 Renk Paleti

| Rol | Renk | Kullanım |
|---|---|---|
| Ana renk (Primary) | `#6C5CE7` — canlı mor | Butonlar, başlıklar, ilerleme çubuğu |
| İkincil (Secondary) | `#00C2A8` — turkuaz | Vurgular, ikincil butonlar |
| Vurgu (Accent) | `#FFB020` — ayçiçeği sarısı | Puan, yıldızlar, rozetler |
| Doğru | `#22C55E` — yeşil | Doğru şık geri bildirimi |
| Yanlış | `#FF5A6E` — mercan | Yanlış şık geri bildirimi |
| Arka plan | `#F7F5FF` — çok açık lavanta | Sayfa zemini |
| Yüzey | `#FFFFFF` | Kartlar |
| Metin | `#1E1B4B` — koyu lacivert | Ana metin (tam siyah değil) |
| İkincil metin | `#6B6B8D` | Açıklamalar |

**Kategori renkleri:**

| Kategori | Renk |
|---|---|
| Genel İslami İlimler | `#6C5CE7` mor |
| Siyer | `#FF8A3D` turuncu |
| İslam Tarihi | `#3D8BFF` mavi |
| Sahabe Hayatı | `#00C2A8` turkuaz |
| Kur'an | `#22B573` yeşil |

Arka planlarda hafif degrade kullanılabilir (ör. `#F7F5FF → #EAF9F6`). Metin/zemin kontrastı WCAG AA (en az 4.5:1) olmalıdır.

### 10.2 Tipografi

- **Başlık ve gövde:** *Nunito* veya *Poppins* (Türkçe karakter desteği tam, yuvarlak ve samimi).
- **Arapça metin (ayet/hadis):** *Amiri* veya *Scheherazade New*, sağdan sola (`dir="rtl"`).
- Soru metni mobilde en az 20px, şıklar en az 17px.

### 10.3 Bileşen Kuralları

- **Köşeler:** Kartlarda 20px, butonlarda 14px yuvarlama.
- **Şık butonları:** Tam genişlik, en az 56px yükseklik (parmakla kolay basılsın), A/B/C/D etiketli.
- **Sayaç:** Soru üstünde dairesel halka; 15→6 sn yeşil/mor, 5→0 sn mercan rengine döner ve hafifçe titrer.
- **İlerleme:** "Soru 4 / 20" yazısı + ince ilerleme çubuğu.
- **Geri bildirim:** Doğru şık yeşil + ✓, seçilen yanlış şık mercan + ✕, kısa bir "+138" puan animasyonu.
- **Sonuç ekranı:** Büyük puan, konfeti (Top 10'a girdiyse), doğru/yanlış/boş sayıları.
- **Skor tablosu:** İlk 3'e altın/gümüş/bronz rozet; kullanıcının satırı vurgulu.
- **Animasyonlar:** Kısa ve hafif (150–300 ms). `prefers-reduced-motion` açıksa animasyonlar kapatılır.

### 10.4 Ekranlar

1. **Ana ekran** — Logo, "DiniQuiz" yazısı, kısa slogan, büyük "Başla" butonu, "Skor Tablosu" bağlantısı
2. **Kategori seçimi** — 5 renkli kart (ikon + ad + "20 soru")
3. **Soru ekranı** — Sayaç, ilerleme, soru, 4 şık
4. **Sonuç ekranı** — Puan, istatistikler, tahmini sıra
5. **İsim girişi** — Tek alan, "Kaydet" ve "Geç"
6. **Skor tablosu** — Kategori sekmeleri (Genel + 5 kategori), Top 10 listesi

Tasarım **mobil öncelikli** (mobile-first) yapılır; web sürümü telefonda da uygulama gibi hissettirmelidir.

---

## 11. Mobil Uygulama Hazırlığı

Backend, ileride yapılacak mobil uygulamayı düşünerek tasarlanmıştır:

- API **durumsuz** (stateless) ve JSON tabanlıdır; cookie veya oturum çerezi kullanılmaz.
- Sürümleme `/api/v1/` ile yapılır; kırıcı değişiklikler `/api/v2/` ile gelir.
- Tüm metinler (soru, açıklama, kategori) API'den gelir; mobilde tekrar yazılmaz.
- Süre ve puan sunucuda hesaplandığı için web ve mobil aynı kurallarla yarışır.
- `platform` alanı ile hangi platformdan oynandığı izlenebilir.
- OpenAPI şeması (`/api/schema/`) mobil istemci üretiminde kullanılabilir.
- Mobil teknoloji seçimi (Flutter, React Native veya Vue koduyla Capacitor) v2 aşamasında yapılacaktır. Mevcut Vue kodunu yeniden kullanmak isteniyorsa **Capacitor** en hızlı yoldur.

---

## 12. Soru Veri Formatı

Sorular, backend reposundaki `fixtures/questions/` klasöründe her kategori için bir JSON dosyası olarak tutulur ve `python manage.py load_questions` komutuyla yüklenir.

```json
{
  "category": "siyer",
  "questions": [
    {
      "text": "Peygamber Efendimiz'e (s.a.v.) ilk vahiy hangi mağarada gelmiştir?",
      "choices": ["Sevr", "Hira", "Uhud", "Kuba"],
      "correct": 1,
      "explanation": "İlk vahiy Nur Dağı'ndaki Hira Mağarası'nda gelmiştir.",
      "source": "Alak Suresi 1-5; Buhârî, Bed'ü'l-vahy 3",
      "difficulty": 1
    }
  ]
}
```

- `correct`: `choices` listesindeki doğru şıkkın sırası (0'dan başlar).
- Komut, aynı metne sahip soruyu tekrar eklemez (güncelleme yapar).
- Yüklenen sorular varsayılan olarak `is_approved = false` gelir; onay admin panelinden verilir. (`--approve` parametresi ile toplu onay verilebilir.)

---

## 13. Yol Haritası

| Aşama | İçerik | Tahmini süre |
|---|---|---|
| **1. Hazırlık** | Repolar, Docker Compose, CI, renk paleti ve ekran tasarımları | 1 hafta |
| **2. Backend çekirdek** | Modeller, admin, soru yükleme komutu, kategori ve oturum API'leri | 1–2 hafta |
| **3. Frontend çekirdek** | Ekranlar, sayaç, quiz akışı, API bağlantısı | 1–2 hafta |
| **4. Skor tablosu** | İsim kaydı, Top 10, kategori sekmeleri | 3–4 gün |
| **5. İçerik** | 100 sorunun yazılması ve uzman onayı | Paralel yürür |
| **6. Test & cilalama** | Birim/entegrasyon testleri, animasyonlar, erişilebilirlik | 1 hafta |
| **7. Yayın (v1)** | Backend + PostgreSQL ve frontend dağıtımı | 2–3 gün |
| **8. Mobil (v2)** | Mobil uygulama, mağaza yayını | Ayrıca planlanacak |

---

## 14. Kabul Kriterleri (v1)

- [ ] 5 kategori ve her birinde en az 20 onaylı soru var.
- [ ] Kullanıcı kayıt olmadan quiz başlatabiliyor.
- [ ] Her ekranda yalnızca bir soru görünüyor; cevap vermeden sonraki soruya geçilemiyor.
- [ ] Her soru için 15 sn sayaç çalışıyor; süre dolunca soru boş sayılıp otomatik geçiliyor.
- [ ] Sayfa yenilendiğinde süre sıfırlanmıyor, quiz kaldığı yerden devam ediyor.
- [ ] Doğru şık, cevap gönderilmeden önce hiçbir API yanıtında bulunmuyor.
- [ ] Puan sunucuda Bölüm 5'teki formüle göre hesaplanıyor.
- [ ] Quiz sonunda isim soruluyor; girilen isim Top 10'da doğru sırada görünüyor.
- [ ] Skor tablosu genel ve kategori bazında Top 10 gösteriyor.
- [ ] Arayüz mobilde (360px genişlik) ve masaüstünde düzgün görünüyor.
- [ ] Renkler Bölüm 10'daki palete uygun, koyu tema kullanılmamış.
- [ ] Backend ve frontend ayrı repolarda, her birinin README dosyası var.
- [ ] Backend testleri geçiyor (quiz akışı, puanlama, süre, hile önleme).

---

## 15. Sözlük

| Terim | Anlamı |
|---|---|
| Oturum (Session) | Bir kullanıcının başlattığı tek bir quiz oyunu |
| Token | Oturumu sadece başlatan istemcinin yönetebilmesi için verilen gizli anahtar |
| Top 10 | Skor tablosunda en yüksek puanlı ilk 10 kayıt |
| Hız bonusu | Doğru cevap ne kadar hızlı verilirse o kadar fazla olan ek puan |
| SPA | Single Page Application — tek sayfa web uygulaması |
