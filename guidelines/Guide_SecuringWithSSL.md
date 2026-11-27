# Securing Brainstormer with SSL/TLS

Brainstormer terminates TLS **inside its own container**. There is no
reverse proxy to install and no host-level certificate service to run:
mount a certificate and key, set two environment variables, restart.

> The second half of this guide is an optional, more advanced setup for
> teams running several services behind a private CA (step-ca + Caddy).
> It is not required for Brainstormer and is kept as an appendix.

## A. Self-contained TLS (recommended)

### 1. Create the certificate

For a local install or a small team, a self-signed certificate is fine:

```bash
mkdir -p certs
openssl req -x509 -newkey rsa:2048 -nodes -days 365 \
  -keyout certs/server.key -out certs/server.crt \
  -subj "/CN=brainstormer.local"
```

For a public domain, use your certificate provider (or Let's Encrypt)
and place the full-chain certificate and the unencrypted private key in
`certs/server.crt` and `certs/server.key`.

### 2. Tell Brainstormer where they are

In `.env`:

```bash
TLS_CERT_FILE=/certs/server.crt
TLS_KEY_FILE=/certs/server.key
```

`docker-compose.yml` already mounts `./certs` read-only at `/certs`.

### 3. Restart

```bash
docker restart brainstormer-web
```

Open `https://127.0.0.1:8000` (or your hostname). Brainstormer now:

- serves HTTPS on the normal port;
- redirects plain `http://` requests to `https://`;
- sends `Strict-Transport-Security` (HSTS, one year);
- marks session and JWT cookies `Secure`.

### 4. If something goes wrong

- **The site still loads over HTTP.** Check the two variables are set
  *and* the files are readable by the container user:
  `docker exec brainstormer-web ls -l /certs`.
  The app deliberately falls back to HTTP rather than crash.
- **Browser warning about the certificate.** That is expected for a
  self-signed certificate. Trust it on each client:
  - **Linux:** copy `certs/server.crt` to
    `/usr/local/share/ca-certificates/` and run
    `sudo update-ca-certificates`.
  - **macOS:** import into Keychain Access → System → "Always Trust".
  - **Windows:** install into *Trusted Root Certification Authorities*.
- **Certificate expired.** Replace the two files and restart; no code or
  config changes are needed.

### 5. Behind a reverse proxy instead

If you already terminate TLS elsewhere, leave `TLS_CERT_FILE` and
`TLS_KEY_FILE` empty and set:

```bash
TRUST_PROXY_HEADERS=True
```

Do this only when a trusted proxy sits directly in front of the app —
otherwise clients can spoof `X-Forwarded-Proto`.

---

## B. Appendix: private CA for several services (step-ca)

Deploying **`step-ca`** alongside applications in Docker Compose gives you a complete, isolated private Certificate Authority (CA). By enabling `step-ca`’s built-in **ACME provisioner**, your applications and reverse proxies can automatically request, install, and renew local TLS certificates just as they would with Let’s Encrypt.

  

### Architecture Overview

```
                          ┌────────────────────────┐
                          │     Clients / LAN      │
                          └───────────┬────────────┘
                                      │ https://app.home.lan
                                      ▼
                      ┌────────────────────────────────┐
                      │        Reverse Proxy           │
                      │  (Caddy / Nginx Proxy Manager) │
                      └───────────────┬────────────────┘
                                      │ ACME TLS Requests
                                      ▼
 ┌────────────────────────────────────────────────────────────────────────┐
 │ Docker Network: step-ca-net                                           │
 │                                                                        │
 │   ┌──────────────────────┐              ┌──────────────────────────┐   │
 │   │       step-ca        │              │  App Developed by BS     │   │
 │   │ (Private ACME Server)│              │    (Backend/Frontend)    │   │
 │   └──────────────────────┘              └──────────────────────────┘   │
 └────────────────────────────────────────────────────────────────────────┘
```

### Step 1: Initialize and Run `step-ca` in Docker Compose

Create a working directory and set up a `docker-compose.yml` file:

  

YAML

```
version: '3.8'

networks:
  step-ca-net:
    driver: bridge

volumes:
  step-ca-data:

services:
  step-ca:
    image: smallstep/step-ca:latest
    container_name: step-ca
    restart: unless-stopped
    ports:
      - "9000:9000"
    environment:
      - DOCKER_STEPCA_INIT_NAME=Brainstormer Internal CA
      - DOCKER_STEPCA_INIT_DNS_NAMES=step-ca,localhost,127.0.0.1
      - DOCKER_STEPCA_INIT_ACME=true         # Enables ACME provisioner automatically
      - DOCKER_STEPCA_INIT_PASSWORD=SecretCAPassword123!
    volumes:
      - step-ca-data:/home/step
    networks:
      - step-ca-net
```

Start `step-ca`:

  

Bash

```
docker compose up -d step-ca
```

When started with `DOCKER_STEPCA_INIT_ACME=true`, `step-ca` initializes its internal database and creates an ACME directory endpoint at:

`https://step-ca:9000/acme/acme/directory`

  

### Step 2: Retrieve the Root Certificate Fingerprint

Your applications and reverse proxy must trust the internal `step-ca` Root CA certificate to request and validate certificates smoothly. Get the CA root fingerprint:

  

Bash

```
docker exec step-ca step certificate fingerprint /home/step/certs/root_ca.crt
```

_Save this 64-character hash value for client configuration._

  

### Step 3: Automatically Secure Applications via Reverse Proxy

Rather than embedding TLS certificate management logic inside your custom application code, terminate TLS at a modern reverse proxy (like **Caddy**) running on the same network. Caddy handles automatic ACME certificate requests and 60-day background renewals with minimal configuration.

  

Add Caddy and your BS app service to `docker-compose.yml`:

  

YAML

```
services:
  # --- STEP-CA ---
  step-ca:
    image: smallstep/step-ca:latest
    container_name: step-ca
    restart: unless-stopped
    ports:
      - "9000:9000"
    environment:
      - DOCKER_STEPCA_INIT_NAME=Brainstormer Internal CA
      - DOCKER_STEPCA_INIT_DNS_NAMES=step-ca,localhost,127.0.0.1
      - DOCKER_STEPCA_INIT_ACME=true
      - DOCKER_STEPCA_INIT_PASSWORD=SecretCAPassword123!
    volumes:
      - step-ca-data:/home/step
    networks:
      - step-ca-net

  # --- YOUR APPLICATION ---
  bs-app:
    image: your-repo/bs-app:latest  # Your application developed by BS
    container_name: bs-app
    restart: unless-stopped
    expose:
      - "8080"
    networks:
      - step-ca-net

  # --- REVERSE PROXY (CADDY) ---
  caddy:
    image: caddy:2-alpine
    container_name: caddy
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile
      - step-ca-data:/certs:ro      # Mount root CA cert so Caddy can trust step-ca
    networks:
      - step-ca-net
```

### Step 4: Configure the Reverse Proxy (`Caddyfile`)

Create a `Caddyfile` alongside your `docker-compose.yml`:

  

Code snippet

```
{
    # Tell Caddy to trust your internal step-ca Root Certificate
    pki {
        ca local {
            root_trust /certs/certs/root_ca.crt
        }
    }
}

# The internal local domain for your BS application
app.home.lan {
    tls {
        # Point Caddy's ACME client to step-ca's directory endpoint
        ca https://step-ca:9000/acme/acme/directory
    }

    # Proxy traffic to your BS application container
    reverse_proxy bs-app:8080
}
```

Start the full stack:

  

Bash

```
docker compose up -d
```

Caddy will automatically contact `step-ca` over the private Docker network, validate the challenge, fetch a valid TLS certificate for `app.home.lan`, and auto-renew it in the background.

  

### Step 5: Trust the Root CA on Client Devices

Because `step-ca` acts as your own private Certificate Authority, client devices (laptops, phones, browsers) must trust its Root CA once to eliminate security warnings.

  

1. **Extract the Root Certificate:**
    
      
    
    Bash
    
    ```
    docker cp step-ca:/home/step/certs/root_ca.crt ./bs_root_ca.crt
    ```
    
2. **Install on Client Systems:**
    
      
    - **Linux:** Copy `bs_root_ca.crt` to `/usr/local/share/ca-certificates/` and run `sudo update-ca-certificates`.
        
          
        
    - **macOS:** Open Keychain Access, import `bs_root_ca.crt` into **System**, and set its trust settings to **"Always Trust"**.
        
          
        
    - **Windows:** Double-click `bs_root_ca.crt`, select **Install Certificate** $\rightarrow$ **Local Machine** $\rightarrow$ **Trusted Root Certification Authorities**.
        
          
        

### Alternative: Direct ACME in Application Containers (without Proxy)

If your app requires direct end-to-end TLS within its container without a reverse proxy, you can use `acme.sh` or `certbot` inside a sidecar container or container entrypoint script:

Bash

```
# Register account with internal ACME directory
acme.sh --register-account \
  --server https://step-ca:9000/acme/acme/directory \
  --ca-bundle /path/to/root_ca.crt

# Issue certificate via HTTP-01 challenge
acme.sh --issue -d bs-app.lan \
  --standalone \
  --server https://step-ca:9000/acme/acme/directory \
  --ca-bundle /path/to/root_ca.crt
```