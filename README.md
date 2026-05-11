# EduCheck — AI-Powered Academic Plagiarism Detection Platform

<div align="center">

![EduCheck](https://img.shields.io/badge/EduCheck-v2.0-1F4E79?style=for-the-badge)
![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688?style=for-the-badge&logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-18-61DAFB?style=for-the-badge&logo=react&logoColor=black)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-pgvector-4169E1?style=for-the-badge&logo=postgresql&logoColor=white)
![Supabase](https://img.shields.io/badge/Supabase-Auth-3ECF8E?style=for-the-badge&logo=supabase&logoColor=white)

**A production-ready, open-source alternative to Turnitin.**  
Detects plagiarism using BERT semantic embeddings, BM25 retrieval, k-gram fingerprinting,  
and real-time academic source checking against arXiv, OpenAlex, and GitHub.

[Features](#features) · [Architecture](#architecture) · [Quick Start](#quick-start) · [API Reference](#api-reference) · [Deployment](#deployment)

</div>

---

## Table of Contents

- [Features](#features)
- [Architecture](#architecture)
- [Project Structure](#project-structure)
- [Quick Start](#quick-start)
- [Environment Variables](#environment-variables)
- [API Reference](#api-reference)
- [The 5-Stage Hybrid Pipeline](#the-5-stage-hybrid-pipeline)
- [Deployment](#deployment)
- [Technology Stack](#technology-stack)

---

## Features

### For Teachers
- 📋 **Assignment Management** — Create, update, and delete assignments with deadline scheduling
- ⏰ **Automated Deadline Triggers** — APScheduler fires plagiarism checks exactly at deadline; no manual action needed
- 🔍 **Submission Inspector** — View every student's plagiarism score with matched sentence pairs
- 👥 **Student Pair Analysis** — See which student pairs share suspicious sentences side by side
- 📊 **Analytics Dashboard** — Bar charts showing risk distribution across the class
- 🎓 **Academic Check on Submissions** — Run live academic source check on any stored submission

### For Students
- 📝 **Flexible Submission** — Type text directly or upload PDF, DOCX, or TXT files
- ⏳ **Pending State** — Results hidden until deadline; no early score disclosure
- 📈 **Score Gauge** — Animated SVG gauge with colour-coded risk classification
- 🎓 **Academic Check** — Check own text against arXiv, OpenAlex, and GitHub before submitting
- 📄 **File Upload Academic Check** — Upload a PDF/DOCX/TXT for direct academic plagiarism checking

### AI Detection Engine
- 🤖 **BERT Semantic Embeddings** — Detects paraphrased plagiarism that keyword tools miss (~87% accuracy on paraphrased text vs ~0% for keyword matching)
- 🔎 **BM25 Pre-filtering** — Narrows thousands of candidate sentences to top-15 before expensive BERT comparison
- 🔏 **Fingerprinting** — k=5 word shingling with MD5 hashing and Jaccard similarity for exact-match detection
- 🌐 **Multi-Source Retrieval** — arXiv + OpenAlex + GitHub queried simultaneously via `asyncio.gather()`
- ⚡ **Vectorised Batch Processing** — Global N×N similarity matrix computed in one BLAS-level numpy call

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    React 18 SPA (Vite)                      │
│  Teacher Dashboard │ Student Dashboard │ Academic Check     │
└─────────────────────────┬───────────────────────────────────┘
                          │ HTTPS / JWT
┌─────────────────────────▼───────────────────────────────────┐
│                  FastAPI Backend (Python)                    │
│  Auth (Supabase JWT) │ RBAC │ APScheduler │ 20+ endpoints  │
└──────┬──────────────────────────────────┬────────────────────┘
       │                                  │
┌──────▼──────────┐              ┌────────▼──────────────────┐
│  PostgreSQL     │              │   5-Stage AI Pipeline     │
│  + pgvector     │              │                           │
│                 │              │  1. Preprocessing         │
│  users          │              │  2. BM25 Retrieval        │
│  assignments    │              │  3. Fingerprinting        │
│  submissions    │              │  4. BERT Semantic         │
│  sentences      │              │  5. Hybrid Scoring        │
│  matches        │              │                           │
└─────────────────┘              │  Sources: arXiv           │
                                 │           OpenAlex        │
                                 │           GitHub          │
                                 └───────────────────────────┘
```

### Assignment Lifecycle

```
  OPEN ──────────────────► CLOSED ──────────────► CHECKED
  (Submissions accepted)   (Deadline fired)       (Scores visible)
       ▲                        │
       └── Teacher extends ◄────┘
           deadline
```

---

## Project Structure

```
educheck/
├── backend/
│   ├── app/
│   │   ├── main.py                          # FastAPI app, all endpoints, APScheduler
│   │   ├── models.py                        # SQLAlchemy ORM models (5 tables)
│   │   ├── schemas.py                       # Pydantic request/response schemas
│   │   ├── database.py                      # SQLAlchemy engine + session
│   │   ├── config.py                        # Environment variable loading
│   │   ├── auth/
│   │   │   ├── router.py                    # /api/auth/signup, /api/auth/login
│   │   │   └── dependencies.py             # JWT decode, get_current_user, require_teacher/student
│   │   ├── services/
│   │   │   ├── embedding_service.py         # BERT singleton + batch encoding
│   │   │   ├── plagiarism_service.py        # Intra-assignment vectorised batch checker
│   │   │   └── pipeline/                   # Academic Check 5-stage pipeline
│   │   │       ├── __init__.py
│   │   │       ├── academic_service.py      # Orchestrator: fetch → BM25 → fingerprint → BERT → hybrid
│   │   │       ├── preprocessing.py         # Sentence splitting + text normalisation
│   │   │       ├── retrieval.py             # BM25Okapi index + top-K retrieval
│   │   │       ├── fingerprinting.py        # k-gram shingling + Jaccard similarity
│   │   │       ├── semantic.py              # BERT encoding + cosine similarity
│   │   │       ├── utils.py                 # Keyword extraction + text cleaning helpers
│   │   │       ├── file_extractor.py        # PDF / DOCX / TXT server-side extraction
│   │   │       └── api_routes.py            # Academic check FastAPI router
│   │   └── utils/
│   │       ├── text_utils.py                # split_sentences()
│   │       └── similarity_utils.py          # cosine similarity helpers
│   ├── requirements.txt
│   └── .ENV                                 # Environment variables (never commit)
│
├── frontend/
│   ├── src/
│   │   ├── App.jsx                          # Root component, auth state machine, all dashboards
│   │   ├── AcademicCheckPanel.jsx           # Academic Check UI (text + file upload)
│   │   ├── AcademicHighlighter.js           # Sentence highlighting utilities
│   │   ├── auth.js                          # Supabase auth helpers
│   │   ├── supabaseClient.js                # Supabase client initialisation
│   │   └── main.jsx                         # React entry point
│   ├── public/
│   │   └── _redirects                       # Netlify / static host SPA routing
│   ├── package.json
│   └── vite.config.js
│
├── docker-compose.yml                       # Optional: full stack containerisation
└── README.md
```

---

## Quick Start

### Prerequisites

- Python 3.10+
- Node.js 18+
- PostgreSQL 14+ with [pgvector](https://github.com/pgvector/pgvector) extension
- A [Supabase](https://supabase.com) project (free tier works)

### 1. Clone the Repository

```bash
git clone https://github.com/yourusername/educheck.git
cd educheck
```

### 2. Backend Setup

```bash
cd backend

# Create and activate virtual environment
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Download NLTK data (first run only)
python -c "import nltk; nltk.download('punkt'); nltk.download('stopwords')"

# Copy and fill in environment variables
cp app/.ENV.example app/.ENV
# Edit app/.ENV with your Supabase credentials and database URL
```

### 3. Database Setup

```sql
-- In your PostgreSQL instance or Supabase SQL editor:
CREATE EXTENSION IF NOT EXISTS vector;
```

The tables are created automatically by SQLAlchemy on first run.

### 4. Start the Backend

```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

API available at `http://localhost:8000`  
Interactive docs at `http://localhost:8000/api/docs`

### 5. Frontend Setup

```bash
cd frontend
npm install

# Copy environment file
cp env.example .env.local
# Edit .env.local with your Supabase URL and anon key
```

### 6. Start the Frontend

```bash
npm run dev
```

Frontend available at `http://localhost:5173`

### 7. (Optional) GitHub Token for Higher Rate Limits

```bash
# In backend app/.ENV:
GITHUB_TOKEN=ghp_your_token_here
```

Without a token: 60 API requests/hour. With token: 5,000/hour.

---

## Environment Variables

### Backend — `backend/app/.ENV`

```env
# Database
DATABASE_URL=postgresql://user:password@host:5432/dbname

# Supabase
SUPABASE_URL=https://yourproject.supabase.co
SUPABASE_ANON_KEY=your-anon-key
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
SUPABASE_JWT_SECRET=your-jwt-secret

# Optional — GitHub API (increases rate limit from 60 to 5000 req/hr)
GITHUB_TOKEN=ghp_your_github_token
```

### Frontend — `frontend/.env.local`

```env
VITE_SUPABASE_URL=https://yourproject.supabase.co
VITE_SUPABASE_ANON_KEY=your-anon-key

# Only needed for separate frontend/backend deployment (e.g. Vercel + Railway)
VITE_API_URL=https://your-backend.railway.app
```

---

## API Reference

All endpoints are prefixed `/api`. Protected endpoints require:
```
Authorization: Bearer <supabase_jwt_token>
```

### Authentication

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `POST` | `/api/auth/signup` | Public | Register with email + password + role |
| `POST` | `/api/auth/login` | Public | Login — returns JWT access token |

### Assignments

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `GET` | `/api/assignments` | Any | List all assignments with status and deadline |
| `POST` | `/api/assignments` | Teacher | Create assignment; schedules deadline job |
| `PATCH` | `/api/assignments/{id}` | Teacher | Update title/deadline; reschedules APScheduler job |
| `DELETE` | `/api/assignments/{id}` | Teacher | Delete assignment and all related data |

### Submissions

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `POST` | `/api/submissions` | Student | Submit text; stores BERT embeddings |
| `GET` | `/api/submissions` | Teacher | List all submissions with scores |
| `GET` | `/api/submissions/my` | Student | Own submissions; `null` score = pending |
| `GET` | `/api/submissions/{id}` | Teacher | Full detail with matched sentence pairs |

### Analytics

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `GET` | `/api/assignments/{id}/similarity-pairs` | Teacher | Student pair collusion analysis |

### Academic Check

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `POST` | `/api/academic-check` | Any | Check pasted text against arXiv + OpenAlex + GitHub |
| `POST` | `/api/academic-check/file` | Any | Check uploaded PDF/DOCX/TXT (multipart/form-data) |
| `POST` | `/api/submissions/{id}/academic-check` | Teacher | Academic check on a stored submission |

### Request / Response Examples

**POST `/api/academic-check`**
```json
// Request
{
  "text": "Transformer models have become the dominant architecture in NLP...",
  "threshold": 0.65
}

// Response
{
  "plagiarism_percentage": 34.5,
  "flagged": false,
  "sources_checked": 42,
  "sentences_checked": 8,
  "elapsed_seconds": 11.2,
  "matches": [
    {
      "input_sentence": "Transformer models have become the dominant architecture in NLP.",
      "matched_sentence": "Transformer architectures dominate modern natural language processing.",
      "source": "arXiv",
      "similarity": 0.81,
      "similarity_pct": 81.0,
      "semantic_score": 87.2,
      "exact_score": 18.4,
      "title": "Attention Is All You Need",
      "url": "https://arxiv.org/abs/1706.03762"
    }
  ]
}
```

**POST `/api/academic-check/file`**
```bash
curl -X POST http://localhost:8000/api/academic-check/file \
  -H "Authorization: Bearer <token>" \
  -F "file=@essay.pdf" \
  -F "threshold=0.65"
```

---

## The 5-Stage Hybrid Pipeline

The Academic Check module uses a production-grade NLP pipeline:

```
Input Text / File
      │
      ▼
┌─────────────────────────────────────┐
│  STAGE 1 — Preprocessing            │
│  • Lowercase + punctuation removal  │
│  • NLTK sentence splitting          │
│  • Top-8 keyword extraction         │
└──────────────────┬──────────────────┘
                   │ keywords
                   ▼
┌─────────────────────────────────────┐
│  STAGE 2 — Parallel Retrieval       │
│  asyncio.gather() fires all at once │
│  • arXiv API  (research papers)     │
│  • OpenAlex API (200M+ works)       │
│  • GitHub API  (repos + READMEs)    │
│  → deduplicated by title MD5        │
└──────────────────┬──────────────────┘
                   │ reference corpus
                   ▼
┌─────────────────────────────────────┐
│  STAGE 3 — BM25 Pre-filtering       │
│  • BM25Okapi index over all         │
│    reference sentences              │
│  • Top-15 candidates per            │
│    submission sentence              │
└──────────────────┬──────────────────┘
                   │ top-K candidates
                   ▼
┌─────────────────────────────────────┐
│  STAGE 4a — Fingerprinting          │
│  • k=5 word shingles, MD5 hashed   │
│  • Jaccard similarity score         │
│  (catches verbatim copying)         │
└──────────────────┬──────────────────┘
                   │
                   ▼
┌─────────────────────────────────────┐
│  STAGE 4b — BERT Semantic           │
│  • all-MiniLM-L6-v2 (384-dim)      │
│  • Batched encoding                 │
│  • Cosine similarity (dot product   │
│    of L2-normalised vectors)        │
└──────────────────┬──────────────────┘
                   │ both scores
                   ▼
┌─────────────────────────────────────┐
│  STAGE 5 — Hybrid Scoring           │
│                                     │
│  hybrid = 0.60 × semantic           │
│         + 0.40 × fingerprint        │
│                                     │
│  flag if hybrid ≥ τ (default 0.65) │
│  P = flagged / total × 100          │
└─────────────────────────────────────┘
```

### Intra-Assignment Detection

For student-vs-student comparison, a vectorised global matrix approach is used:

```
All student embeddings stacked → E ∈ ℝ^(N×384)
Global similarity matrix:      SIM = E_norm · E_normᵀ   ← single BLAS call
Per student:                   slice rows, zero same-student columns, argmax
Hybrid score:                  0.70 × BERT + 0.20 × TF-IDF + 0.10 × Jaccard
```

### Risk Classification

| Score | Level | Colour | Action |
|-------|-------|--------|--------|
| 0–24% | Original | 🟢 Green | No action |
| 25–49% | Low Risk | 🟡 Amber | Teacher review |
| 50–74% | Suspicious | 🟠 Orange | Match inspection |
| 75–100% | High Risk | 🔴 Red | Academic integrity review |

---

## Deployment

### Option A — Railway (Backend) + Vercel (Frontend) — Recommended

**Backend on Railway:**

1. Push your repo to GitHub
2. Go to [railway.app](https://railway.app) → New Project → Deploy from GitHub
3. Set root directory to `backend/`
4. Add environment variables (all values from your `.ENV` file)
5. Railway auto-detects `requirements.txt` and starts with:
   ```
   uvicorn app.main:app --host 0.0.0.0 --port $PORT
   ```
6. Copy your Railway URL (e.g. `https://educheck.railway.app`)

**Frontend on Vercel:**

1. Go to [vercel.com](https://vercel.com) → New Project → Import from GitHub
2. Set root directory to `frontend/`
3. Add environment variables:
   ```
   VITE_SUPABASE_URL=https://yourproject.supabase.co
   VITE_SUPABASE_ANON_KEY=your-anon-key
   VITE_API_URL=https://educheck.railway.app
   ```
4. Deploy — Vercel auto-detects Vite

**Update CORS in `main.py`:**
```python
allow_origins=[
    "http://localhost:5173",
    "https://your-site.vercel.app",   # add your Vercel URL
]
```

---

### Option B — Docker Compose (Self-hosted)

```bash
# From project root
docker-compose up --build
```

Services:
- `backend` — FastAPI on port 8000
- `frontend` — Nginx serving React build on port 80
- `db` — PostgreSQL 16 with pgvector on port 5432

---

### Option C — Netlify (Frontend Only)

1. Build the frontend: `cd frontend && npm run build`
2. Ensure `frontend/public/_redirects` contains:
   ```
   /*    /index.html   200
   ```
3. Drag and drop the `dist/` folder at [netlify.com/drop](https://netlify.com/drop)
4. Set environment variables in Netlify dashboard → Site settings → Environment variables

> ⚠️ The FastAPI backend **cannot** run on Netlify. Deploy it separately on Railway or Render.

---

## Technology Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| Frontend | React 18 + Vite | Single-page application |
| UI Charts | Recharts | Analytics bar charts |
| File Parsing (client) | PDF.js, Mammoth.js | Client-side PDF/DOCX extraction for submissions |
| Backend | FastAPI (Python) | REST API, dependency injection, CORS |
| Auth | Supabase | JWT issuance, email + Google OAuth |
| Database | PostgreSQL 14+ | Relational data storage |
| Vector Search | pgvector | 384-dim embedding storage + cosine similarity |
| ORM | SQLAlchemy | Database models and queries |
| Scheduler | APScheduler | Deadline-triggered plagiarism jobs |
| BERT Model | all-MiniLM-L6-v2 | 384-dim sentence embeddings |
| BM25 | rank-bm25 | Candidate pre-filtering |
| HTTP Client | aiohttp | Async multi-source API fetching |
| PDF Extraction | pdfplumber + PyMuPDF | Server-side PDF text extraction |
| DOCX Extraction | python-docx | Server-side Word document extraction |
| Vector Indexing | FAISS (optional) | Approximate nearest-neighbour search |
| Deployment | Railway + Vercel | Backend + frontend cloud hosting |

---

## Key Design Decisions

**Why sentence-level comparison?**  
Document-level comparison misses mosaic plagiarism (interspersed copied sentences). Sentence granularity localises copied content precisely and enables per-sentence evidence display.

**Why BM25 before BERT?**  
BERT encoding is expensive. BM25 reduces the reference corpus from potentially thousands of sentences to 15 candidates per query sentence, making the pipeline 50–100× faster with negligible accuracy loss.

**Why hybrid scoring?**  
Semantic-only models over-generalise (high false positives on topically similar but independently written text). Fingerprinting anchors the score on lexical evidence. The weighted combination (60/40) balances precision and recall.

**Why vectorised global matrix?**  
Sequential per-student comparison requires O(k) database round-trips and O(k·N²·d) Python loops. The global matrix approach uses 2 database calls and O(N²) at BLAS speed regardless of student count.

**Why APScheduler DateTrigger?**  
Results must not be visible before the deadline (academic fairness). DateTrigger fires exactly once at the deadline timestamp. Server restart resilience ensures no deadline is ever missed.

---

## License

MIT License — see [LICENSE](LICENSE) for details.

---

## Author

**Rohan Deb**  
Student ID: 23051452  
Applications Development Laboratory  
Kalinga Institute of Industrial Technology (KIIT), Deemed University  
Supervisor: Jyoti Prakash Meher

---

<div align="center">
Built with ❤️ at KIIT University · EduCheck v2.0
</div>
