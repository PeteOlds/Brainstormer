#!/bin/sh
# Container entrypoint: add TLS flags when a cert/key pair is mounted.
#
# Set TLS_CERT_FILE and TLS_KEY_FILE (e.g. /certs/server.crt and
# /certs/server.key). If both exist and are readable, gunicorn serves
# HTTPS on the normal port. Otherwise it starts plain HTTP exactly as
# before, so this entrypoint is safe for every existing deployment.
set -e

if [ -n "${TLS_CERT_FILE:-}" ] && [ -n "${TLS_KEY_FILE:-}" ]; then
    if [ -r "$TLS_CERT_FILE" ] && [ -r "$TLS_KEY_FILE" ]; then
        if [ "${1:-}" = "gunicorn" ]; then
            shift
            echo "TLS enabled: cert=$TLS_CERT_FILE key=$TLS_KEY_FILE"
            exec gunicorn "$@" --certfile "$TLS_CERT_FILE" --keyfile "$TLS_KEY_FILE"
        fi
        if [ "${1:-}" = "hypercorn" ]; then
            shift
            echo "TLS enabled: cert=$TLS_CERT_FILE key=$TLS_KEY_FILE"
            exec hypercorn "$@" --certfile "$TLS_CERT_FILE" --keyfile "$TLS_KEY_FILE"
        fi
        echo "TLS files found but the command is not gunicorn; starting unchanged." >&2
    else
        echo "TLS_CERT_FILE/TLS_KEY_FILE are set but not readable; starting HTTP." >&2
    fi
fi

exec "$@"
