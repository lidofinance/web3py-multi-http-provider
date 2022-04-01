FROM python:3.9-slim as base

RUN apt-get update && apt-get install -y --no-install-recommends gcc libffi-dev g++ git curl
WORKDIR /app

FROM base as builder

ENV POETRY_VERSION=1.1.13
RUN pip install --no-cache-dir poetry==$POETRY_VERSION

COPY pyproject.toml poetry.lock ./
RUN python -m venv --copies /venv

RUN . /venv/bin/activate && poetry install --no-dev --no-root


FROM base as production

RUN mkdir /var/www && chown www-data /var/www && \
    apt-get clean && find /var/lib/apt/lists/ -type f -delete && \
    chown www-data /app/

COPY --from=builder /venv /venv
COPY . .

ENV PATH=$PATH:/app/venv/bin
ENV PYTHONPATH="/venv/lib/python3.9/site-packages/"

EXPOSE 9000
USER www-data

HEALTHCHECK --interval=10s --timeout=3s CMD curl -f http://localhost:9000/healthcheck || exit 1

ENTRYPOINT ["python3"]
CMD ["-u", "myproject/main.py"]
