# Oracle Cloud Free ARM VM — setup runbook

Stage 4 of build order. candidate runs this manually first time; subsequent re-provisioning automated via cloud-init.

## Account

- Sign up: https://www.oracle.com/cloud/free/ (uses candidate@example.com).
- Verify with credit card (no charge unless upgrading).
- Region: Mumbai (low latency from Delhi).

## VM provisioning

Compute → Instances → Create:
- Shape: **VM.Standard.A1.Flex** (Ampere ARM, always-free)
- 4 OCPU / 24 GB RAM (max free tier per tenancy)
- OS: Ubuntu 24.04 ARM
- Boot volume: 100 GB (free tier)
- SSH key: generate on candidate's Mac, paste public key in console.
- Networking: public IPv4 enabled.

## Initial setup (run via SSH)

```bash
# Update + base packages
sudo apt update && sudo apt -y upgrade
sudo apt -y install build-essential git curl jq htop tmux fail2ban ufw

# Firewall
sudo ufw allow OpenSSH
sudo ufw allow 5678/tcp  # n8n
sudo ufw enable

# fail2ban for SSH brute-force protection
sudo systemctl enable fail2ban

# Node 22 LTS
curl -fsSL https://deb.nodesource.com/setup_22.x | sudo bash -
sudo apt -y install nodejs

# Python 3.12 + venv
sudo apt -y install python3.12 python3.12-venv python3-pip pipx
pipx ensurepath

# Playwright
sudo apt -y install libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
  libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 libgbm1 \
  libasound2t64 libpango-1.0-0 libcairo2

# n8n self-hosted (Docker preferred)
sudo apt -y install docker.io docker-compose-v2
sudo usermod -aG docker $USER
# log out + back in

mkdir -p ~/n8n-data
cat > ~/docker-compose.yml <<EOF
services:
  n8n:
    image: n8nio/n8n:latest
    restart: always
    ports: ["5678:5678"]
    environment:
      - N8N_HOST=n8n.example.com
      - N8N_PROTOCOL=https
      - N8N_PORT=5678
      - WEBHOOK_URL=https://n8n.example.com/
      - GENERIC_TIMEZONE=Asia/Kolkata
      - N8N_BASIC_AUTH_ACTIVE=true
      - N8N_BASIC_AUTH_USER=reviewer
      - N8N_BASIC_AUTH_PASSWORD=<set on first run>
    volumes: ["~/n8n-data:/home/node/.n8n"]
EOF
docker compose up -d

# Claude Code CLI
curl -fsSL claude.ai/install.sh | bash
claude /login   # opens device-flow, paste candidate's Pro plan auth

# Codex CLI
# (install instructions per https://docs.codex.dev/install/)

# Antigravity CLI
# (install instructions per Google Antigravity docs; `agy login`)

# Python tools
pipx install python-jobspy
pipx install playwright
playwright install chromium

# Project dir mirror
git clone <repo or rsync from Mac> ~/JobHunt
```

## Cloudflare Tunnel

- Domain: register `example.com` (any short domain) or use existing.
- Cloudflare account → Zero Trust → Tunnels → Create tunnel.
- Subdomains:
  - `n8n.example.com` → http://localhost:5678
  - `review.example.com` → http://localhost:5678/webhook/review  (n8n hosts the Tinder app via webhook)

## Smoke test

```bash
# n8n reachable
curl -u reviewer:<password> https://n8n.example.com/healthz
# expected: {"status":"ok"}

# Claude Code authed
claude -p "say 'caveman hi' in 3 words" --model claude-haiku-4-5

# Playwright works
node -e "const {chromium}=require('playwright'); (async()=>{const b=await chromium.launch();const p=await b.newPage();await p.goto('https://google.com');console.log(await p.title());await b.close()})()"
```

## Monitoring

- `docker compose logs -f n8n` (or systemd journal).
- Oracle Cloud monitoring → CPU + memory alarms (free).
- n8n's built-in execution log + retry view.

## Backups

- Daily 02:00 IST cron: `tar czf ~/backups/n8n-$(date +%F).tgz ~/n8n-data` → rclone to Drive `/JobHunt/backups/`.
- Keep last 14 days; prune older.
