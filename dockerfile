FROM python:3.11-alpine

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=3000

WORKDIR /app

# Runtime deps (HTTPS, C++ runtime, BLAS untuk numpy/pandas)
RUN apk add --no-cache ca-certificates libstdc++ openblas

# Install pip deps (pakai build deps sementara lalu hapus)
COPY requirements.txt .
RUN apk add --no-cache --virtual .build-deps \
        build-base gcc musl-dev openblas-dev python3-dev \
    && pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt \
    && apk del .build-deps

# App source
COPY . .

# Compile Python files to bytecode and remove source files
RUN python -m compileall -b . && \
    find . -name "*.py" -not -path "./venv/*" -delete && \
    find . -name "__pycache__" -exec rm -rf {} + || true

EXPOSE 3000

# Gunicorn via /bin/sh agar ${PORT} bisa diexpand,
# dan **QUOTE** "app:create_app()" supaya tidak dianggap fungsi shell.
CMD sh -c 'exec gunicorn --bind 0.0.0.0:${PORT:-3000} --access-logfile - --error-logfile - "app:create_app()"'
