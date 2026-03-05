#!/bin/bash
# Setup OIDC token for PyPI trusted publishing
# Usage: setup_oidc_token.sh <repository_domain>
# Example: setup_oidc_token.sh pypi.org
#          setup_oidc_token.sh test.pypi.org

set -euo pipefail

REPOSITORY_DOMAIN="${1:-}"

if [ -z "$REPOSITORY_DOMAIN" ]; then
  echo "❌ Repository domain is required"
  echo "Usage: $0 <repository_domain>"
  exit 1
fi

# Step 1: Get audience from PyPI
echo "🔄 Getting OIDC audience from PyPI..."
AUDIENCE_URL="https://${REPOSITORY_DOMAIN}/_/oidc/audience"
AUDIENCE_RESPONSE=$(curl -sS -w "\n%{http_code}" "$AUDIENCE_URL")
HTTP_CODE=$(echo "$AUDIENCE_RESPONSE" | tail -n1)
AUDIENCE_RESPONSE=$(echo "$AUDIENCE_RESPONSE" | sed '$d')
if [ "$HTTP_CODE" != "200" ]; then
  echo "❌ Failed to get audience from PyPI (HTTP $HTTP_CODE). Response: ${AUDIENCE_RESPONSE:-<empty>}"
  exit 1
fi

OIDC_AUDIENCE=$(echo "$AUDIENCE_RESPONSE" | jq -r '.audience')
if [ -z "$OIDC_AUDIENCE" ] || [ "$OIDC_AUDIENCE" = "null" ]; then
  echo "❌ Invalid audience response: $AUDIENCE_RESPONSE"
  exit 1
fi

echo "✅ Got OIDC audience: $OIDC_AUDIENCE"

# Step 2: Get OIDC token from GitHub Actions with the correct audience
echo "🔄 Getting OIDC token from GitHub Actions..."
OIDC_RAW=$(curl -sS -w "\n%{http_code}" -H "Authorization: bearer $ACTIONS_ID_TOKEN_REQUEST_TOKEN" \
  "$ACTIONS_ID_TOKEN_REQUEST_URL&audience=$OIDC_AUDIENCE")
HTTP_CODE=$(echo "$OIDC_RAW" | tail -n1)
OIDC_JSON=$(echo "$OIDC_RAW" | sed '$d')
if [ "$HTTP_CODE" != "200" ]; then
  echo "❌ Failed to get OIDC token (HTTP $HTTP_CODE). Response: ${OIDC_JSON:-<empty>}"
  exit 1
fi
OIDC_TOKEN=$(echo "$OIDC_JSON" | jq -r '.value')

if [ -z "$OIDC_TOKEN" ] || [ "$OIDC_TOKEN" = "null" ]; then
  echo "❌ Invalid OIDC token response: $OIDC_JSON"
  exit 1
fi

echo "✅ OIDC token obtained (length: ${#OIDC_TOKEN})"

# Step 3: Set up token exchange URL
TOKEN_EXCHANGE_URL="https://${REPOSITORY_DOMAIN}/_/oidc/mint-token"

# Export for Python script
export OIDC_TOKEN
export TOKEN_EXCHANGE_URL

echo "✅ OIDC token setup complete"
