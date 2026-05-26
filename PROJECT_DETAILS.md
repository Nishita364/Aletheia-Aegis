# Aletheia-Aegis — Project Details

## Overview

**Aletheia-Aegis** is an AI-powered fake news detection web platform that classifies news articles as **Real** or **Fake** in three languages: English, Hindi, and Telugu. It combines machine learning, a REST API backend, a React frontend, and a browser extension into a full-stack application.

---

## Project Structure

```
CITD project/
├── backend/                        # Python FastAPI backend
│   ├── main.py                     # App entry point, middleware, startup
│   ├── schemas.py                  # Pydantic request/response models
│   ├── conftest.py                 # Pytest fixtures
│   ├── pyproject.toml              # Python project config & dependencies
│   ├── .env                        # Environment variables (secrets)
│   ├── ml/
│   │   ├── train.py                # English model training script
│   │   ├── train_multilingual.py   # Hindi + Telugu model training script
│   │   ├── prediction_service.py   # ML inference wrapper
│   │   ├── language_router.py      # Language detection + pipeline routing
│   │   ├── data_loader.py          # CSV loader + English text preprocessor
│   │   ├── model_registry.py       # Hot-swap model registry
│   │   └── artifacts/              # Saved model files (.joblib + metadata)
│   ├── routers/
│   │   ├── submissions.py          # POST /api/v1/submissions
│   │   ├── history.py              # GET/DELETE /api/v1/history
│   │   └── admin.py                # Admin endpoints (analytics, retrain)
│   ├── db/
│   │   ├── repository.py           # Abstract repo interface + in-memory impl
│   │   └── mongo_repository.py     # MongoDB (Motor async) implementation
│   ├── services/
│   │   ├── fact_check_client.py    # Google Fact Check Explorer API client
│   │   ├── trust_rater.py          # Domain trust rating service
│   │   └── trust_domains.json      # Trusted / untrusted domain list
│   └── tests/                      # Pytest unit + property-based tests
│       ├── test_prediction_service.py
│       ├── test_language_router.py
│       ├── test_integration.py
│       ├── test_property_*.py      # Hypothesis property-based tests
│       └── smoke_test.py
├── frontend/                       # React + TypeScript frontend
│   └── src/
│       ├── App.tsx                 # Root component + routing
│       ├── types.ts                # Shared TypeScript interfaces
│       ├── pages/
│       │   ├── HomePage.tsx        # Article submission form
│       │   ├── ResultPage.tsx      # Prediction result display
│       │   ├── HistoryPage.tsx     # Submission history list
│       │   ├── AdminDashboard.tsx  # Admin panel + analytics
│       │   └── LoginPage.tsx       # Admin login page
│       ├── components/
│       │   ├── SubmissionForm.tsx  # Text / URL input form
│       │   ├── PredictionCard.tsx  # Verdict, confidence, fact-checks
│       │   ├── HighlightedText.tsx # Article text with phrase highlights
│       │   ├── HistoryList.tsx     # Paginated history entries
│       │   ├── AnalyticsWidgets.tsx# Stats cards (total, Real%, Fake%, accuracy)
│       │   ├── AppLayout.tsx       # Header, nav, dark mode toggle
│       │   ├── AuthGuard.tsx       # Route protection for admin
│       │   └── ThemeToggle.tsx     # Dark / light mode switch
│       └── context/
│           └── AuthContext.tsx     # JWT auth state (login / logout)
├── extension/                      # Browser extension
│   ├── manifest.json               # Chrome MV3 manifest
│   ├── manifest.firefox.json       # Firefox MV2 manifest
│   ├── content.js                  # Content script (page text extraction)
│   ├── background.js               # Service worker
│   └── popup/                      # Extension popup UI
├── Hindi_F&R_News/                 # Hindi training dataset
│   ├── Hindi_fake_news/            # 10,293 fake news articles (.txt)
│   └── Hindi_real_news/            # 10,300 real news articles (.txt)
├── Telugu_F&R_News/                # Telugu training dataset
│   ├── Telugu_fake_news/           # 10,000 fake news articles (.txt)
│   └── Telugu_real_news/           # 10,001 real news articles (.txt)
└── archive/                        # English training dataset
    ├── Fake.csv                    # ~23,000 fake English articles
    └── True.csv                    # ~21,000 real English articles
```

