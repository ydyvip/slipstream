#!/usr/bin/env bash
# Slipstream deployment helper.
#
#   ./deploy.sh              load the image (if needed) and start the stack
#   ./deploy.sh --image FILE load a specific exported image tarball, then start
#   ./deploy.sh status       container state + API health
#   ./deploy.sh logs         follow container logs
#   ./deploy.sh restart      restart the container
#   ./deploy.sh down         stop and remove the container (data volume kept)
#
# Works in the repository (deploy/deploy.sh, compose file at the repo root) and
# in the exported deployment package (script next to docker-compose.yml).
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "$HERE/docker-compose.yml" ]]; then
    PKG_DIR="$HERE"
elif [[ -f "$HERE/../docker-compose.yml" ]]; then
    PKG_DIR="$(cd "$HERE/.." && pwd)"
else
    echo "error: docker-compose.yml not found next to $HERE or its parent" >&2
    exit 1
fi
cd "$PKG_DIR"
COMPOSE_FILE="$PKG_DIR/docker-compose.yml"

ACTION="up"
IMAGE_FILE=""

usage() {
    sed -n '2,12p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        up|down|logs|status|restart) ACTION="$1"; shift ;;
        -f|--image) IMAGE_FILE="${2:?--image needs a file path}"; shift 2 ;;
        -h|--help) usage; exit 0 ;;
        *) echo "error: unknown argument '$1'" >&2; usage >&2; exit 2 ;;
    esac
done

command -v docker >/dev/null 2>&1 || {
    echo "error: docker is not installed or not on PATH" >&2
    exit 1
}

# Prefer the Compose v2 plugin, fall back to the standalone v1 binary.
if docker compose version >/dev/null 2>&1; then
    COMPOSE=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
    COMPOSE=(docker-compose)
else
    echo "error: Docker Compose not found (need 'docker compose' or 'docker-compose')" >&2
    exit 1
fi

compose() {
    "${COMPOSE[@]}" -f "$COMPOSE_FILE" "$@"
}

compose_image() {
    local img=""
    img="$(compose config --images 2>/dev/null | tr -d '\r' | head -n1 || true)"
    if [[ -z "$img" ]]; then
        # Compose v1 has no `config --images`; `config` still resolves .env
        # and prints the effective image.
        img="$(compose config 2>/dev/null \
            | sed -n 's/^[[:space:]]*image:[[:space:]]*//p' \
            | head -n1 || true)"
    fi
    if [[ -z "$img" ]]; then
        img="$(sed -n 's/^[[:space:]]*image:[[:space:]]*//p' "$COMPOSE_FILE" | head -n1)"
        # Resolve the ${SLIPSTREAM_IMAGE:-default} form used in the compose file.
        if [[ "$img" == '${SLIPSTREAM_IMAGE:-'*'}' ]]; then
            img="${img#\$\{SLIPSTREAM_IMAGE:-}"
            img="${img%\}}"
        fi
    fi
    img="${img%\"}"
    img="${img#\"}"
    printf '%s' "${img:-slipstream:0.2.0}"
}

prepare_env() {
    local env_file="$PKG_DIR/.env"
    if [[ ! -f "$env_file" ]]; then
        local example=""
        if [[ -f "$PKG_DIR/.env.example" ]]; then
            example="$PKG_DIR/.env.example"
        elif [[ -f "$PKG_DIR/deploy/.env.example" ]]; then
            example="$PKG_DIR/deploy/.env.example"
        fi
        if [[ -n "$example" ]]; then
            cp "$example" "$env_file"
            echo "created $env_file from $example"
        else
            : > "$env_file"
        fi
    fi

    # Pick a safe worker count on first run: each analysis uses 6 MPI ranks.
    if [[ -z "${SLIPSTREAM_WORKERS:-}" ]] \
       && ! grep -Eq '^[[:space:]]*SLIPSTREAM_WORKERS[[:space:]]*=' "$env_file" 2>/dev/null; then
        local cores workers
        cores="$(getconf _NPROCESSORS_ONLN 2>/dev/null || nproc 2>/dev/null || echo 4)"
        if (( cores >= 12 )); then workers=2; else workers=1; fi
        {
            printf '\n# Added by deploy.sh: %s hardware threads detected\n' "$cores"
            printf 'SLIPSTREAM_WORKERS=%s\n' "$workers"
        } >> "$env_file"
        echo "set SLIPSTREAM_WORKERS=$workers (host threads: $cores)"
    fi
}

