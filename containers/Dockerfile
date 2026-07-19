FROM python:3.14-slim@sha256:cea0e6040540fb2b965b6e7fb5ffa00871e632eef63719f0ea54bca189ce14a6

LABEL org.opencontainers.image.title="PyFixAgent runner" \
      org.opencontainers.image.description="Network-disabled test runner for PyFixAgent" \
      org.opencontainers.image.version="0.7.1" \
      org.opencontainers.image.source="https://github.com/instruzhao/pyfix-agent"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    MPLCONFIGDIR=/tmp/matplotlib

COPY containers/requirements.lock /tmp/pyfixagent-requirements.lock
RUN python -m pip install --no-cache-dir --require-hashes -r /tmp/pyfixagent-requirements.lock \
    && rm /tmp/pyfixagent-requirements.lock

WORKDIR /workspace
USER 65534:65534
ENTRYPOINT []