---

## Tech Stack

### Backend

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Web framework | **FastAPI** (Python 3.12) | REST API, async request handling, OpenAPI docs |
| ML library | **scikit-learn** | TF-IDF vectorizer, Logistic Regression, Pipeline, FeatureUnion |
| Model serialisation | **joblib** | Save and load trained model artifacts |
| Language detection | **langdetect** | Detect English / Hindi / Telugu from input text |
| Async DB driver | **Motor** (async MongoDB) | Persist submission history to MongoDB Atlas |
| Sync DB probe | **PyMongo** | Startup connection health check |
| HTTP client | **httpx** | Fetch articles from URLs, call external APIs |
| HTML extraction | **regex** (stdlib) | Extract article text from fetched HTML pages |
| Authentication | **python-jose** (JWT HS256) | Admin route protection |
| Rate limiting | **slowapi** | 30 requests/minute per IP address |
| Environment config | **python-dotenv** | Load `.env` variables at startup |
| Data validation | **Pydantic v2** | Request/response schema validation and serialisation |
| ASGI server | **Uvicorn** | Run the FastAPI application |
| Text normalisation | **unicodedata** (stdlib) | NFC normalisation for Indic scripts |
| Property testing | **Hypothesis** | Property-based tests for correctness properties |

### ML Models

| Language | Training Data | Features | Algorithm | Accuracy |
|----------|-------------|----------|-----------|---------|
| English | 23,481 articles (Fake.csv + True.csv) | Word TF-IDF (1,2-grams) | Logistic Regression | ~98.8% |
| Hindi | 10,293 fake + 10,300 real `.txt` files + snippets (~78,000 samples) | FeatureUnion: word TF-IDF(1,2) + char_wb TF-IDF(3,5) | Logistic Regression | 99.39% |
| Telugu | 10,000 fake + 10,001 real `.txt` files + snippets (~65,000 samples) | FeatureUnion: word TF-IDF(1,2) + char_wb TF-IDF(3,5) | Logistic Regression | 99.91% |

#### Why This Approach for Hindi and Telugu

- **Word n-grams (1,2)** capture topic and vocabulary patterns — effective even on short text snippets
- **Character n-grams (3,5)** capture morphological patterns specific to Indic scripts where word boundaries are less reliable
- **Snippet augmentation** — each full article generates 3 additional training samples (first 3, 5, and 8 sentences) so the model learns to classify partial text, not just full articles
- **No translation** — each language uses its own native model trained directly on native-language data

### Frontend

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Framework | **React 18** + **TypeScript** | UI components and state management |
| Build tool | **Vite** | Fast development server and production build |
| Routing | **React Router v6** | Client-side navigation |
| Styling | **Tailwind CSS** | Utility-first responsive styling |
| HTTP | Native `fetch` API | API calls to the backend |
| Auth state | React Context + `localStorage` | JWT token storage and auth state |
| Theme | CSS class toggling + `localStorage` | Dark/light mode persistence |

### Browser Extension

| Component | Technology |
|-----------|-----------|
| Chrome | Manifest V3, content script + background service worker |
| Firefox | Manifest V2 compatible build |
| Popup UI | Vanilla HTML / CSS / JavaScript |

### External Services

| Service | Purpose |
|---------|---------|
| **Google Fact Check Explorer API** | Cross-reference article claims against independently verified fact-checks |
| **MongoDB Atlas** | Cloud-hosted database for persistent submission history |

---

## How It Works — End to End

