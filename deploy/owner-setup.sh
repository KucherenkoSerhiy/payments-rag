#!/usr/bin/env bash
# One-shot owner setup for the cloud deploy: seeds Neon and sets Fly secrets.
# Run from anywhere in the repo, in Git Bash:
#
#     ./deploy/owner-setup.sh
#
# It prompts for the Neon connection string and the two API keys, so nothing
# secret is typed into a chat, a command line, or shell history. Contains no
# secrets itself. Prerequisites: docker running (local DB with the indexed
# chunks), flyctl installed and logged in (flyctl auth login).

set -euo pipefail
cd "$(dirname "$0")/.."

# flyctl may not be on Git Bash's PATH right after install; fall back to the
# installer's default location.
FLY="flyctl"
if ! command -v flyctl >/dev/null 2>&1; then
  FLY="$USERPROFILE/.fly/bin/flyctl.exe"
  [ -x "$FLY" ] || { echo "flyctl not found; install it first" >&2; exit 1; }
fi

echo "== payments-rag cloud setup =="
echo
echo "Paste the DIRECT Neon connection string (postgresql://...sslmode=require)."
read -r -p "NEON_URL: " NEON_URL
case "$NEON_URL" in
  postgresql://*|postgres://*) ;;
  *) echo "that does not look like a Postgres URL, aborting" >&2; exit 1 ;;
esac
case "$NEON_URL" in
  *sslmode=*) ;;
  *) echo "note: no sslmode in the URL; Neon usually needs ?sslmode=require" ;;
esac

echo
echo "-- applying schema to Neon..."
./deploy/seed-neon.sh schema "$NEON_URL"
echo "-- copying chunks from the local DB..."
./deploy/seed-neon.sh copy "$NEON_URL"
echo "-- verifying..."
./deploy/seed-neon.sh verify "$NEON_URL"

echo
read -r -p "Fly app name [payments-rag]: " APP
APP="${APP:-payments-rag}"
if ! "$FLY" status -a "$APP" >/dev/null 2>&1; then
  echo "-- creating Fly app $APP..."
  "$FLY" apps create "$APP"
else
  echo "-- Fly app $APP already exists, reusing it"
fi
if [ "$APP" != "payments-rag" ]; then
  sed -i "s/^app = .*/app = \"$APP\"/" deploy/fly.toml
  echo "-- updated deploy/fly.toml app name to $APP (commit this change)"
fi

echo
echo "API keys are read hidden (nothing is echoed)."
read -r -s -p "ANTHROPIC_API_KEY: " ANTHROPIC_KEY; echo
read -r -s -p "OPENAI_API_KEY: " OPENAI_KEY; echo
[ -n "$ANTHROPIC_KEY" ] && [ -n "$OPENAI_KEY" ] || { echo "empty key, aborting" >&2; exit 1; }

echo "-- setting Fly secrets..."
"$FLY" secrets set -a "$APP" --stage \
    ANTHROPIC_API_KEY="$ANTHROPIC_KEY" \
    OPENAI_API_KEY="$OPENAI_KEY" \
    DATABASE_URL="$NEON_URL"

echo
echo "== done. Secrets are staged (applied on first deploy). =="
echo "Next: tell your assistant 'done' and it will deploy and verify."
