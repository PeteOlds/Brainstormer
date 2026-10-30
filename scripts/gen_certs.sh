#!/usr/bin/env bash
# Generate a self-signed TLS certificate for LAN use.
#
#   ./scripts/gen_certs.sh                  # auto-detect this host's IPs
#   ./scripts/gen_certs.sh 192.168.1.20     # add extra SANs
#
# Writes certs/server.crt and certs/server.key (0600). docker-compose mounts
# ./certs read-only at /certs, so the container serves HTTPS as soon as
# TLS_CERT_FILE=/certs/server.crt and TLS_KEY_FILE=/certs/server.key are set.
#
# Self-signed means browsers warn until the certificate is trusted. That is
# fine on a LAN; for internet exposure use a real CA (Let's Encrypt) instead.
set -euo pipefail

CERT_DIR="${CERT_DIR:-certs}"
CERT_FILE="$CERT_DIR/server.crt"
KEY_FILE="$CERT_DIR/server.key"
DAYS="${DAYS:-825}"
HOSTNAME_FQDN="$(hostname -f 2>/dev/null || hostname)"

if [ -e "$CERT_FILE" ] || [ -e "$KEY_FILE" ]; then
    echo "Refusing to overwrite existing $CERT_DIR/server.{crt,key}." >&2
    echo "Remove them first if you really want a new certificate." >&2
    exit 1
fi

# Collect SANs: localhost, the hostname, every non-loopback IPv4 address,
# plus anything passed on the command line.
SANS="DNS:localhost,DNS:${HOSTNAME_FQDN},IP:127.0.0.1"
while read -r ip; do
    [ -z "$ip" ] && continue
    SANS="${SANS},IP:${ip}"
done < <(hostname -I 2>/dev/null | tr ' ' '\n' | grep -E '^[0-9]+(\.[0-9]+){3}$' || true)
for extra in "$@"; do
    if printf '%s' "$extra" | grep -qE '^[0-9]+(\.[0-9]+){3}$'; then
        SANS="${SANS},IP:${extra}"
    else
        SANS="${SANS},DNS:${extra}"
    fi
done

mkdir -p "$CERT_DIR"

openssl req -x509 -nodes -newkey rsa:2048 \
    -keyout "$KEY_FILE" \
    -out "$CERT_FILE" \
    -days "$DAYS" \
    -subj "/CN=${HOSTNAME_FQDN}" \
    -addext "subjectAltName=${SANS}" \
    -addext "basicConstraints=critical,CA:FALSE" \
    -addext "keyUsage=critical,digitalSignature,keyEncipherment" \
    -addext "extendedKeyUsage=serverAuth" >/dev/null 2>&1

chmod 600 "$KEY_FILE"
chmod 644 "$CERT_FILE"

echo "Created $CERT_FILE and $KEY_FILE"
echo "SANs: $SANS"
echo
echo "Enable it in .env:"
echo "  TLS_CERT_FILE=/certs/server.crt"
echo "  TLS_KEY_FILE=/certs/server.key"
echo "Then: docker compose up -d --force-recreate brainstormer-web"
