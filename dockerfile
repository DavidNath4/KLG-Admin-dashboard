FROM python:3.11-alpine

# Logging ke stdout, no .pyc, dan default PORT
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=3000

WORKDIR /app

# Runtime libs yang dibutuhkan saat jalan (TIDAK dihapus)
# - ca-certificates: HTTPS
# - libstdc++: beberapa wheel butuh
# - libffi, openssl: dipakai di runtime oleh beberapa lib (tanpa header dev)
RUN apk add --no-cache ca-certificates libstdc++ libffi openssl

# Copy daftar dependencies lebih dulu biar layer cache efektif
COPY requirements.txt .

# Pasang build deps sementara (akan dihapus) lalu install pip requirements
# - build-base, gcc, musl-dev: toolchain C
# - libffi-dev, openssl-dev: header untuk compile
# - cargo: jika ada lib yang butuh Rust (mis. cryptography versi lama/tanpa wheel)
RUN apk add --no-cache --virtual .build-deps \
        build-base gcc musl-dev libffi-dev openssl-dev cargo \
    && pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt \
    && apk del .build-deps

# Copy source code
COPY . .

# (Opsional) user non-root
# RUN adduser -D -H appuser && chown -R appuser:appuser /app
# USER appuser

EXPOSE 3000

# Gunicorn: port fleksibel + log ke stdout/stderr
CMD sh -c 'gunicorn --bind 0.0.0.0:${PORT:-3000} --access-logfile - --error-logfile - app:create_app()'
