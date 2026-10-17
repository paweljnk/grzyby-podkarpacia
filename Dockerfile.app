# Obraz "wszystko w jednym" do uruchomienia w domu / na serwerze: API + zbudowana PWA.
# Kod, konfiguracja i baza wiedzy są w obrazie; dane (DEM, cache) w wolumenie ./data.

# --- etap 1: frontend (PWA) ---
FROM node:22-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# --- etap 2: backend ---
FROM python:3.12
COPY backend/certs/ /usr/local/share/ca-certificates/extra/
RUN update-ca-certificates >/dev/null 2>&1 || true
ENV PIP_CERT=/etc/ssl/certs/ca-certificates.crt \
    REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt \
    SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt \
    PYTHONUNBUFFERED=1 TZ=Europe/Warsaw GRZYBY_ROOT=/app
WORKDIR /app/backend
COPY backend/pyproject.toml ./
COPY backend/grzyby ./grzyby
RUN pip install --no-cache-dir .
WORKDIR /app
COPY config ./config
COPY species ./species
COPY db ./db
COPY docs/schemas ./docs/schemas
COPY sources.yaml ./
COPY --from=web /web/dist ./frontend/dist
EXPOSE 8000
CMD ["uvicorn", "grzyby.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
