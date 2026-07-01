# Maestro Platform

Herkese açık, genel amaçlı bir **AI agent orkestrasyon platformu**. Kullanıcılar kendi
LLM API anahtarlarını bağlar (BYOK) ve çok katmanlı agent hiyerarşisi
(**Orchestrator → Main Agent → Subagent → Reviewer**) ile karmaşık görevleri
otomatikleştirir.

> Mimari, kurallar ve standartlar için tek kaynak: [`CLAUDE.md`](./CLAUDE.md).
> Ürün gereksinimleri: [`project-docs.md`](./project-docs.md).

## Mevcut Durum

Geliştirme **vertical-slice-first** ilerliyor (bkz. `CLAUDE.md` §16). Tur 1 uçtan uca
çalışan akış: **kayıt/giriş → BYOK anahtar ekleme → prompt ile görev → agent
hiyerarşisi (ücretsiz Qwen3/Ollama) → canlı sonuç**.

## Stack

| Katman | Teknoloji |
|---|---|
| Frontend | Next.js (App Router) + TypeScript + Tailwind + shadcn/ui + Zustand |
| Backend | FastAPI (async) + SQLAlchemy + Motor |
| İlişkisel DB | PostgreSQL |
| NoSQL | MongoDB |
| Vektör DB | Qdrant |
| Ücretsiz LLM | Qwen3 via Ollama (OpenAI-uyumlu) |
| Auth | Backend JWT |

## Ön Gereksinimler

- **Docker** (Postgres/Mongo/Qdrant için)
- **Python 3.11+**
- **Node.js 20+**
- **[Ollama](https://ollama.com)** (ücretsiz lokal model için)

## Kurulum

### 1. Altyapı (Docker)

```bash
cp .env.example .env          # değerleri doldur (JWT_SECRET, API_KEY_MASTER_KEY)
docker compose up -d          # postgres, mongo, qdrant
```

### 2. Ollama modelleri (ücretsiz katman)

```bash
ollama serve                  # ayrı bir terminalde
ollama pull qwen3
ollama pull nomic-embed-text
```

### 3. Backend

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate     |  macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head          # DB migration'ları
uvicorn app.main:app --reload # http://localhost:8000  (docs: /docs)
```

### 4. Frontend

```bash
cd frontend
npm install
npm run dev                   # http://localhost:3000
```

## Doğrulama

```bash
# Backend
cd backend && pytest && ruff check . && ruff format --check .

# Frontend
cd frontend && npm run lint && npm run type-check
```

## Güvenlik Notu

BYOK API anahtarları **AES-256-GCM** ile şifrelenir; düz metin saklanmaz, log'lanmaz ve
frontend'e asla döndürülmez. Secret'lar yalnızca `.env` üzerinden okunur ve `.env` asla
commit edilmez.