find_tarball() {
    local f
    f="$(find "$PKG_DIR" -maxdepth 1 -type f \
        \( -name 'slipstream-*.tar.gz' -o -name 'slipstream-*.tar' \) \
        -print 2>/dev/null | sort | tail -n1)"
    printf '%s' "$f"
}

load_image() {
    local img="$1" file="$2"
    if [[ -n "$file" ]]; then
        [[ -f "$file" ]] || { echo "error: image file not found: $file" >&2; exit 1; }
        echo "loading image from $file ..."
        docker load -i "$file"
        return 0
    fi
    if docker image inspect "$img" >/dev/null 2>&1; then
        echo "image $img already present"
        return 0
    fi
    file="$(find_tarball)"
    if [[ -z "$file" ]]; then
        echo "error: image '$img' is not loaded and no slipstream-*.tar.gz is next to $COMPOSE_FILE" >&2
        echo "       run: docker load -i <exported-image>.tar.gz" >&2
        exit 1
    fi
    echo "loading image from $file ..."
    docker load -i "$file"
    docker image inspect "$img" >/dev/null 2>&1 || {
        echo "error: $file did not provide image '$img'" >&2
        exit 1
    }
}

wait_healthy() {
    local cid deadline status
    cid="$(compose ps -q slipstream 2>/dev/null | tr -d '\r' | head -n1 || true)"
    if [[ -z "$cid" ]]; then
        echo "error: the slipstream container was not created" >&2
        compose ps >&2 || true
        exit 1
    fi
    deadline=$((SECONDS + 180))
    while (( SECONDS < deadline )); do
        status="$(docker inspect --format \
            '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' \
            "$cid" 2>/dev/null || echo unknown)"
        case "$status" in
            healthy)
                return 0
                ;;
            unhealthy|exited|dead)
                echo "error: container is $status; recent logs:" >&2
                compose logs --tail=80 slipstream >&2 || true
                exit 1
                ;;
        esac
        sleep 3
    done
    echo "error: container did not become healthy within 180s; recent logs:" >&2
    compose logs --tail=80 slipstream >&2 || true
    exit 1
}

print_url() {
    local published port
    published="$(compose port slipstream 8000 2>/dev/null | tr -d '\r' | head -n1 || true)"
    port="${published##*:}"
    port="${port:-8000}"
    echo
    echo "Slipstream is ready:  http://localhost:${port}"
    echo "API health:           http://localhost:${port}/api/health"
    echo "LAN access:           http://<this-host-ip>:${port}"
}

case "$ACTION" in
    up)
        prepare_env
        IMG="$(compose_image)"
        load_image "$IMG" "$IMAGE_FILE"
        echo "starting $IMG ..."
        compose up -d
        wait_healthy
        print_url
        ;;
    down)
        compose down
        echo "container removed; run data is kept in the 'slipstream-data' volume (unless a bind mount is configured)."
        ;;
    logs)
        compose logs -f --tail=200 slipstream
        ;;
    status)
        compose ps
        cid="$(compose ps -q slipstream 2>/dev/null | tr -d '\r' | head -n1 || true)"
        if [[ -n "$cid" ]]; then
            echo
            docker inspect --format 'health: {{if .State.Health}}{{.State.Health.Status}}{{else}}n/a{{end}}  status: {{.State.Status}}' "$cid" || true
            port="$(compose port slipstream 8000 2>/dev/null | tr -d '\r' | head -n1 || true)"
            port="${port##*:}"
            port="${port:-8000}"
            echo "health URL: http://localhost:${port}/api/health"
            if command -v curl >/dev/null 2>&1; then
                curl -fsS "http://localhost:${port}/api/health" || true
                echo
            fi
        fi
        ;;
    restart)
        compose restart
        wait_healthy
        print_url
        ;;
esac
