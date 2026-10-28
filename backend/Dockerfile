FROM python:3.12-slim@sha256:aa943ce411423c7582288f18707ff66eddcbaeb510502d747a72aeb34f30d159
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app/backend \
    OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
WORKDIR /app
COPY backend/requirements.runtime.lock /app/backend/requirements.runtime.lock
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 libseccomp2 && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir -r backend/requirements.runtime.lock \
    && useradd --uid 10001 --create-home --shell /usr/sbin/nologin vantage \
    && mkdir -p /app/artifacts/models /app/artifacts/documents /app/artifacts/private \
    && chown -R 10001:10001 /app/artifacts
COPY --chown=root:root backend/app /app/backend/app
COPY --chown=root:root backend/migrations /app/backend/migrations
COPY --chown=root:root backend/scripts /app/backend/scripts
COPY --chown=root:root backend/alembic.ini backend/pyproject.toml /app/backend/
COPY --chown=root:root data /app/data
ARG BUILD_COMMIT=development
LABEL org.opencontainers.image.source="https://github.com/Kumaryan12/VANTAGE" org.opencontainers.image.revision=$BUILD_COMMIT
ENV BUILD_COMMIT=$BUILD_COMMIT
USER 10001:10001
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log", "--timeout-keep-alive", "5", "--limit-concurrency", "64"]
