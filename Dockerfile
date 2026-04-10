FROM python:3.11-slim

WORKDIR /app

# System deps
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc g++ gfortran && \
    rm -rf /var/lib/apt/lists/*

# Install Python deps
COPY pyproject.toml ./
RUN pip install --no-cache-dir ".[thermo]"

# Copy source
COPY hx_engine/ ./hx_engine/

EXPOSE 8100

CMD ["uvicorn", "hx_engine.app.main:app", "--host", "0.0.0.0", "--port", "8100"]
