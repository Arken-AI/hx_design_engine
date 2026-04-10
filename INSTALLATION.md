# Installation & Setup

## Prerequisites

- **Python 3.11+**
- **Redis** (session state store)
- **MongoDB** (optional — fouling factor cache)
- **Anthropic API key** (for AI-powered design review steps)

---

## 1. Clone & Enter the Project

```bash
cd hx_design_engine
```

## 2. Create a Virtual Environment

```bash
python3.11 -m venv venv
source venv/bin/activate
```

## 3. Install Dependencies

**Core + thermo libraries (recommended):**

```bash
pip install ".[thermo]"
```

**Core only (skip CoolProp / IAPWS / thermo):**

```bash
pip install .
```

**Dev / testing extras:**

```bash
pip install ".[dev]"
```

## 4. Configure Environment Variables

```bash
cp .env.example .env
```

Edit `.env` and fill in the required values:

| Variable               | Required | Description                                                |
| ---------------------- | -------- | ---------------------------------------------------------- |
| `HX_ANTHROPIC_API_KEY` | Yes      | Anthropic API key for Claude                               |
| `HX_REDIS_URL`         | Yes      | Redis connection URL (default: `redis://localhost:6379/0`) |
| `HX_MONGODB_URI`       | No       | MongoDB connection string                                  |
| `HX_MONGODB_DB_NAME`   | No       | MongoDB database name (default: `arken_process_db`)        |
| `HX_HOST`              | No       | Bind address (default: `0.0.0.0`)                          |
| `HX_PORT`              | No       | Port (default: `8100`)                                     |
| `HX_DEBUG`             | No       | Debug mode (default: `false`)                              |
| `HX_LOG_LEVEL`         | No       | Logging level (default: `INFO`)                            |

## 5. Start Redis

```bash
# macOS (Homebrew)
brew services start redis

# Linux
sudo systemctl start redis

# Docker
docker run -d --name redis -p 6379:6379 redis:7-alpine
```

## 6. Start MongoDB (Optional)

```bash
docker run -d --name mongo \
  -p 27017:27017 \
  -e MONGO_INITDB_ROOT_USERNAME=admin \
  -e MONGO_INITDB_ROOT_PASSWORD=admin \
  mongo:7
```

## 7. Run the Server

```bash
uvicorn hx_engine.app.main:app --host 0.0.0.0 --port 8100 --reload
```

The API is now available at **http://localhost:8100**.

- Health check: `GET /health`
- API docs: `GET /docs` (Swagger UI)
- API routes are under `/api/v1/hx/`

---

## Running with Docker

```bash
docker build -t hx-design-engine .
docker run -d --name hx-engine \
  -p 8100:8100 \
  --env-file .env \
  hx-design-engine
```

---

## Running Tests

```bash
pip install ".[dev]"
pytest
```
