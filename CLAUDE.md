# CLAUDE.md — Maestro Platform

> Bu dosya, Maestro projesinde çalışan AI asistanları (Claude, vb.) için projenin mimarisini, kurallarını ve standartlarını tanımlayan tek kaynak belgedir.

---
# NOT: Koddaki her şeyi ingilizce yaz. Sadece benle iletişime geçerken Türkçe kullan 

## 1. Proje Tanımı

**Maestro**, herkese açık, genel amaçlı bir AI agent orkestrasyon platformudur. Kullanıcılar kendi yapay zeka API anahtarlarını (BYOK — Bring Your Own Key) bağlayarak çok katmanlı agent hiyerarşisi ile karmaşık görevleri otomatikleştirir.

### Temel Değer Önerisi

- Kullanıcı tek bir prompt girer → Orchestrator görevi analiz eder → uygun Main Agent'a yönlendirir → Main Agent alt görevlere böler → Subagent'lar görevleri yürütür → Reviewer Agent kaliteyi denetler → sonuç kullanıcıya sunulur.
- Marketplace üzerinden topluluk tarafından oluşturulan agent takımları paylaşılır ve tek tıkla kurulur.

---

## 2. Agent Hiyerarşisi (Mimari)

```
Kullanıcı Promptu
       │
       ▼
┌─────────────────┐
│  ORCHESTRATOR    │  ← Kullanıcının bağladığı LLM API ile çalışır
│  (Yönlendirici)  │     Görevin hangi domain'e ait olduğunu belirler
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   MAIN AGENT    │  ← Finans, Yazılım, Pazarlama vb. domain uzmanı
│    (Uzman)      │     Görevi alt adımlara böler, Subagent'lara dağıtır
└────────┬────────┘
         │
    ┌────┴────┐
    ▼         ▼
┌────────┐ ┌────────┐
│SUBAGENT│ │SUBAGENT│  ← Tek bir spesifik görev (veri çekme, analiz, vb.)
│(İşçi)  │ │(İşçi)  │
└────┬───┘ └────┬───┘
     │          │
     ▼          ▼
┌─────────────────┐
│    REVIEWER     │  ← İsteğe bağlı (açılıp kapatılabilir)
│   (Denetmen)    │     Hata varsa Subagent'a geri gönderir
└─────────────────┘
```

### Kurallar

- **Orchestrator** yalnızca yönlendirme yapar, doğrudan iş üretmez.
- **Main Agent** alt görev planı oluşturur ve Subagent'ları koordine eder.
- **Subagent** tek bir atomik görev yürütür (örn: Twitter/X duyarlılık analizi, Polymarket veri çekme).
- **Reviewer Agent** isteğe bağlıdır (`reviewer_enabled: boolean`). Aktifse, Subagent çıktısını doğrular; hata bulursa hatayı belirterek Subagent'a geri gönderir. Bu döngü `max_review_iterations` kadar tekrar edebilir.

---

## 3. Teknoloji Stack'i

