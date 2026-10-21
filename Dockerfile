# syntax=docker/dockerfile:1
#
# Slipstream all-in-one image: FastAPI backend + built web UI + OpenFOAM solver.
#
# The backend launches OpenFOAM as an external process through an `openfoam -c
# "<shell>"` wrapper. The OpenCFD image ships exactly that wrapper at
# /usr/bin/openfoam, so the app runs unmodified inside the container - no
# Docker-in-Docker and no second container to coordinate.
#
# Build:
#   cd frontend && npm ci && npm run build     # once, or use deploy/export-image.*
#   docker build -t slipstream:0.2.0 .
#
# Run:
#   docker run -d --name slipstream --init -p 8000:8000 \
#     -v slipstream-data:/data --shm-size=1g slipstream:0.2.0

ARG OPENFOAM_IMAGE=opencfd/openfoam-default:2512

# ---------------------------------------------------------------------------
# Runtime: OpenFOAM v2512 (Ubuntu 24.04) + Python 3.12 backend + built web UI
#
# The frontend is built on the host (frontend/dist) instead of in a Node build
# stage: the runtime base image is ~2.2 GB already, and this keeps the build
# working on offline/corporate networks without pulling a second base image.
# ---------------------------------------------------------------------------
FROM ${OPENFOAM_IMAGE}

ARG PIP_INDEX_URL=https://pypi.org/simple
ARG SLIPSTREAM_VERSION=0.2.0

LABEL org.opencontainers.image.title="Slipstream" \
      org.opencontainers.image.description="Virtual wind tunnel: STL in, CFD out (OpenFOAM + FastAPI + web UI)" \
      org.opencontainers.image.version="${SLIPSTREAM_VERSION}" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.source="https://github.com/OwenTWebb/slipstream"

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HOME=/home/openfoam \
    SLIPSTREAM_HOST=0.0.0.0 \
    SLIPSTREAM_PORT=8000 \
    SLIPSTREAM_DATA_DIR=/data \
    SLIPSTREAM_STATIC=/app/ui \
    SLIPSTREAM_WORKERS=2 \
    OMPI_ALLOW_RUN_AS_ROOT=1 \
    OMPI_ALLOW_RUN_AS_ROOT_CONFIRM=1

# MPI as root is refused by OpenMPI unless the two OMPI_ALLOW_RUN_AS_ROOT*
# variables above are set; the image defaults to a non-root user anyway.

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        libgomp1 \
        python3 \
        python3-venv \
        tzdata \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}"

COPY backend/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --index-url "${PIP_INDEX_URL}" -r /tmp/requirements.txt \
    && rm -f /tmp/requirements.txt

WORKDIR /app/backend
COPY backend/ /app/backend/
COPY frontend/dist/ /app/ui/

# uid/gid 10001 = "openfoam" (the name the container entrypoint reports for a
# non-root user). /home/openfoam already exists in the base image; take it over
# so OpenFOAM can write per-user config there.
RUN groupadd --gid 10001 openfoam \
    && useradd --uid 10001 --gid 10001 --home-dir /home/openfoam \
        --no-create-home --shell /bin/bash openfoam \
    && mkdir -p /data \
    && chown -R 10001:10001 /data /app /home/openfoam \
    && chmod -R a+rX /opt/venv

USER 10001:10001

EXPOSE 8000
VOLUME ["/data"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import sys, urllib.request; \
sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4).status == 200 else 1)"

# The base image's entrypoint (/openfoam/run) sources the OpenFOAM environment,
# changes to $HOME and then execs this command - use an absolute script path.
CMD ["python", "/app/backend/run_server.py"]
