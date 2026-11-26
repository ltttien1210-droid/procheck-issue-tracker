FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl unixodbc \
    && curl -fsSL https://packages.microsoft.com/config/debian/12/packages-microsoft-prod.deb -o /tmp/microsoft.deb \
    && dpkg -i /tmp/microsoft.deb && rm /tmp/microsoft.deb \
    && apt-get update && ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql18 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt requirements-mssql.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-mssql.txt && useradd --system appuser
COPY --chown=appuser:appuser procheck ./procheck
COPY --chown=appuser:appuser scripts/mssql_bootstrap.py ./scripts/mssql_bootstrap.py
COPY --chown=appuser:appuser tests ./tests
USER appuser
ENV PYTHONPATH=/app
CMD ["python", "scripts/mssql_bootstrap.py", "gunicorn", "--workers", "1", "--bind", "0.0.0.0:5050", "procheck:create_app()"]
