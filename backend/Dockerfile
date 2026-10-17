# Pełny obraz (nie -slim): koła rasterio/pyogrio wymagają bibliotek systemowych, m.in. libexpat.
FROM python:3.12

# Opcjonalne dodatkowe certyfikaty CA (np. proxy firmowe): pliki *.crt w backend/certs/.
COPY certs/ /usr/local/share/ca-certificates/extra/
RUN update-ca-certificates >/dev/null 2>&1 || true
ENV PIP_CERT=/etc/ssl/certs/ca-certificates.crt \
    REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt \
    SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt \
    PYTHONUNBUFFERED=1 \
    TZ=Europe/Warsaw

WORKDIR /app/backend
COPY pyproject.toml ./
COPY grzyby ./grzyby
RUN pip install --no-cache-dir -e ".[dev]"
COPY tests ./tests
WORKDIR /app
