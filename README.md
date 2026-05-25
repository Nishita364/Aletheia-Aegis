# Aletheia-Aegis

**AI-Powered Fake News Detection Platform — Detecting Misinformation with AI**

Aletheia-Aegis is a full-stack web application that uses machine learning to classify news articles as **Real** or **Fake**. It supports English, Telugu, and Hindi, provides fact-check cross-referencing via the Google Fact Check Explorer API, and includes a browser extension for on-page analysis.

---

## Features

- **ML-powered classification** — TF-IDF + Logistic Regression trained on 44,000+ articles (98.8% accuracy)
- **Multilingual support** — English (direct), Telugu and Hindi (via translation)
- **URL analysis** — paste a news article URL and the system fetches and analyses it
- **Fact-check integration** — cross-references claims with Google Fact Check Explorer
- **Source trust rating** — rates the credibility of the news source domain
- **Submission history** — persistent history stored in MongoDB
- **Admin dashboard** — upload new training data, retrain the model, view analytics
- **Browser extension** — analyse any webpage directly from your browser (Chrome/Firefox)
- **Dark/light mode** — persists across sessions

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.12, FastAPI, scikit-learn, motor (MongoDB) |
| Frontend | React 18, TypeScript, Vite, Tailwind CSS |
| Database | MongoDB Atlas |
| ML | TF-IDF Vectorizer + Logistic Regression |
| Translation | deep-translator (Google Translate) |
| Extension | Manifest V3 (Chrome), Manifest V2 (Firefox) |

---

## Project Structure

```
CITD project/
├── backend/              # FastAPI backend + ML pipeline
│   ├── ml/               # Data loader, training, prediction service
│   ├── routers/          # API route handlers
│   ├── services/         # Trust rater, fact-check client, translator
│   ├── db/               # MongoDB repository
│   ├── tests/            # Unit, integration, and property-based tests
│   └── main.py           # App entry point
├── frontend/             # React + Vite frontend
│   └── src/
│       ├── components/   # UI components
│       └── pages/        # Route pages
├── extension/            # Browser extension (MV3 + MV2)
├── archive/              # Training data (Fake.csv, True.csv)
└── README.md
```

---

## Setup & Running Locally

### Prerequisites

- Python 3.11+
- Node.js 18+
- MongoDB Atlas account (or local MongoDB)

### 1. Backend

```bash
# Create and activate virtual environment
cd backend
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Linux/Mac

# Install dependencies
pip install -e ".[dev]"

# Copy and fill in environment variables
copy .env.example .env
# Edit .env with your MongoDB URI, API keys, etc.

# Train the ML model (first time only)
python -m backend.ml.train

# Start the backend
uvicorn backend.main:app --reload --port 8000
```

### 2. Frontend

```bash
cd frontend

# Install dependencies
npm install

# Copy and fill in environment variables
copy .env.example .env
# Set VITE_API_BASE_URL=http://localhost:8000

# Start the frontend
npm run dev
```

The app will be available at **http://localhost:5173**

---

## Environment Variables

### Backend (`backend/.env`)

| Variable | Description | Default |
|----------|-------------|---------|
| `MONGODB_URI` | MongoDB Atlas connection string | (in-memory fallback) |
| `MONGODB_DB_NAME` | Database name | `fake_news_detector` |
| `JWT_SECRET` | Secret key for JWT tokens | `change-me-in-production` |
| `ADMIN_USERNAME` | Admin login username | `admin` |
| `ADMIN_PASSWORD` | Admin login password | `admin123` |
| `FACT_CHECK_API_KEY` | Google Fact Check Explorer API key | (disabled if empty) |

### Frontend (`frontend/.env`)

| Variable | Description | Default |
|----------|-------------|---------|
| `VITE_API_BASE_URL` | Backend API URL | `http://localhost:8000` |

---

## Admin Dashboard

Access the admin dashboard at **http://localhost:5173/admin**

Default credentials:
- Username: `admin`
- Password: `admin123`

Features:
- Upload new CSV training data
- Trigger model retraining
- View submission analytics
- Update trust domain list

---

## API Documentation

Interactive API docs available at **http://localhost:8000/docs** when the backend is running.

Key endpoints:

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/submissions` | Analyse a news article (text or URL) |
| `GET` | `/api/v1/history` | Get recent submission history |
| `GET` | `/api/v1/health` | Health check |
| `POST` | `/api/v1/login` | Admin login |
| `GET` | `/api/v1/admin/analytics` | Submission statistics |
| `POST` | `/api/v1/admin/retrain` | Trigger model retraining |

---

## Browser Extension

1. Open Chrome → `chrome://extensions/`
2. Enable "Developer mode"
3. Click "Load unpacked" → select the `extension/` folder
4. Click the extension icon on any news webpage to analyse it

For Firefox, use `extension/manifest.v2.json` (see `extension/build.ps1`).

---

## Running Tests

```bash
# Backend tests
cd backend
pytest

# Frontend tests
cd frontend
npm test
```

---

## Language Support

| Language | Method |
|----------|--------|
| English | Direct ML classification |
| Telugu | Translated to English → classified |
| Hindi | Translated to English → classified |

---

## Notes

- The ML model was trained on the [ISOT Fake News Dataset](https://www.uvic.ca/engineering/ece/isot/datasets/) (Reuters/AP articles, 2016–2018)
- URL analysis works best with publicly accessible articles; paywalled or Cloudflare-protected sites may not be accessible
- Confidence below 70% shows a warning — treat those results with caution
