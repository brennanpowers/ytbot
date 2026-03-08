#!/usr/bin/env bash
set -euo pipefail

# Load .env if present
if [[ -f .env ]]; then
  source .env
fi

: "${YOUTUBE_CLIENT_ID:?Set YOUTUBE_CLIENT_ID in .env or environment}"
: "${YOUTUBE_CLIENT_SECRET:?Set YOUTUBE_CLIENT_SECRET in .env or environment}"

REDIRECT_URI="http://localhost:8090"
SCOPE="https://www.googleapis.com/auth/youtube"

AUTH_URL="https://accounts.google.com/o/oauth2/v2/auth?\
client_id=${YOUTUBE_CLIENT_ID}&\
redirect_uri=${REDIRECT_URI}&\
response_type=code&\
scope=${SCOPE}&\
access_type=offline&\
prompt=consent"

echo ""
echo "Open this URL in your browser:"
echo ""
echo "$AUTH_URL"
echo ""
echo "After granting access, paste the full redirect URL from your browser's address bar:"
read -rp "> " REDIRECT_RESPONSE

# Extract the authorization code from the redirect URL
CODE=$(echo "$REDIRECT_RESPONSE" | sed -n 's/.*code=\([^&]*\).*/\1/p')

if [[ -z "$CODE" ]]; then
  echo "ERROR: Could not extract authorization code from URL."
  exit 1
fi

# Exchange the code for tokens
RESPONSE=$(curl -s -X POST https://oauth2.googleapis.com/token \
  -d "code=${CODE}" \
  -d "client_id=${YOUTUBE_CLIENT_ID}" \
  -d "client_secret=${YOUTUBE_CLIENT_SECRET}" \
  -d "redirect_uri=${REDIRECT_URI}" \
  -d "grant_type=authorization_code")

REFRESH_TOKEN=$(echo "$RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('refresh_token',''))" 2>/dev/null)

if [[ -n "$REFRESH_TOKEN" ]]; then
  echo ""
  echo "YOUTUBE_REFRESH_TOKEN=${REFRESH_TOKEN}"
  echo ""
  echo "Add this to your .env file."
else
  echo ""
  echo "ERROR: No refresh token in response:"
  echo "$RESPONSE"
fi