```
User pastes article text  OR  enters a URL
              ↓
    SubmissionForm (React frontend)
              ↓
    POST /api/v1/submissions  (FastAPI)
              ↓
    [If URL] → httpx fetches page → regex extracts article text
              ↓
    langdetect → detect language: en / hi / te
              ↓
    LanguageRouter → select native model pipeline
              ↓
    PredictionService.predict()
      ├── NFC normalise (Indic) or full preprocess (English)
      ├── TF-IDF transform (word + char features)
      ├── LogisticRegression.predict_proba()
      └── extract top suspicious phrases
              ↓
    TrustRater → rate source domain (High / Medium / Low / Unknown)
              ↓
    FactCheckClient → query Google Fact Check Explorer API
              ↓
    Save HistoryRecord to MongoDB (or in-memory fallback)
              ↓
    Return PredictionResponse (JSON)
              ↓
    ResultPage (React) → display:
      - Verdict badge (Real ✅ / Fake ❌)
      - Confidence bar
      - Plain-language explanation
      - Suspicious phrases highlighted in article text
      - Fact-check results
      - Source trust rating
```

---

## API Endpoints

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/api/v1/submissions` | Public | Submit article text or URL for analysis |
| GET | `/api/v1/history` | Public | List 50 most recent submissions |
| GET | `/api/v1/history/{id}` | Public | Get a single submission by ID |
| DELETE | `/api/v1/history/{id}` | Public | Delete a submission record |
| POST | `/api/v1/login` | Public | Admin login, returns JWT token |
| GET | `/api/v1/admin/analytics` | JWT | Submission stats + model accuracy |
| POST | `/api/v1/admin/retrain` | JWT | Trigger background model retrain |
| GET | `/api/v1/admin/retrain/{job_id}` | JWT | Poll retrain job status |
| POST | `/api/v1/admin/dataset` | JWT | Upload CSV training dataset |
| PUT | `/api/v1/admin/trust-domains` | JWT | Update trusted domain list |
| GET | `/api/v1/health` | Public | Liveness probe |

---

## Key Features

- **Multilingual detection** — English, Hindi, Telugu with separate native models (no translation)
- **URL support** — paste a URL and the backend fetches and extracts the article text automatically
- **Fact-check integration** — cross-references claims with Google Fact Check Explorer
- **Source trust rating** — rates the article's source domain as High / Medium / Low / Unknown
- **Submission history** — all checks saved and browsable with delete support
- **Admin dashboard** — analytics widgets, CSV dataset upload, model retrain trigger
- **JWT authentication** — admin-only routes protected with HS256 JWT tokens
- **Dark / light mode** — persisted in localStorage across sessions
- **Browser extension** — Chrome MV3 + Firefox MV2 for checking articles directly in the browser
- **Rate limiting** — 30 requests/minute per IP to prevent abuse
- **Responsive UI** — works on mobile and desktop
- **Low-confidence warning** — alerts users when the model confidence is below 70%
- **Property-based testing** — Hypothesis tests verify correctness properties of the ML pipeline

---

## Running the Project

### Start the Backend (port 8000)

```bash
cd "CITD project"
backend\.venv\Scripts\uvicorn.exe backend.main:app --host 0.0.0.0 --port 8000 --reload
```

### Start the Frontend (port 5173)

```bash
cd "CITD project\frontend"
npm run dev
```

### Retrain Hindi + Telugu Models

```bash
cd "CITD project"
backend\.venv\Scripts\python.exe -m backend.ml.train_multilingual
```

### Retrain English Model

```bash
cd "CITD project"
backend\.venv\Scripts\python.exe -m backend.ml.train
```

### Run Backend Tests

```bash
cd "CITD project\backend"
.venv\Scripts\pytest tests/ -v
```

---

## Environment Variables (`backend/.env`)

| Variable | Example Value | Purpose |
|----------|--------------|---------|
| `MONGODB_URI` | `mongodb+srv://user:pass@cluster.mongodb.net/` | MongoDB Atlas connection string |
| `MONGODB_DB_NAME` | `fake_news_detector` | Database name |
| `JWT_SECRET` | `your-secret-key` | Secret for signing JWT tokens |
| `JWT_ALGORITHM` | `HS256` | JWT signing algorithm |
| `JWT_EXPIRATION_HOURS` | `24` | Token expiry duration |
| `ADMIN_USERNAME` | `admin` | Admin login username |
| `ADMIN_PASSWORD` | `admin123` | Admin login password |
| `FACT_CHECK_API_KEY` | `AIza...` | Google Fact Check Explorer API key |
| `RATE_LIMIT_PER_MINUTE` | `30` | Max requests per IP per minute |

