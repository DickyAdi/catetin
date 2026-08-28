#!/usr/bin/env bash
# Test the CatetIn Telegram webhook end-to-end via a public tunnel URL.
#
# Usage:
#   ./scripts/test_webhook.sh <tunnel-url>      # set webhook + send a test ping
#   ./scripts/test_webhook.sh <tunnel-url> --check   # just show current webhook state
#   ./scripts/test_webhook.sh --remove          # delete the webhook (back to polling)
#
# The tunnel URL comes from `cloudflared tunnel --url http://localhost:8000`
# (the random https://xxx.trycloudflare.com it prints). This script reads
# CATETIN_TELEGRAM_BOT_TOKEN and CATETIN_TELEGRAM_WEBHOOK_SECRET from
# apps/api/.env automatically, so you never paste secrets by hand.
#
# Requires: curl, grep, cut. Works on macOS and Linux.

set -euo pipefail

ENV_FILE="apps/api/.env"
API_BASE="https://api.telegram.org"

die() {
    echo "❌ $*" >&2
    exit 1
}

# --- Load .env values -------------------------------------------------------

load_env() {
    if [[ ! -f "$ENV_FILE" ]]; then
        die "$ENV_FILE not found. Copy apps/api/.env.example to apps/api/.env first."
    fi
    TOKEN=$(grep -E '^CATETIN_TELEGRAM_BOT_TOKEN=' "$ENV_FILE" | head -1 | cut -d= -f2- | tr -d '"' | tr -d "'" || true)
    SECRET=$(grep -E '^CATETIN_TELEGRAM_WEBHOOK_SECRET=' "$ENV_FILE" | head -1 | cut -d= -f2- | tr -d '"' | tr -d "'" || true)

    [[ -z "$TOKEN" ]] && die "CATETIN_TELEGRAM_BOT_TOKEN is empty in $ENV_FILE"
    [[ -z "$SECRET" ]] && die "CATETIN_TELEGRAM_WEBHOOK_SECRET is empty in $ENV_FILE

Generate one with:  openssl rand -hex 32
Then add to $ENV_FILE:
    CATETIN_TELEGRAM_WEBHOOK_SECRET=<the-random-string>"
}

# --- Commands ---------------------------------------------------------------

cmd_set() {
    local tunnel_url="$1"
    [[ -z "$tunnel_url" ]] && die "missing tunnel URL. Usage: $0 <tunnel-url>"
    [[ "$tunnel_url" != https://* ]] && die "tunnel URL must start with https:// (got: $tunnel_url)"

    local webhook_url="${tunnel_url%/}/webhook/telegram/${SECRET}"
    echo "🔗 Setting webhook to: $webhook_url"
    curl -sS "$API_BASE/bot${TOKEN}/setWebhook?url=${webhook_url}" | python3 -m json.tool

    echo
    echo "✅ Webhook set. Send a message to your bot in Telegram — it should"
    echo "   hit your local FastAPI (make dev-api) through the tunnel."
    echo "   Check the API log for: POST /webhook/telegram/<secret> 200"
}

cmd_check() {
    echo "📡 Current webhook (from Telegram):"
    curl -sS "$API_BASE/bot${TOKEN}/getWebhookInfo" | python3 -m json.tool
}

cmd_remove() {
    echo "🧹 Deleting webhook (bot falls back to polling mode):"
    curl -sS "$API_BASE/bot${TOKEN}/deleteWebhook" | python3 -m json.tool
}

# --- Main -------------------------------------------------------------------

load_env

case "${1:-}" in
    --check)
        cmd_check
        ;;
    --remove)
        cmd_remove
        ;;
    *)
        cmd_set "${1:-}"
        ;;
esac
