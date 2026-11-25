#!/bin/bash
# PyPI trusted publishing: exchanges the OIDC token of the GitHub job for a short-lived PyPI API token and prints it.
# The job needs `permissions: id-token: write`.
# Usage: pypi_oidc_token.sh <repository_domain>, as pypi.org or test.pypi.org

set -euo pipefail

REPOSITORY_DOMAIN="${1:?Usage: $0 <repository_domain>}"

# Prints the body of a response, fails with the body when the status is not 200.
request() {
  local response code body
  response=$(curl -sS -w '\n%{http_code}' "$@")
  code=$(echo "$response" | tail -n1)
  body=$(echo "$response" | sed '$d')
  if [ "$code" != "200" ]; then
    echo "::error::HTTP $code from ${*: -1}: ${body:-<empty>}" >&2
    return 1
  fi
  echo "$body"
}

audience=$(request "https://${REPOSITORY_DOMAIN}/_/oidc/audience" | jq -r '.audience // empty')
if [ -z "$audience" ]; then
  echo "::error::No OIDC audience from ${REPOSITORY_DOMAIN}" >&2
  exit 1
fi

oidc_token=$(request -H "Authorization: bearer $ACTIONS_ID_TOKEN_REQUEST_TOKEN" \
  "${ACTIONS_ID_TOKEN_REQUEST_URL}&audience=${audience}" | jq -r '.value // empty')
if [ -z "$oidc_token" ]; then
  echo "::error::No OIDC token from GitHub Actions, check the id-token: write permission" >&2
  exit 1
fi
echo "::add-mask::$oidc_token" >&2

# A failure here usually means the trusted publisher on PyPI does not match: owner, repository, workflow file or environment.
pypi_token=$(request -X POST -H 'Content-Type: application/json' \
  -d "$(jq -n --arg token "$oidc_token" '{token: $token}')" \
  "https://${REPOSITORY_DOMAIN}/_/oidc/mint-token" | jq -r '.token // empty')
if [ -z "$pypi_token" ]; then
  echo "::error::No API token from ${REPOSITORY_DOMAIN}" >&2
  exit 1
fi
echo "::add-mask::$pypi_token" >&2

echo "$pypi_token"