---

## Model Artifacts

All trained model files are stored in `backend/ml/artifacts/`:

| File | Description |
|------|-------------|
| `tfidf_vectorizer.joblib` | English TF-IDF vectorizer |
| `logistic_regression.joblib` | English Logistic Regression model |
| `model_metadata.json` | English model training metadata |
| `hi_tfidf_vectorizer.joblib` | Hindi full sklearn Pipeline (word+char TF-IDF + LR) |
| `hi_logistic_regression.joblib` | Hindi LR classifier (extracted from pipeline) |
| `hi_model_metadata.json` | Hindi model training metadata |
| `te_tfidf_vectorizer.joblib` | Telugu full sklearn Pipeline (word+char TF-IDF + LR) |
| `te_logistic_regression.joblib` | Telugu LR classifier (extracted from pipeline) |
| `te_model_metadata.json` | Telugu model training metadata |

---

## Admin Access

- **URL:** `http://localhost:5173/login`
- **Username:** `admin`
- **Password:** `admin123`

After login, the Admin link appears in the navigation bar giving access to analytics, dataset upload, and model retraining.

---

## Notes

- The Hindi and Telugu models are trained on actual news articles (BBC-style fact-checks and real news). They work best with full article text (at least 5 sentences). Very short snippets may not have enough vocabulary signal.
- MongoDB Atlas requires your current IP address to be whitelisted in the Atlas Network Access settings. If the connection fails, the app automatically falls back to an in-memory store (history will not persist across restarts).
- The Google Fact Check API key is already configured in `backend/.env`.


---

## Accessing the Project from a Phone

`localhost` only works on the machine running the server. Your phone cannot reach `localhost` because it refers to "this device only." To access from a phone, both devices must be on the **same Wi-Fi network** and you use the laptop's actual IP address.

### What Was Changed

**1. Found the laptop's Wi-Fi IP**
Used PowerShell's `Get-NetIPAddress` to find the laptop's IP on the local network → `192.168.29.99`

**2. Updated `frontend/vite.config.ts`**
Added `host: true` so Vite binds to all network interfaces (not just localhost):
```ts
server: {
  host: true,   // binds to 0.0.0.0 — all network interfaces
  port: 5173,
}
```

**3. Updated `frontend/.env`**
Changed the API base URL from `localhost` to the real laptop IP:
```
VITE_API_BASE_URL=http://192.168.29.99:8000
```
Without this, the frontend loads on the phone but all API calls go to the phone's own `localhost` instead of the laptop.

**4. Updated `backend/main.py` CORS**
Added the network IP to the allowed origins list so the browser doesn't block API responses:
```python
"http://192.168.29.99:5173"
```

**5. Backend already network-accessible**
The backend was already started with `--host 0.0.0.0` so no change was needed there.

### How to Access from Your Phone

Make sure your phone is on the **same Wi-Fi network** as your laptop, then open in your phone's browser:

| Service | URL |
|---------|-----|
| Frontend | `http://192.168.29.99:5173` |
| Backend API | `http://192.168.29.99:8000` |

> **Note:** The IP address (`192.168.29.99`) may change each time you reconnect to Wi-Fi. If it stops working, check the Network URL shown in the Vite terminal output when you start the frontend — it always shows the current IP.
