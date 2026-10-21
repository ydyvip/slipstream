#!/usr/bin/env bash
# Build the Slipstream image and export it as a self-contained deployment package.
#
#   ./deploy/export-image.sh
#   SLIPSTREAM_VERSION=0.3.0 ./deploy/export-image.sh
#   PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple \
#   NPM_REGISTRY=https://registry.npmmirror.com ./deploy/export-image.sh
#
# Output (default: <repo>/dist-docker/):
#   slipstream-<version>-<os>-<arch>.tar.gz   docker save artifact
#   docker-compose.yml, deploy.sh, deploy.ps1, .env.example, README.md
#   SHA256SUMS
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"

VERSION="${SLIPSTREAM_VERSION:-}"
if [[ -z "$VERSION" ]]; then
    VERSION="$(sed -n 's/^[[:space:]]*"version":[[:space:]]*"\([^"]*\)".*/\1/p' \
        "$ROOT/frontend/package.json" | head -n1)"
fi
VERSION="${VERSION:-0.2.0}"

IMAGE="${SLIPSTREAM_IMAGE:-slipstream:$VERSION}"
OPENFOAM_IMAGE="${OPENFOAM_IMAGE:-opencfd/openfoam-default:2512}"
OUT_DIR="${SLIPSTREAM_OUT_DIR:-$ROOT/dist-docker}"

command -v docker >/dev/null 2>&1 || {
    echo "error: docker is not installed or not on PATH" >&2
    exit 1
}

BUILD_ARGS=(
    --build-arg "OPENFOAM_IMAGE=$OPENFOAM_IMAGE"
    --build-arg "SLIPSTREAM_VERSION=$VERSION"
)
[[ -n "${PIP_INDEX_URL:-}" ]] && BUILD_ARGS+=(--build-arg "PIP_INDEX_URL=$PIP_INDEX_URL")
[[ -n "${SLIPSTREAM_PLATFORM:-}" ]] && BUILD_ARGS+=(--platform "$SLIPSTREAM_PLATFORM")

# The image copies the prebuilt frontend/dist, so build it on the host first.
if [[ "${SLIPSTREAM_SKIP_FRONTEND_BUILD:-0}" == "1" ]]; then
    [[ -f "$ROOT/frontend/dist/index.html" ]] || {
        echo "error: SLIPSTREAM_SKIP_FRONTEND_BUILD=1 but frontend/dist is missing" >&2
        exit 1
    }
else
    command -v npm >/dev/null 2>&1 || {
        echo "error: npm is required to build the web UI (or set SLIPSTREAM_SKIP_FRONTEND_BUILD=1)" >&2
        exit 1
    }
    if [[ ! -d "$ROOT/frontend/node_modules" ]]; then
        echo "installing frontend dependencies ..."
        ( cd "$ROOT/frontend" \
          && if [[ -n "${NPM_REGISTRY:-}" ]]; then
                 npm ci --no-audit --no-fund --registry "$NPM_REGISTRY"
             else
                 npm ci --no-audit --no-fund
             fi )
    fi
    echo "building frontend ..."
    ( cd "$ROOT/frontend" && npm run build )
fi

echo "=============================================================="
echo " Slipstream image export"
echo "   version      : $VERSION"
echo "   image        : $IMAGE"
echo "   OpenFOAM base: $OPENFOAM_IMAGE"
echo "   output       : $OUT_DIR"
echo "=============================================================="
echo "building (this can take a while on the first run) ..."

docker build "${BUILD_ARGS[@]}" -t "$IMAGE" "$ROOT"

ARCH="$(docker image inspect "$IMAGE" --format '{{.Os}}-{{.Architecture}}' | tr -d '\r')"
ARCH="${ARCH//\//-}"

mkdir -p "$OUT_DIR"
FILE="$OUT_DIR/slipstream-${VERSION}-${ARCH}.tar.gz"

echo "exporting $IMAGE -> $FILE ..."
TMP="$FILE.tmp"
trap 'rm -f "$TMP"' EXIT

if command -v gzip >/dev/null 2>&1; then
    docker save "$IMAGE" | gzip -6 > "$TMP"
    mv "$TMP" "$FILE"
else
    FILE="$OUT_DIR/slipstream-${VERSION}-${ARCH}.tar"
    TMP="$FILE.tmp"
    docker save -o "$TMP" "$IMAGE"
    mv "$TMP" "$FILE"
    echo "note: gzip not found; exported an uncompressed .tar"
fi
trap - EXIT

# Deployment package contents (script run from the package or the repo).
cp "$ROOT/docker-compose.yml" "$OUT_DIR/"
cp "$ROOT/deploy/deploy.sh" "$OUT_DIR/"
cp "$ROOT/deploy/deploy.ps1" "$OUT_DIR/"
cp "$ROOT/deploy/.env.example" "$OUT_DIR/"
cp "$ROOT/deploy/README.md" "$OUT_DIR/"
chmod +x "$OUT_DIR/deploy.sh"

(
    cd "$OUT_DIR"
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum "$(basename "$FILE")" > SHA256SUMS
    elif command -v shasum >/dev/null 2>&1; then
        shasum -a 256 "$(basename "$FILE")" > SHA256SUMS
    else
        echo "note: no sha256sum/shasum; SHA256SUMS not generated"
    fi
)

SIZE="$(du -h "$FILE" 2>/dev/null | cut -f1 || echo '?')"
echo
echo "done: $FILE ($SIZE)"
echo "deployment package: $OUT_DIR"
ls -1 "$OUT_DIR"
