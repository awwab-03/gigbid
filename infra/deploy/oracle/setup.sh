#!/usr/bin/env bash
# One-time setup of the Always Free VM.Standard.E2.1.Micro (1 GB RAM, Ubuntu 24.04). Run as ubuntu from ~/gigbid.
# Expects ~/gigbid.env (secrets, chmod 600) and ~/web-dist (the built React app) to exist already.
set -euo pipefail
source ~/gigbid.env
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq postgresql postgresql-16-pgvector caddy >/dev/null
DB_PW=$(python3 -c "import os,urllib.parse as u;print(u.urlparse(os.environ['DATABASE_URL']).password)")
sudo -u postgres psql -v ON_ERROR_STOP=0 -q <<SQL
CREATE ROLE gigbid LOGIN PASSWORD '$DB_PW';
CREATE DATABASE gigbid OWNER gigbid;
SQL
sudo -u postgres psql -q -d gigbid -c "CREATE EXTENSION IF NOT EXISTS vector;"
python3 -m venv .venv && .venv/bin/pip install -q --upgrade pip uv && .venv/bin/uv pip install -q -e . --python .venv/bin/python
mkdir -p ~/state && sudo mkdir -p /srv/gigbid && sudo rsync -a --delete ~/web-dist/ /srv/gigbid/
sudo cp infra/deploy/oracle/Caddyfile /etc/caddy/Caddyfile
echo "SITE_ADDRESS=$SITE_ADDRESS" | sudo tee /etc/default/caddy >/dev/null
sudo mkdir -p /etc/systemd/system/caddy.service.d
printf '[Service]\nEnvironmentFile=/etc/default/caddy\n' | sudo tee /etc/systemd/system/caddy.service.d/env.conf >/dev/null
sudo cp infra/deploy/oracle/gigbid-*.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now gigbid-gigsim gigbid-api && sudo systemctl restart caddy
