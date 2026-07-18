FROM python:3.12-slim@sha256:57cd7c3a7a273101a6485ba99423ee568157882804b1124b4dd04266317710de

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    MPLCONFIGDIR=/tmp/matplotlib

COPY containers/requirements.lock /tmp/pyfixagent-requirements.lock
RUN python -m pip install --no-cache-dir -r /tmp/pyfixagent-requirements.lock \
    && rm /tmp/pyfixagent-requirements.lock

WORKDIR /workspace
ENTRYPOINT []
