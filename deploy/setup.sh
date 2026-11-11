#!/usr/bin/env bash
# Ubuntu 24.04 serverini sozlaydi va ilovani yangilaydi. Qayta ishga tushirish xavfsiz.
# Ishlatish (root): bash deploy/setup.sh <domen> <certbot-email>
set -euo pipefail

DOMAIN="${1:?Domen kiritilmagan}"
EMAIL="${2:?Certbot uchun email kiritilmagan}"
APP_DIR=/opt/talababot
TOKEN_FILE=/root/talababot.token
SITE=/etc/nginx/sites-available/talababot

if [[ $EUID -ne 0 ]]; then
  echo "Skriptni root sifatida ishga tushiring." >&2
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get install -y -q python3 python3-venv nginx certbot python3-certbot-nginx ufw

id talababot >/dev/null 2>&1 || useradd --system --home-dir "$APP_DIR" --shell /usr/sbin/nologin talababot
install -d -o talababot -g talababot -m 700 "$APP_DIR/var" "$APP_DIR/var/backups"

python3 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install -q --upgrade pip
"$APP_DIR/.venv/bin/pip" install -q -r "$APP_DIR/requirements.txt"

if [[ ! -f "$APP_DIR/.env" ]]; then
  if [[ ! -f "$TOKEN_FILE" ]]; then
    echo "$TOKEN_FILE topilmadi: unda TELEGRAM_BOT_TOKEN qiymati bo'lishi kerak." >&2
    exit 1
  fi
  (
    umask 077
    "$APP_DIR/.venv/bin/python" - "$TOKEN_FILE" "$DOMAIN" > "$APP_DIR/.env" <<'PY'
import secrets
import sys

from cryptography.fernet import Fernet

token = open(sys.argv[1], encoding="utf-8").read().strip()
print(f"SECRET_KEY={secrets.token_urlsafe(32)}")
print(f"USER_HASH_SALT={secrets.token_urlsafe(32)}")
print(f"BOT_API_TOKEN={secrets.token_urlsafe(32)}")
print(f"DELIVERY_KEY={Fernet.generate_key().decode()}")
print(f"TELEGRAM_BOT_TOKEN={token}")
print("API_BASE_URL=http://127.0.0.1:8000")
print("DATABASE_URL=sqlite:////opt/talababot/var/talababot.db")
print("BACKUP_DIR=/opt/talababot/var/backups")
print("COOKIE_SECURE=true")
print("TEST_MODE=true")
PY
  )
fi
rm -f "$TOKEN_FILE"
chown -R root:root "$APP_DIR"
chown -R talababot:talababot "$APP_DIR/var"
chown talababot:talababot "$APP_DIR/.env"
chmod 600 "$APP_DIR/.env"

install -m 644 "$APP_DIR"/deploy/talababot-*.service "$APP_DIR"/deploy/talababot-backup.timer /etc/systemd/system/
install -m 644 "$APP_DIR/deploy/talababot-proxy.conf" /etc/nginx/snippets/talababot-proxy.conf

# Sertifikat olingach certbot sayt faylini o'zi o'zgartiradi, uni qayta yozmaymiz.
if [[ ! -d "/etc/letsencrypt/live/$DOMAIN" ]]; then
  sed "s/__DOMAIN__/$DOMAIN/g" "$APP_DIR/deploy/nginx.conf.template" > "$SITE"
  ln -sf "$SITE" /etc/nginx/sites-enabled/talababot
  rm -f /etc/nginx/sites-enabled/default
fi
nginx -t
systemctl reload-or-restart nginx

ufw allow OpenSSH
ufw allow "Nginx Full"
ufw --force enable

if [[ ! -d "/etc/letsencrypt/live/$DOMAIN" ]]; then
  certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos -m "$EMAIL" --redirect
fi

systemctl daemon-reload
systemctl enable talababot-web talababot-bot talababot-backup.timer
systemctl restart talababot-web
systemctl restart talababot-bot
systemctl start talababot-backup.timer

sleep 3
systemctl --no-pager --lines=0 status talababot-web talababot-bot
curl -fsS -o /dev/null "https://$DOMAIN/" && echo "HTTPS ishlayapti: https://$DOMAIN/"
echo "Admin yaratish: cd $APP_DIR && sudo -u talababot .venv/bin/python -m app.manage create-staff admin admin"