| Katman | Teknoloji | Amaç |
|---|---|---|
| **Frontend** | Next.js (App Router) + React + TypeScript | UI modülleri, SSR, routing |
| **Backend** | FastAPI (Python) | Agent iletişimi, long-polling, WebSocket, API |
| **API Katmanı** | REST (varsayılan), GraphQL (performans gerekirse) | Frontend-Backend iletişimi |
| **İlişkisel DB** | PostgreSQL | Kullanıcı verileri, abonelikler, faturalandırma |
| **NoSQL DB** | MongoDB | Agent logları, dinamik veriler, marketplace içerikleri |
| **Vektör DB** | **Qdrant** (seçildi) | RAG hafıza sistemi, doküman embedding'leri |
| **Gerçek Zamanlı** | WebSocket (FastAPI) | Canlı agent durumu, kullanıcıya anlık soru sorma |
| **Kimlik Doğrulama** | **Backend JWT** (FastAPI, kendi auth'umuz — seçildi) | Kullanıcı oturum yönetimi |
| **Şifreleme** | AES-256-GCM (API anahtarları için) | BYOK güvenliği |
| **Ücretsiz Model** | **Qwen3** via **Ollama** (OpenAI-uyumlu endpoint) | Ücretsiz katman / lokal geliştirme |
| **Embedding** | **nomic-embed-text** via Ollama | RAG için ücretsiz/lokal embedding |

---

## 4. Proje Dizin Yapısı

```
maestro/
├── CLAUDE.md                        # Bu dosya
│
├── frontend/                        # Next.js + React + TypeScript
│   ├── src/
│   │   ├── app/                     # Next.js App Router sayfaları
│   │   │   ├── (auth)/              # Login, Register sayfaları
│   │   │   ├── dashboard/           # Dashboard & Metrikler
│   │   │   ├── architect/           # Canlı node haritası / log akışı
│   │   │   ├── marketplace/         # Pazar yeri
│   │   │   ├── agents/              # Agent profili & ayarları
│   │   │   ├── settings/            # API yönetimi, kullanıcı profili
│   │   │   └── layout.tsx
│   │   ├── components/
│   │   │   ├── ui/                  # Genel UI bileşenleri (Button, Modal, vb.)
│   │   │   ├── dashboard/           # Dashboard'a özel bileşenler
│   │   │   ├── architect/           # Architect görünümü bileşenleri
│   │   │   ├── marketplace/         # Marketplace bileşenleri
│   │   │   └── agents/              # Agent yönetimi bileşenleri
│   │   ├── hooks/                   # Custom React hook'ları
│   │   ├── lib/                     # Yardımcı fonksiyonlar, API client
│   │   ├── stores/                  # State management (Zustand)
│   │   ├── types/                   # TypeScript tip tanımları
│   │   └── styles/                  # Global stiller
│   ├── public/
│   ├── next.config.ts
│   ├── tailwind.config.ts
│   ├── tsconfig.json
│   └── package.json
│
├── backend/                         # FastAPI (Python)
│   ├── app/
│   │   ├── main.py                  # FastAPI giriş noktası
│   │   ├── core/
│   │   │   ├── config.py            # Ortam değişkenleri ve ayarlar
│   │   │   ├── security.py          # API anahtar şifreleme/çözme
│   │   │   └── database.py          # DB bağlantıları (Postgres, Mongo)
│   │   ├── api/
│   │   │   ├── v1/
│   │   │   │   ├── auth.py          # Kimlik doğrulama endpoint'leri
│   │   │   │   ├── agents.py        # Agent CRUD endpoint'leri
│   │   │   │   ├── tasks.py         # Görev yönetimi endpoint'leri
│   │   │   │   ├── marketplace.py   # Marketplace endpoint'leri
│   │   │   │   ├── api_keys.py      # BYOK API anahtar yönetimi
│   │   │   │   └── dashboard.py     # Metrik endpoint'leri
│   │   │   └── websocket.py         # WebSocket bağlantı yönetimi
│   │   ├── agents/
│   │   │   ├── orchestrator.py      # Orchestrator agent mantığı
│   │   │   ├── main_agent.py        # Main Agent mantığı
│   │   │   ├── subagent.py          # Subagent mantığı
│   │   │   ├── reviewer.py          # Reviewer agent mantığı
│   │   │   └── registry.py          # Agent kayıt ve keşif sistemi
│   │   ├── models/                  # SQLAlchemy & Pydantic modelleri
│   │   │   ├── user.py
│   │   │   ├── agent.py
│   │   │   ├── task.py
│   │   │   └── api_key.py
│   │   ├── services/
│   │   │   ├── llm_service.py       # LLM API entegrasyonu (OpenAI, Anthropic, vb.)
│   │   │   ├── memory_service.py    # RAG & vektör DB yönetimi
│   │   │   ├── marketplace_service.py
│   │   │   └── billing_service.py   # Token/maliyet takibi
│   │   └── utils/
│   │       ├── prompt_guard.py      # Prompt injection koruması
│   │       └── rate_limiter.py      # Rate limiting
│   ├── tests/
│   ├── alembic/                     # PostgreSQL migration'ları
│   ├── requirements.txt
│   └── pyproject.toml
│
├── docker-compose.yml               # Tüm servisler (DB'ler dahil)
├── .env.example                     # Ortam değişkenleri şablonu
└── README.md
```

---

## 5. Kodlama Kuralları

### 5.1 Genel

- **Dil:** Kod, değişken adları, commit mesajları ve yorumlar **İngilizce** yazılır. Kullanıcıya dönük UI metinleri Türkçe olabilir (i18n altyapısı ile).
- **Formatlama:** Frontend → ESLint + Prettier. Backend → Ruff (linter + formatter).
- Tüm fonksiyonlar ve sınıflar **docstring/JSDoc** ile belgelenir.
- **Magic number** ve **magic string** kullanılmaz; sabitler ayrı dosyalarda (`constants.ts`, `constants.py`) tanımlanır.

### 5.2 Frontend (TypeScript / Next.js)

- Bileşenler **fonksiyonel** olmalı, `class component` kullanılmaz.
- State yönetimi için **Zustand** tercih edilir.
- API çağrıları `lib/api/` altında merkezi bir client üzerinden yapılır.
- Tüm API response'ları TypeScript tipleri ile tanımlanır (`types/` altında).
- Sayfa bileşenleri `app/` dizininde, paylaşılan bileşenler `components/` dizininde tutulur.
- CSS için **Tailwind CSS** kullanılır (proje dokümanında modern mimari istendiği için).

### 5.3 Backend (Python / FastAPI)

- **Python 3.11+** kullanılır.
- Tüm endpoint'ler **async** olmalıdır.
- Pydantic v2 modelleri ile request/response validasyonu zorunludur.
- Veritabanı işlemleri **SQLAlchemy (async)** ile yapılır (PostgreSQL için).
- MongoDB işlemleri **Motor** (async MongoDB driver) ile yapılır.
- Business logic **services/** katmanında tutulur; route handler'lar ince olmalıdır.
- Hata yönetimi merkezi bir exception handler ile yapılır.
- Her endpoint için **rate limiting** uygulanır.

### 5.4 Agent Geliştirme Kuralları

- Her agent'ın bir `system_prompt`, `tools` listesi ve `max_iterations` değeri vardır.
- Agent'lar arası iletişim **yapılandırılmış mesajlar** (JSON schema) ile yapılır.
- Subagent çıktıları her zaman şu formatta olmalıdır:
  ```json
  {
    "status": "success | error | needs_review",
    "data": {},
    "metadata": {
      "tokens_used": 0,
      "execution_time_ms": 0,
      "model_used": "string"
    }
  }
  ```
- Reviewer Agent'ın geri bildirim formatı:
  ```json
  {
    "approved": false,
    "issues": ["Açıklama 1", "Açıklama 2"],
    "retry_hints": ["İpucu 1"]
  }
  ```

---

## 6. Veritabanı Şemaları

### PostgreSQL (İlişkisel Veriler)

```
users
├── id (UUID, PK)
├── email (UNIQUE)
├── hashed_password
├── display_name
├── subscription_tier (starter | pro | scale)   ← aktif planın denormalize cache'i
├── created_at
└── updated_at

api_keys
├── id (UUID, PK)
├── user_id (FK → users)
├── provider (openai | anthropic | x | github | custom)
├── encrypted_key (AES-256-GCM ile şifrelenmiş)
├── label
├── is_active
├── created_at
└── updated_at

subscriptions                                   ← kullanıcı başına tek satır
├── id (UUID, PK)
├── user_id (FK → users, UNIQUE)
├── plan (starter | pro | scale)
├── status (active | past_due | canceled | inactive)   ← trial yok; kayıt abonelik oluşturmaz
├── provider (mock | …)                         ← processor-agnostic
├── provider_subscription_id
├── provider_customer_id
├── current_period_start                        ← kota penceresinin çıpası
├── current_period_end
├── trial_end                                   ← legacy, nullable, artık kullanılmıyor (0009)
└── cancel_at_period_end

payment_methods                                 ← ham PAN ASLA saklanmaz
├── id (UUID, PK)
├── user_id (FK → users)
├── provider + provider_payment_method_id
├── brand (visa | mastercard)
├── last4, exp_month, exp_year
└── is_default

usage_records                                   ← append-only kota ledger'ı (kotanın tek güvendiği kaynak)
├── id (UUID, PK)
├── user_id (FK → users)
├── task_id (UNIQUE)                            ← idempotency anahtarı
├── tokens
├── provider, status
└── period_start                                ← subscriptions.current_period_start
```

### MongoDB (Dinamik Veriler)

```
agent_logs             → Agent çalışma geçmişi, adım adım log
marketplace_items      → Paylaşılan agent takımları ve meta verileri
task_sessions          → Görev oturumları ve ara durumları
agent_configurations   → Agent system prompt'ları ve tool tanımları
```

### Vektör DB (Hafıza / RAG)

```
conversation_memories  → Geçmiş konuşma embedding'leri
document_chunks        → Yüklenen doküman parçaları ve embedding'leri
```

---

## 7. API Endpoint Yapısı

```
# Kimlik Doğrulama
POST   /api/v1/auth/register
POST   /api/v1/auth/login
POST   /api/v1/auth/refresh

# API Anahtar Yönetimi (BYOK)
GET    /api/v1/api-keys
POST   /api/v1/api-keys
DELETE /api/v1/api-keys/{id}

# Abonelik & Faturalandırma
GET    /api/v1/billing/plans            # Kullanıcıya özel fiyatlanmış 3 plan
GET    /api/v1/billing/subscription     # Plan, durum + canlı kota tüketimi
POST   /api/v1/billing/subscribe        # Kart al, ilk dönemi tahsil et, planı aktive et
POST   /api/v1/billing/cancel           # Yenilemeyi durdur (dönem sonuna kadar kullanılır)
GET    /api/v1/billing/payment-method   # Yalnızca brand + last4 + expiry

# Agent Yönetimi
GET    /api/v1/agents
POST   /api/v1/agents
GET    /api/v1/agents/{id}
PUT    /api/v1/agents/{id}
DELETE /api/v1/agents/{id}
PATCH  /api/v1/agents/{id}/system-prompt

# Görev Yönetimi
POST   /api/v1/tasks                    # Yeni görev başlat
GET    /api/v1/tasks/{id}               # Görev durumu sorgula
POST   /api/v1/tasks/{id}/cancel        # Görevi iptal et
WS     /api/v1/tasks/{id}/stream        # Canlı görev akışı (WebSocket)

# Dashboard & Metrikler
GET    /api/v1/dashboard/metrics        # Genel metrikler
GET    /api/v1/dashboard/token-usage    # Token kullanımı
GET    /api/v1/dashboard/cost-summary   # Maliyet özeti

# Marketplace
GET    /api/v1/marketplace              # Agent takımlarını listele
POST   /api/v1/marketplace              # Agent takımı yayınla
POST   /api/v1/marketplace/{id}/install # Tek tıkla kurulum
GET    /api/v1/marketplace/{id}/reviews # Değerlendirmeler

# Architect (Canlı Görünüm)
WS     /api/v1/architect/live           # Canlı agent haberleşme akışı
```

---

## 8. UI Modülleri ve Sayfalar

| Modül | Route | Açıklama |
|---|---|---|
| **API Management** | `/settings/api-keys` | BYOK anahtar yönetimi. Eksik API uyarı sistemi. |
| **Dashboard** | `/dashboard` | API istek sayıları, uptime, token kullanımı, başarı/başarısızlık oranları. |
| **Architect** | `/architect` | Canlı node haritası veya log akışı. Hangi subagent ne yapıyor, kime veri gönderiyor. |
| **Marketplace** | `/marketplace` | Topluluk agent takımları. Tek tıkla kopyala & entegre et. |
| **Agent Profili** | `/agents/{id}` | System Prompt düzenleme, araç (tool) atama, davranış ayarları. |
| **Kullanıcı Profili** | `/settings/profile` | Hesap kişiselleştirme, abonelik yönetimi. |

---

## 9. Güvenlik Politikaları

### 9.1 API Anahtar Güvenliği (BYOK)

- API anahtarları **AES-256-GCM** ile şifrelenir, düz metin olarak asla saklanmaz.
- Şifreleme anahtarı (master key) environment variable olarak tutulur, kod tabanında yer almaz.
- API anahtarları frontend'e asla döndürülmez; yalnızca `provider` ve `label` bilgisi gösterilir.
- Görev başlatıldığında gerekli API eksikse, sistem görevi **durdurur** ve kullanıcıyı uyarır.

### 9.2 Sonsuz Döngü Koruması

- Her Subagent için `max_iterations` limiti tanımlanır (varsayılan: 10).
- Reviewer ↔ Subagent döngüsü için `max_review_iterations` limiti tanımlanır (varsayılan: 3).
- Toplam görev süresi için `task_timeout_seconds` limiti uygulanır (varsayılan: 300).
- Limit aşıldığında görev durdurulur, kullanıcıya bilgi verilir ve log kaydedilir.

### 9.3 Prompt Injection Koruması

- Marketplace'e yüklenen agent takımları otomatik **güvenlik taramasından** geçer.
- System prompt'larda zararlı pattern tespiti yapılır.
- Marketplace agent'ları, kurulum yapan kullanıcının API anahtarlarına **doğrudan erişemez**; tüm API çağrıları sandbox'lanmış servis katmanı üzerinden yapılır.

### 9.4 Genel Güvenlik

- Tüm endpoint'ler JWT tabanlı kimlik doğrulama gerektirir (public olanlar hariç).
- Rate limiting tüm endpoint'lerde aktiftir.
- Input validasyonu Pydantic ile zorunludur.
- CORS politikası sadece bilinen origin'lere izin verir.
- Environment variable'lar `.env` dosyasında tutulur, `.gitignore`'a eklenir.

---

## 10. Hafıza ve RAG Sistemi

- Agent'lar geçmiş konuşmaları ve yüklenen dokümanları **hatırlar**.
- Vektör DB'de conversation embedding'leri ve document chunk'ları saklanır.
- Her görev başlangıcında ilgili hafıza bağlamı (context) RAG ile çekilir ve agent'a enjekte edilir.
- Hafıza kapsamı kullanıcıya özeldir; farklı kullanıcıların verileri birbirinden izole edilir.

---

## 11. Lokal/Ücretsiz Model Desteği

- Kullanıcılar kendi **OpenAI**, **Anthropic (Claude)** veya diğer provider API anahtarlarını girebilir (BYOK).
- Ücretsiz katman ve lokal geliştirme için **Qwen3**, **Ollama** üzerinden (OpenAI-uyumlu endpoint `http://localhost:11434/v1`) sunulur. Böylece tüm akış lokalde bedava çalışabilir.
- RAG embedding'leri de ücretsiz/lokal kalması için **nomic-embed-text** (Ollama) ile üretilir.
- LLM servis katmanı (`llm_service.py`) provider-agnostic olmalıdır; her provider bir **adapter** class'tır. İlk/varsayılan adapter `OllamaAdapter`'dır. Yeni provider eklemek = yeni adapter eklemek (mevcut kod değişmez).

---

## 12. Gerçek Zamanlı İletişim

- **WebSocket** bağlantıları üzerinden:
  - Görev ilerleme durumu canlı olarak kullanıcıya aktarılır.
  - Agent'lar çalışma sırasında kullanıcıya soru sorabilir (human-in-the-loop).
  - Architect görünümü için canlı agent haberleşme akışı sağlanır.
- Bağlantı koptuğunda yeniden bağlanma (reconnection) mekanizması uygulanır.
- Long-polling, WebSocket desteklenmeyen ortamlar için fallback olarak tutulur.

---

## 13. Geliştirme Ortamı Komutları

```bash
# Frontend
cd frontend
npm install
npm run dev              # Geliştirme sunucusu (localhost:3000)
npm run build            # Production build
npm run lint             # ESLint kontrolü
npm run type-check       # TypeScript tip kontrolü

# Backend
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload    # Geliştirme sunucusu (localhost:8000)
pytest                           # Testleri çalıştır
ruff check .                     # Lint kontrolü
ruff format .                    # Kod formatlama

# Docker (Tüm Sistem)
docker-compose up -d             # Tüm servisleri başlat
docker-compose down              # Tüm servisleri durdur
```

---

## 14. Ortam Değişkenleri (.env)

```env
# Veritabanı
POSTGRES_URL=postgresql+asyncpg://user:pass@localhost:5433/maestro
MONGODB_URL=mongodb://localhost:27017/maestro

# Güvenlik
JWT_SECRET=<random-secret>
API_KEY_MASTER_KEY=<aes-256-master-key>
CORS_ORIGINS=http://localhost:3000

# Vektör DB (Qdrant)
QDRANT_URL=http://localhost:6333
QDRANT_API_KEY=

# Rate limiting
# REDIS_URL boşsa bucket'lar process belleğinde tutulur (tek worker'lık dev/test).
REDIS_URL=
RATE_LIMIT_ENABLED=true
# Yalnızca X-Forwarded-For ekleyen bir reverse proxy arkasındayken true.
TRUST_PROXY_HEADERS=false

# Ücretsiz Model (Ollama — OpenAI-uyumlu)
FREE_MODEL_ENDPOINT=http://localhost:11434/v1
FREE_MODEL_NAME=qwen3
EMBEDDING_MODEL_NAME=nomic-embed-text

# Varsayılan Limitler
MAX_ITERATIONS=10
MAX_REVIEW_ITERATIONS=3
TASK_TIMEOUT_SECONDS=300

# Ödeme sağlayıcı (yalnızca "mock" implement edildi; gerçek processor = yeni adapter)
# Fiyat/kota değerleri secret değil → constants.py'de tutulur. Trial/indirim yok.
PAYMENT_PROVIDER=mock

# Observability (boş DSN = tamamen kapalı, sıfır egress)
LOG_FORMAT=text                  # prod'da "json" (structured, satır başına obje)
SENTRY_DSN=                      # backend Sentry projesi
SENTRY_TRACES_SAMPLE_RATE=0.0
SENTRY_ENVIRONMENT=              # boşsa ENVIRONMENT'a düşer
# Frontend'in DSN'i AYRI bir Sentry projesidir; prod compose'ta
# FRONTEND_SENTRY_DSN olarak verilir (backend'inki env_file ile gider).

# Frontend: kanonik URL / sitemap / OG origin'i (şema dahil). Server-only,
# request-time'da okunur; NEXT_PUBLIC_ DEĞİL (imaj domain-agnostik kalmalı).
# Boşsa placeholder domain'e düşer. DOMAIN'den türetilmez (şema çakışması).
SITE_URL=https://maestro.example.com
```

---

## 15. Dikkat Edilmesi Gereken Kritik Noktalar

> ⚠️ Bu kurallar her zaman geçerlidir:

1. **API anahtarlarını asla log'lama, düz metin saklama veya frontend'e döndürme.**
2. **Agent döngülerinde mutlaka iterasyon limiti uygula.**
3. **Marketplace içerikleri için güvenlik taraması atlanmamalıdır.**
4. **Kullanıcı verileri (hafıza dahil) mutlaka izole edilmelidir — bir kullanıcının verisi başka kullanıcıya sızmamalıdır.**
5. **Her yeni LLM provider entegrasyonu adapter pattern ile yapılmalıdır; mevcut kodu değiştirmek yerine yeni adapter eklenmeli.**
6. **WebSocket bağlantılarında kimlik doğrulama zorunludur.**
7. **Veritabanı migration'ları Alembic ile yönetilir; elle SQL çalıştırılmaz.**
8. **Bu proje bir web platformudur; global `torch device` (CUDA→MPS→CPU) kuralı burada geçerli DEĞİLDİR.** Yerel torch modeli çalıştırılmaz; tüm LLM/embedding işlemleri HTTP üzerinden (Ollama/BYOK provider) yapılır.
9. **Ham kart numarası (PAN) asla saklanmaz, loglanmaz veya response'a konmaz.** Yalnızca `brand + last4 + expiry` kalıcıdır. PAN sadece `CardDetails` içinde, tek bir provider çağrısı boyunca bellekte yaşar.
10. **Hesap purge'ünde PostgreSQL satırı EN SON silinir.** `deletion_requested_at` flag'i, sweep'in hesabı tekrar bulma yoludur; Mongo ve Qdrant temizlenmeden PG satırı silinirse veri öksüz kalır ve geri dönüşü olmaz. `purge_user_data` hata yutmaz — fırlatır ki sweep retry etsin.
11. **Kota yalnızca Postgres `usage_records` üzerinden enforce edilir.** MongoDB `task_sessions` sadece analitiktir. Token'lar `TokenMeter` ile sayılır ve `_run_task`'ın `finally` bloğunda — başarı, hata, timeout, iptal — her terminal yolda ledger'a yazılır.
12. **Her yeni endpoint açık bir `dependencies=[rate_limit(...)]` taşımalı.** Router seviyesinde default verilmez: FastAPI router- ve route-level dependency listelerini birleştirir, override eden route iki kez sayılır. `tests/test_rate_limiter.py` unutulan route'u yakalar. Yeni bir WebSocket route'u `accept()`'ten önce `check_websocket` çağırmalı ve testteki allow-list'e eklenmeli.
13. **`TRUST_PROXY_HEADERS` yalnızca `X-Forwarded-For` ekleyen bir proxy arkasında `true` olmalı.** Backend doğrudan internete açıksa client header'ı forge edip her istekte yeni bucket açar. Proxy arkasında `false` bırakmak da ters yönde bozar: herkes proxy'nin IP'si altında tek bucket paylaşır.

---

## 16. Build Status / Roadmap

> Geliştirme **dikey dilim (vertical-slice-first)** yaklaşımıyla ilerler: önce sağlam temel, sonra uçtan uca çalışan tek bir akış. Diğer modüller stub olarak durur ve sonraki turlarda doldurulur.

### Tur 1 — Tamamlandı (uçtan uca çalışan akış)
- **Canlı:** Auth (register/login/refresh, JWT), BYOK API-key yönetimi (AES-256-GCM), görev akışı (Orchestrator→Main→Subagent→opsiyonel Reviewer, Ollama/Qwen3 ile), WebSocket canlı task/architect akışı.
- **UI (canlı):** `(auth)` sayfaları, `settings/api-keys`, görev başlatma ekranı, `architect` canlı görünüm.

### Tur 2 — Tamamlandı (modül derinleştirme)
- **RAG:** Görev başında per-user hafıza + doküman chunk'ları (`document_chunks`) retrieval ile agent prompt'larına enjekte edilir. Doküman yükleme (`/documents`, .txt/.md → chunk+embed).
- **LLM adapter'ları:** `OllamaAdapter` + `OpenAIAdapter` (çalışır), `AnthropicAdapter` (gerçek Messages API — `x-api-key`, `system`, `max_tokens`).
- **Dashboard:** `billing_service` gerçek token/başarı/maliyet toplama (`task_sessions`); `/dashboard` metrik + grafik UI.
- **Agent profili:** `agent_configurations` üzerinden özel agent CRUD + tool atama editörü (`/agents`, `/agents/{id}`); system prompt yazımında güvenlik taraması.
- **Marketplace:** yayınla (zorunlu güvenlik taraması) + tek tıkla kur + install sayacı; `/marketplace` UI.
- **Human-in-the-loop:** Main Agent belirsizlikte tek bir netleştirme sorusu sorabilir; WS inbound + `POST /tasks/{id}/answer` ile yanıtlanır. Görev iptali UI'da.
- **Dev script'leri:** `scripts/dev.ps1` (Windows) + `scripts/dev.sh` (macOS/Linux) — infra + backend + frontend.

### Tur 3 — Tamamlandı (abonelik + kota)
- **Planlar:** Free tier yok, trial yok, indirim yok (bkz. aşağıdaki "Fiyatlandırma sadeleştirmesi" turu). `starter` $5 / `pro` $15 / `scale` $50 aylık; sırasıyla 500K / 3M / 10M token kotası. Yeni kayıt **abonelik oluşturmaz** → ürünü kullanmak (yerel Ollama modeli dahil, çünkü hosted'da o da sunulan bir hizmet) için tam fiyattan abone olmak şart; abonelik yoksa `POST /tasks` **HTTP 402**.
- **Ödeme katmanı:** `services/payment/` — `PaymentProvider` protokolü + `MockPaymentProvider` (sıfır bağımlılık, sıfır network). Visa/Mastercard **şema** desteği: Luhn + BIN→marka tespiti. Stripe **kullanılmıyor**; gerçek processor (iyzico/PayTR/Adyen/Stripe) = tek yeni adapter dosyası, mevcut kod değişmez. `create_subscription`'ın `first_amount_cents`/`recurring_amount_cents` ayrımı korunur ama bugün ikisi eşittir (ilk dönem indirimi yok).
- **Kota enforcement:** `POST /tasks` (tek giriş noktası) → `quota_service.enforce_can_start_task`. Pre-flight görevin maliyetini bilemez; yalnızca zaten limitte/üstündeyken bloklanır.
- **Token muhasebesi düzeltmeleri:** `TokenMeter` adapter'ı tüm LLM çağrılarını (orchestrator, planner, subagent, reviewer, synthesis) sayar — eskiden sadece subagent'lar sayılıyordu (~%45 eksik). `_run_task` tamamen `try/finally` ile sarıldı: iptal/hata/timeout eden görevler de harcadıkları token'ı öder ve terminal duruma geçer.
- **UI:** `/settings/billing` — kota göstergesi, plan grid'i (liste fiyatı), canlı Luhn + marka tespitli kart formu. Abonesiz kullanıcı (subscription 404) plan grid'ini görüp abone olur. Profil sayfasındaki mock plan seçici kaldırıldı.

### Tur 4 — Tamamlandı (hukuk, güven, silme hakkı)
- **Legal sayfalar:** `/legal` hub + `/terms`, `/privacy` (KVKK+GDPR), `/security` (BYOK güven sayfası), `/acceptable-use`, `/cookies`. Metinler `frontend/src/lib/legal/` altında modül başına bir dosya; `LEGAL_DOCS` registry hem hub'ı hem footer'ı besler (drift imkânsız). Operatör bilgileri tek yerde: `lib/legal/config.ts`.
- **Dürüstlük flag'leri:** `BILLING_LIVE=false` → `/terms` ve `/pricing`'te "no real payments are processed" bandı. `KVKK_TURKISH_PENDING=true` → `/privacy`'de Türkçe metnin hazırlandığı notu. İkisi de tek satır değişimiyle kapanır.
- **Cookie notice:** Sahte Accept/Reject yok — JWT `localStorage`'da ve strictly-necessary, tracking sıfır. `stores/consent.ts` `analytics` slotuyla ileriye hazır.
- **Hesap silme (GDPR Md.17 / KVKK Md.7):** `users.deletion_requested_at` tek kaynak. Talep → hesap anında kilitli (`ActiveUser` dep'i tüm ürün endpoint'lerinde 403; login/refresh çalışır ki self-servis geri alma mümkün olsun) → 30 gün içinde `POST /users/me/deletion/cancel` ile geri alınır → süre dolunca `python -m app.scripts.purge_deleted_accounts` (cron) kalıcı siler. Veri dışa aktarma: `GET /users/me/export` (Md.20).
- **Düzeltilen iki erasure defect'i:** (1) `agent_logs` dokümanlarına `user_id` yazılmıyordu, purge filtresi sıfır doküman eşleştiriyordu — write path düzeltildi, eski satırlar `task_id` üzerinden siliniyor. (2) Qdrant vektörleri (`conversation_memories` + `document_chunks`) hiç silinmiyordu — `memory_service.purge_user_vectors` eklendi.
- **Purge kontratı:** Sıra Mongo → Qdrant → **PG en son** (flag'i taşıyan satır, retry'ın çıpası). `purge_user_data` artık hata yutmuyor, fırlatıyor; sweep kullanıcı bazında yakalar, flag durur, sonraki run retry eder. Tüm işlemler idempotent. `marketplace_items` silinmez, `author_id` unset edilip anonimleştirilir.
- **Abonelik:** Silme talebinde yalnızca **ACTIVE** abonelik iptal edilir (abonesiz hesapta iptal edilecek bir şey yoktur). Geri yükleme cancelled planı diriltmez — kullanıcı yeniden abone olur.

### Tur 5 — Tamamlandı (deployment)
- **Container'lar:** `backend/Dockerfile` (multi-stage `python:3.11-slim`, venv, non-root, urllib healthcheck; `alembic/`+`alembic.ini` imajda çünkü migration ve purge cron aynı imajı kullanır) ve `frontend/Dockerfile` (Next `output: 'standalone'`, iki stage de bookworm-slim — musl/glibc karışımı standalone'un trace ettiği native modülleri runtime'da bozar). `frontend/public/` bu repoda yok, runner stage onu kopyalamıyor.
- **Tek origin:** `docker-compose.prod.yml` + `Caddyfile`. Caddy `/api/*` ve `/health`'i backend'e, kalanı frontend'e verir; WebSocket upgrade'i sıfır konfigle geçirir ve hijack edilmiş bağlantıya timeout uygulamaz (1800s'lik task stream'i açık kalır). Yalnızca Caddy port yayınlar. CORS tamamen ortadan kalkar, `NEXT_PUBLIC_*` boş default'a düşer → imaj domain-agnostik, bir kez build edilir.
- **Düzeltilen üç deployment defect'i:** (1) `/pricing` ve `/templates` `force-dynamic` server component'i; frontend container'ının içinden fetch atıyorlar ve relative URL'in sunucuda base'i yok — `api.ts:apiBase()` client/server ayrımı yapıp `INTERNAL_API_ORIGIN` kullanıyor. Eskiden `try/catch` hatayı yutup sayfayı kalıcı "unreachable" fallback'inde bırakırdı, CI yeşil kalırdı. (2) `embed_texts()` provider'dan bağımsız olarak `FREE_MODEL_ENDPOINT`'e gidiyordu ve auth header göndermiyor — artık ayrı `EMBEDDING_ENDPOINT` ayarı var (boşsa eskisine düşer, dev değişmez), prod'da yalnızca `nomic-embed-text` çeken küçük bir `ollama` servisine bakar. Yoksa doküman yükleme 500 verir, RAG sessizce ölür. (3) Frontend'in `/docs` marketing sayfası ile FastAPI Swagger çakışıyordu; `ENVIRONMENT=production`'da `docs_url`/`redoc_url`/`openapi_url` kapalı.
- **CI/CD:** `ci.yml`'e PR'da Dockerfile build doğrulaması eklendi; `docker-publish.yml` GHCR'a push eder (`main` → amd64, `v*` tag → amd64+arm64, çünkü Oracle Always Free Ampere ARM'dir ve QEMU altında `next build` çok yavaş); `deploy.yml` tag'de `environment: production` onayıyla SSH üzerinden `pull && up -d` çalıştırır. `migrate` one-shot servisi `alembic upgrade head` koşar, `backend` onu `service_completed_successfully` ile bekler — başarısız migration eski backend'i ayakta bırakır.
- **Prod kararları:** `CODE_EXECUTION_ENABLED=false` (açmak `/var/run/docker.sock` mount'u ister = host devralma). Mongo root auth + `?authSource=admin` zorunlu. Qdrant `v1.18.2`'ye pinlendi, healthcheck yok (imaj distroless). Purge cron host crontab'ında. Belge: `docs/DEPLOYMENT.md`.
- **Bilinen mimari sınır:** Barındırılan bir instance kullanıcının kendi makinesindeki Ollama'ya erişemez — tüm LLM çağrıları backend-side, dolayısıyla `localhost:11434` sunucunun kendisidir. `ollama` provider'ı ancak operatör container'a bir sohbet modeli çekerse ya da kullanıcı tüm stack'i kendi makinesinde koşarsa çalışır. Sohbet modeli yokken hata görünür olmuyor: her subtask `ollama chat failed` ile düşüyor ama task yine `completed` + `"No successful subtask output."` dönüyor (duman testinde gözlendi). Bu `task_service`'in mevcut davranışı; tüm subtask'ları error olan bir görev `completed` sayılmamalı — ayrı bir iş.

### Tur 6 — Tamamlandı (rate limiting)
- **Düzeltilen prod defect'i:** limiter `request.client.host` ile anahtarlıyordu; Caddy arkasında bu her zaman Caddy container'ının IP'sidir, yani **tüm kullanıcılar tek bir bucket paylaşıyordu** — bir kişi `/auth/login`'in 20/dk limitini doldurunca herkes 429 yiyordu. Limiter yoktan kötüydü. Artık kimlik: geçerli access token varsa `user:{jwt_sub}`, yoksa `ip:{addr}`; IP de `trust_proxy_headers` açıkken `X-Forwarded-For`'un **en sağdaki** girdisinden okunuyor (Caddy'nin eklediği hop; client'ın forge edemeyeceği tek değer). Uvicorn'un `--proxy-headers`'ına bilerek güvenilmiyor — XFF'in hangi ucunu okuduğu sürümler arasında değişti.
- **Kapsam:** eskiden yalnızca `auth` (register/login), `POST /tasks`, `billing` ve `marketplace` throttle'lıydı. Artık her HTTP route'unda açık `dependencies=[...]` var; `users`, `api-keys`, `dashboard`, `agents`, `documents`, `auth/refresh` ve iki WebSocket eklendi. `tests/test_rate_limiter.py::test_every_http_route_declares_a_rate_limit` `app.routes`'u gezip limitsiz route bulursa fail eder — §9.4 kendini korur. (Bu FastAPI sürümü route'ları `_IncludedRouter` altında iç içe tutuyor; walker recursive ve kendi sağlığını ayrı bir testle doğruluyor, yoksa boş liste üzerinde sessizce geçerdi.)
- **Backend'ler:** `RateLimitBackend` protokolü + `MemoryBackend` (sliding-window deque, artık drained bucket'ları süpürüyor — eskiden IP churn'ünde sınırsız büyürdü) ve `RedisBackend` (tek Lua script'te atomik ZSET sliding-window log). `Limiter` dispatcher'ı Redis'i dener, `RedisError`/`OSError`/timeout'ta uyarı loglayıp memory'ye düşer ve 10 sn'lik bir circuit breaker açar (yoksa her istek connect timeout öder). Redis outage'ı API outage'ı değildir.
- **Lua ayrıntısı:** `ZRANGE ... WITHSCORES`'un Lua içindeki şekli RESP2/RESP3'e göre değişiyor (fakeredis iç içe tablo, gerçek Redis düz dizi döndürdü). Script ayrı bir `ZSCORE` kullanıyor; protokolden bağımsız. `member` Python'da üretilir, script deterministik kalsın diye.
- **Tier'lar `constants.py`'de:** public 30 / auth 20 / read 60 / write 20 / payment 10 / expensive 30 / upload 10 / websocket 30 (hepsi 60 sn). Bucket anahtarı `rl:{tier}:{scope}:{identity}`; `scope` iki router'ın aynı tier'ı paylaşıp bütçeyi paylaşmasını engeller.
- **WebSocket:** `Depends` handshake'ten önce reddedemez, bu yüzden `_authenticate` `accept()`'ten önce `check_websocket`'i elle çağırır; aşımda `close(1013)`. Token query param'dan okunur.
- **Konfig:** `REDIS_URL` boş → memory backend (dev + pytest, ekstra servis yok). `RATE_LIMIT_ENABLED`, `TRUST_PROXY_HEADERS`. Dev ve prod compose'a `redis:7-alpine` eklendi; prod'da `requirepass` + `allkeys-lru` + persistence kapalı (bucket'lar zaten 60 sn'de expire olur).

### Tur 7 — Tamamlandı (SEO altyapısı)
- **Sorun:** SEO yüzeyi sıfırdı — `frontend/public/` yok, `sitemap`/`robots`/`manifest`/`icon`/`opengraph-image` hiçbiri yok, root `layout.tsx` yalnız title+description taşıyordu, 11 marketing sayfasının hiçbirinde canonical/OG yoktu. Link paylaşımı görselsiz/başlıksız çıkıyordu.
- **Çözülen çatışma:** Canonical/OG mutlak URL ister; Tur 5 imajın domain-agnostik kalmasını ister. `NEXT_PUBLIC_SITE_URL` build-time inline eder → çözüm **server-only runtime `SITE_URL`**. Root `layout.tsx` `generateMetadata` içinde `await connection()` ile render'ı request-time'a iter (yoksa `next build` değeri dondurur — domain-agnostik imajda hiç). `SITE_URL` yalnız 3 dosyada okunur: `layout.tsx` (connection), `sitemap.ts` + `robots.ts` (`force-dynamic`). Diğer sayfalar canonical/OG'yi **relative** verir; `metadataBase` mutlaklaştırır.
- **`SITE_URL` boş-string tuzağı:** `process.env.SITE_URL ?? PLACEHOLDER` boş string'i yakalamaz (`??` yalnız undefined/null) → `new URL('/', '')` fırlatır. `?.trim() || PLACEHOLDER` ile hem unset hem boş "placeholder"a düşer. `site-url.ts` `import 'server-only'` taşır (client import'u build'i patlatır).
- **Merkezi config:** `lib/seo/config.ts` (client-safe, env yok) — `SITE_NAME = LEGAL_ENTITY.brand`, `TITLE_TEMPLATE = '%s — Maestro'` (suffix tek yerde), `BRAND` renkleri (tailwind primary/background ile aynı hex), `MONOGRAM_PATH` (LandingNav ile birebir). `buildPageMetadata({title,description,path})` helper'ı 11 sayfadaki tekrarı kaldırır.
- **Görseller kodla üretilir:** `icon.svg` (statik), `opengraph-image.tsx` + `apple-icon.tsx` (`next/og` `ImageResponse`, Node runtime, gömülü font — `public/` yok, binary commit yok, Dockerfile değişmez). `twitter-image` OG'den re-export. Ortak `lib/seo/og-monogram.tsx`.
- **Sitemap drift-proof:** route listesi `MARKETING_NAV_LINKS` + `LEGAL_DOCS`'tan türetilir; tek elle giriş `/legal` hub'ı.
- **JSON-LD:** root layout `<body>`'de `Organization` + `SoftwareApplication` graph'ı (fiyat/plan gömülmez — backend tek kaynak). `</script>` escape'li.
- **Yapılmadı (bilinçli):** `(app)`/`(auth)` client layout'ları noindex-meta için bölünmedi — `robots.ts` disallow zaten crawl'ı engelliyor.
- **Doğrulandı:** `type-check`/`lint`/`build` temiz; build tablosunda `sitemap.xml`/`robots.txt`/marketing sayfaları `ƒ`, görseller `○`; farklı `SITE_URL` ile `robots.txt` çıktısı değişiyor (runtime kanıtı); tüm görsel route'ları 200 + doğru content-type.

### E-posta Doğrulama & Transactional E-posta — Tamamlandı
- **Provider katmanı:** `services/email/` — `EmailProvider` protokolü + `ConsoleEmailProvider` (varsayılan; mesajı loglar, dev/self-host'ta doğrulama linki log'dan alınır, sıfır bağımlılık/network) + `ResendProvider` (httpx, retry+backoff; 429/5xx/network transient sayılır, kalıcı 4xx anında fırlar; API key ve ham response body asla loglanmaz). `PaymentProvider` deseninin birebir aynısı: yeni gerçek gönderici = tek adapter dosyası. Şablonlar `templates.py`'de (kod içine gömülü değil), her tip `(subject, html, text)` döner.
- **Token modeli (migration 0008):** `users.email_verified` (bool, default false) + `email_tokens` tablosu. Yalnızca token'ın SHA-256 hash'i saklanır; ham token sadece e-posta linkinde yaşar. Tek kullanımlık (`used_at`), TTL constants.py'de (verify 24s / reset 60dk), aynı (user, purpose) için yeni token eskiyi geçersizler. Satır kullanıcıyla CASCADE silinir → purge kontratına ekstra adım gerekmez.
- **`email_service`:** `issue_token`/`consume_token` commit'i çağırana bırakır (endpoint transaction'ıyla kompoze olur); `consume_token` bilinmeyen/kullanılmış/yanlış-amaç/süresi-dolmuş için ayrımsız `None` döner. `send_*` helper'ları **asla fırlatmaz** — provider hatası loglanır (yalnızca subject + exception sınıfı; alıcı adresi/token/gövde/traceback yok) ve endpoint devam eder.
- **4 endpoint (auth router, `RATE_LIMIT_AUTH`):** `verify-email` (public, tek kullanım), `resend-verification` (auth; doğrulanmışsa yine 202, e-posta göndermez → durum sızmaz), `forgot-password` (her zaman 202, enumeration'a kapalı; silme-kilitli hesaplar için de çalışır), `reset-password` (invalid→400; başarıda parola + **tüm refresh session'ları iptal**). Register `start_trial` sonrası token'ı transaction içinde üretir, **commit sonrası** e-posta yollar (e-posta veriden önce gidemez / veriyle rollback olmaz).
- **Yumuşak kapı:** `deps.VerifiedUser` (`ActiveUser` üzerine katmanlı) yalnız `POST /tasks` + `POST /api-keys`'e uygulanır; `email_verification_required and not user.email_verified` iken 403. `EMAIL_VERIFICATION_REQUIRED=false` ile self-host'ta kapatılır (e-posta yine gider). Diğer tüm route'lar `ActiveUser`'da kalır.
- **Silme yaşam döngüsü e-postaları:** `request_deletion` yalnız taze yolda (idempotent tekrar sessiz) commit sonrası "silme planlandı" (purge tarihi gövdede) yollar; `cancel_deletion` yalnız `was_locked` iken "hesap geri yüklendi" yollar.
- **Frontend:** `api.verifyEmail/resendVerification/forgotPassword/resetPassword` + `UserPublic.email_verified`; `(app)` layout'ta doğrulama banner'ı (`email_verified === false` iken, resend butonlu); register'da toast; login'de "Forgot password?" linki; 3 yeni sayfa `/verify-email` (StrictMode-güvenli `useRef` guard, tek kullanımlık token'ı iki kez yakmaz), `/forgot-password` (enumeration-nötr kopya), `/reset-password` (`useSearchParams` → `<Suspense>` sarmalı, uzunluk+eşleşme validasyonu).
- **Config:** `EMAIL_PROVIDER` (console|resend), `RESEND_API_KEY`, `EMAIL_FROM`, `SITE_URL` (backend'in link kurmak için okuduğu kendi kopyası — frontend'in server-only `SITE_URL`'ünden ayrı), `EMAIL_VERIFICATION_REQUIRED`; prod'da `EMAIL_PROVIDER=resend` iken `RESEND_API_KEY` boşsa boot reddedilir. `.env.example` + `docs/DEPLOYMENT.md` güncellendi.
- **Doğrulandı:** backend `pytest` 524 geçer, `ruff check`/`format` temiz; frontend `type-check`/`lint`/`build` temiz, build tablosunda 3 yeni route.

### Gözlemlenebilirlik — Tamamlandı
- **Zaten vardı (önceki iş, bu turda korundu):** backend Sentry (`core/observability.py`, env-gated, PII scrub) + stdlib `JsonLogFormatter` (`LOG_FORMAT=json`) + `/health` & `/health/ready` probe'ları. "Observability sıfır" tespiti bu tur itibarıyla tamamen kapandı.
- **Frontend Sentry (`@sentry/nextjs@10`):** DSN **runtime'da** okunur (Umami/SITE_URL server-only deseninin birebiri: `lib/observability/config.ts` `server-only`, layout `connection()` ile dinamik, DSN prop → `SentryInit` client component) — imaj domain-agnostik kaldı, `NEXT_PUBLIC_*` yok. SDK **dynamic import**: DSN boşken Sentry chunk'ı tarayıcıya hiç inmez, sıfır egress. Server tarafı `src/instrumentation.ts` (`register` + `onRequestError`). 3 error boundary `reportError()` çağırır (`console.error` da kalır). **Bilinçli yok:** `withSentryConfig`/source-map upload (CI token istemez; client stack'ler minified), tunnel route (ad-blocker browser event'i düşürebilir; server yakalama etkilenmez), Replay (bundle+PII). `tracesSampleRate: 0`, `sendDefaultPii: false`. Compose'ta `FRONTEND_SENTRY_DSN` (backend'in `SENTRY_DSN`'i env_file ile gittiği için ayrı ad — iki ayrı Sentry projesi).
- **Request-ID + access log:** `main.py`'de `@app.middleware("http")` — her istekte server-side üretilen id (`X-Request-ID` yanıt header'ı, inbound header'a güvenilmez: Caddy set etmiyor, forge edilebilir), `maestro.access` logger'ına `extra={request_id, method, path, status, duration_ms}` ile tek satır; `/health*` hariç. Unhandled exception'da access satırı middleware içindeki `try/except+raise` ile yazılır (handler ServerErrorMiddleware'de, middleware'in DIŞINDA — "sadeleştirme" diye kaldırma). Exception handler 500'e de `X-Request-ID` koyar. Sentry event'ine `set_tag("request_id")`.
- **WS hata görünürlüğü:** `websocket.py` artık logger taşıyor; `_run_stream` sarmalayıcısı beklenmedik hatayı `logger.exception` (extra: task_id/user_id) + `close(1011)` ile yakalar (eskiden uvicorn içinde sessizce ölüyordu). `_receive_answers` bozuk JSON'da socket'i öldürmek yerine warning + continue.
- **Seviye disiplini:** agent fallback'leri (orchestrator classification, plan retry, sibling subtask crash, synthesis, reviewer auto-approve) **WARNING** — Sentry `LoggingIntegration(event_level=ERROR)` olduğu için flood etmez; task başına tek Sentry event'i `task_service`'teki ERROR/exception olarak kalır. `task_service` log çağrılarına `extra={task_id, user_id}` eklendi (JSON loglar filtrelenebilir).
- **Infra:** `docker-compose.prod.yml`'e `x-logging` anchor'ı (`json-file`, 10m×5, tüm servisler; stack toplamı ~550MB tavan — eskiden sınırsız büyüyordu); `Caddyfile`'a JSON access log (stdout, rotasyonu compose cap'leri yapar).
- **Metrik YOK (bilinçli, korunan karar):** Prometheus/Grafana kurulmadı (RAM); uptime dış servisle (`/health` + `/health/ready`). Hata görünürlüğü Sentry + structured log + Mongo `task_sessions` üzerinden.
- **Doğrulandı:** backend `pytest` 532 (524+8 yeni: request-context 5, WS logging 3), `ruff` temiz; frontend `type-check`/`lint`/`build` temiz. Kalan risk: standalone imajda `@sentry/nextjs` server trace'i yalnız Docker build kanıtlar — patlarsa `outputFileTracingIncludes` (aynı OG-image riski gibi, aşağıda).

### Fiyatlandırma sadeleştirmesi — Tamamlandı (2026-07-12)
- **Karar:** Free tier yok, 14 gün trial yok, %50 ilk-ay indirimi yok. Her şey (yerel Ollama modeli dahil — hosted'da o da sunulan bir hizmet) baştan abonelik gerektiriyor. Self-host tarafı değişmedi: kendi makinende tüm stack'i koşmak hâlâ bedava (§17 open-core).
- **Fiyatlar:** `PLAN_PRICE_USD_CENTS` starter **$5** / pro **$15** / scale **$50** (eski 15/50/100). Kotalar (500K/3M/10M) aynı. Frontend'de hardcoded fiyat yok; hepsi `GET /billing/plans` üzerinden.
- **Backend söküm:** `start_trial` + `first_month_price_cents` silindi; `resolve_effective_status`'tan trial dalı, `ACTIVE_SUBSCRIPTION_STATUSES`'tan `TRIALING` çıktı (enum üyesi legacy satırlar için kaldı). `register` artık abonelik oluşturmuyor → abonesiz `POST /tasks` **402**. `subscribe` her dönemi tam fiyattan tahsil ediyor. Schema'lardan `discounted_price_cents`/`discount_eligible`/`first_discount_available`/`trial_end` kaldırıldı.
- **Migration `0009_remove_trial_and_discount`:** `users.first_discount_used` drop + kalan `status='trialing'` satırları → `inactive`. `trial_end` kolonu yerinde (nullable, kullanılmıyor). `0003`'ün `TRIAL_DURATION_DAYS` import'u Alembic history'yi kırmasın diye lokal literal `14`'e çevrildi.
- **Frontend:** trial/indirim UI mantığı (`PlanGrid` discount, billing sayfası trial banner, `QuotaMeter` trialing) kaldırıldı; abonesiz kullanıcının billing sayfası 404'ü "henüz abone değil" olarak ele alıp plan grid'i gösteriyor. Tüm "free/ücretsiz" pazarlama+legal dili nötrlendi ("Get started", "local model"); CTA'lar, `LandingMetrics`, docs/architect/marketing/legal (terms 4.1/4.2, security, privacy TR+EN, acceptable-use) güncellendi. Google Gemini'nin gerçek "free tier"ı (üçüncü taraf) ve `TRIALING` enum'u bilerek bırakıldı.
- **Doğrulandı:** backend `pytest` 524, `ruff` temiz; frontend `type-check`/`lint` (0 error)/`build` temiz.

### Backend v2 (Tur 8–13) — Tamamlandı (2026-07-12)
> Tasarım dokümanı (`docs/BACKEND-V2-DESIGN.md` + `.tr.md`) uygulandıktan sonra silindi; aşağısı özet, ayrıntı kod içindedir. Backend `pytest` 599 yeşil, `ruff` temiz, migration head `0011_model_prefs`.
- **Tur 8 — Durable execution engine:** Postgres checkpoint'ler (`task_runs`/`task_checkpoints`/`task_questions`), lease + heartbeat + reconciliation sweep (crash → resume/finalize, asla "running"da asılı kalmaz), usage upsert-max + billable split, `cancelled`/`awaiting_answer`/`completed_with_warnings` statüleri. `task_engine` durable step loop (ROUTE→EXECUTE→FINALIZE, replay-on-resume); `task_service` public API'yi koruyup delege eder.
- **Tur 9 — Distributed runtime:** Redis `EventBus` (pub/sub) + in-proc fallback (redis_url boşsa); `{v,seq,type,ts,...}` envelope; `agent_logs` seq-sıralı kaynak; WS `?after_seq` snapshot/cursor; HITL+cancel `maestro:ctrl:{id}` üzerinden cross-worker; `--workers N`.
- **Tur 10 — LLM Layer v2:** `AdapterCapabilities/ToolDef/StreamEvent`; `structured_call` (extract_json yerine); **native tool-call loop** (directive fallback) + OpenAI tool_calls parse/serialize; **AGENT_DELTA streaming** (synthesis `chat_stream`); TokenMeter v2 (paylaşılan `_TokenCounter`, estimation); **AdapterPool** (rol başına model, tek sayaç; `ctx.role_adapter`); **ToolProvider seam**; model routing (`model_overrides`, `users.model_preferences`, tier default'lar).
- **Tur 11 — Dynamic agent registry:** `resolve_domain_info(user_id, custom:{id})` — custom agent'lar gerçekten koşar (execution-time re-scan + `<agent_persona>` sandbox); orchestrator routing-catalog merge (routable custom agent'lara otomatik yönlendirme, cap 10); agent_configurations metadata + provenance (source/marketplace_item_id/security_scan) + Mongo index'ler.
- **Tur 12 — Observability:** kendi trace altyapımız (`utils/tracing.py`, contextvars nesting, best-effort buffer flush, `tracing_enabled` ile kapalı=sıfır overhead); `TracedAdapter` (TokenMeter altında, OTel `gen_ai.*` + cost); `trace_spans` koleksiyonu + TTL; trace + `/dashboard/costs` endpoint'leri (`MODEL_PRICING`).
- **Tur 13 — Quality & intelligence:** deterministic pre-review validators; structured `review_criteria` (weighted approval + `hard_fail`); partial-failure → `completed_with_warnings` + "Known gaps"; effort scaling (`RouteDecision.complexity`, `simple→1 üye + reviewer skip`); hierarchical token budget (`BudgetGuard` dalga + per-call, step-boundary quota re-check); subagent summaries + context compaction; `reviewer_fail_mode`.
- **Bilinçli sadeleştirmeler (kod yorumlarında işaretli):** OpenAI `tool_call_id` strict round-trip basitleştirildi; context compaction deterministik (LLM'siz); `output_format_sections_present` validator yanlış-pozitif riskiyle bağlanmadı. **Frontend touchpoint'leri** (AGENT_DELTA birleştirme, trace waterfall/cost UI, rol-başına model ayarları) tasarım kapsamı dışıydı — sıradaki frontend işi.

### Sonraki turlar
- **OG image'ın Docker imajında smoke testi** (standalone `next/og` WASM/font trace riski — `next dev` kanıt değil; patlarsa `outputFileTracingIncludes`).
- **Türkçe KVKK aydınlatma metni** (yapı `lib/legal/` locale'e hazır; şu an `/privacy`'de "coming soon" notu var). VERBİS kayıt eşiği kontrolü.
- **Gerçek ödeme processor'ü.** Mock provider'a asla gerçek kart girilmemeli (`payment_methods` PCI kapsamına girer). Processor gelince `BILLING_LIVE=true`.
- Purge öncesi hatırlatma e-postası (30 günlük süre dolmadan; şu an kullanıcı hiç login olmazsa uyarı almıyor). Doğrulama/reset/silme e-postaları eklendi; kalan tek transactional parça bu.
- Purge sweep'te tekrarlayan hata için log/alarm.
- Abonelik süre bitişi (cancelled → inactive) için scheduler (şu an lazy, request anında hesaplanıyor).
- Marketplace değerlendirmeleri/puanlama; dinamik agent'ların görev akışında kullanımı.
- GraphQL (gerekirse), long-polling fallback, i18n altyapısı.
- Refresh token rotation; WS/task_service için test kapsamı.
- Çoklu kart desteği; fatura geçmişi/makbuz.

---

## 17. Lisans ve İş Modeli (KARAR — n8n modeli)

> Karar tarihi: 2026-07-11. Maestro **fair-code / open-core hibrit** modelle yayınlanacak: kod GitHub'da herkese açık, self-host serbest ve ücretsiz; gelir hosted abonelik (starter/pro/scale) üzerinden.

### Model

- **Lisans:** n8n tarzı **Sustainable Use License** (source-available). Herkes okuyabilir, kendi kullanımı için çalıştırabilir ve değiştirebilir; **üçüncü taraflara ticari hizmet olarak satmak yasak** (rakip "Maestro Cloud" açılamaz). MIT/Apache verilmez.
- **Public repo:** Platformun tamamı — auth, agent orkestrasyon, BYOK, RAG, marketplace, `MockPaymentProvider`, Ollama ile tamamen lokal/ücretsiz akış. `docker-compose up` ile self-host tam çalışır (Ollama + Qwen3 + nomic-embed-text sayesinde LLM dahil sıfır maliyet — hosted instance'ın yapamadığı "lokal Ollama" senaryosu self-host'ta doğal avantaj).
- **Private kalan:** Gerçek ödeme processor adapter'ı (iyzico/Stripe vb.), cloud/tenant altyapısı, operasyonel deploy scriptleri. `PaymentProvider` adapter pattern'i bu ayrımı zaten destekliyor — public repo'da yalnızca mock durur, mevcut kod değişmez.
- **Gelir:** Hosted Maestro abonelikleri; ileride kurumsal özellikler (SSO, ekip workspace'leri, audit log) open-core olarak eklenebilir.

### Uygulama durumu (2026-07-11 — tamamlandı)

1. **LICENSE değiştirildi:** Apache-2.0 → Sustainable Use License v1.0. Repo bu tarihte zaten public'ti; Apache ile dağıtılmış eski sürümler o lisans altında kalır (LICENSE dosyasının sonunda not var). Pratik risk sıfıra yakın (henüz görünürlük yoktu) ama Apache döneminde fork alan biri o sürümleri Apache haklarıyla kullanabilir — geri alınamaz.
2. **CLA-lite:** `CONTRIBUTING.md` "Licensing of contributions" bölümü inbound=SUL + maintainer'a relicense hakkı + özgünlük beyanı içeriyor; PR açmak kabul sayılır. Dış katkı hacmi artarsa resmi CLA bot'u eklenir.
3. **Secret taraması yapıldı, temiz:** 117 commit'lik geçmişte gerçek `.env`/key/pem dosyası yok (yalnızca `.env.example` şablonları); bilinen API-key pattern'ları (OpenAI/Anthropic/AWS/GitHub/Google/Slack/private key) sıfır eşleşme; secret-benzeri atamalar yalnızca test fixture'ı (`test_config_guard.py`, sentetik değer).
4. **README:** lisans badge'i + License bölümü SUL'a çevrildi; "Self-Hosting vs Maestro Cloud" karşılaştırma bölümü eklendi.
