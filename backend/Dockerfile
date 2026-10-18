# A backend image-e: Python 3.12 + a uv.lock szerint rögzített csomagok + a kód.
FROM python:3.12-slim

# A uv-t a hivatalos image-ből másoljuk be (nem pip-pel telepítjük).
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /uvx /bin/

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

# Előbb csak a függőségeket telepítjük: ha csak a kód változik, a Docker ezt a
# lépést a gyorsítótárból veszi, és nem tölt le mindent újra.
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev

COPY . .
ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000
# Induláskor előbb az adatbázis-séma frissül (migrációk), utána indul az API.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
