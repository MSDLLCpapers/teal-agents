#!/bin/bash
set -euo pipefail

APP_DIR=$(pwd)
CONF_DIR=${APP_DIR}/conf

echo "Loading .env file from ${APP_DIR}/.env"
if [[ -f "${APP_DIR}/.env" ]]; then
  source "${APP_DIR}/.env"
fi

if [[ "${TA_GITHUB:-false}" == "true" ]]; then
  WORK_DIR=$(mktemp -d)
  echo "Creating temp dir ${WORK_DIR}"

  cd "${WORK_DIR}" || exit
  echo "Cloning ${TA_GH_ORG}/${TA_GH_REPO}#${TA_GH_BRANCH}"
  git clone --no-checkout --depth=1 --branch="${TA_GH_BRANCH}" \
    "https://oauth2:${TA_GH_TOKEN}@github.com/${TA_GH_ORG}/${TA_GH_REPO}.git"

  cd "${TA_GH_REPO}" || exit
  git checkout "${TA_GH_BRANCH}" -- "${TA_AO_NAME}"

  echo "Copying contents of ${TA_AO_NAME} to ${CONF_DIR}"
  cd "${TA_AO_NAME}" || exit
  cp -r . "${CONF_DIR}"

  cd "${APP_DIR}" || exit
  rm -rf "${WORK_DIR}"
fi

echo "Starting FastAPI..."
uv run -- fastapi run jose.py --port 8000 &
FASTAPI_PID=$!

echo "Starting Celery..."
uv run -- celery -A content_update.celery_app.celery_app worker -l info &
CELERY_PID=$!

# Wait for any process to exit
wait -n

echo "One process exited. Shutting down..."

kill -TERM "$FASTAPI_PID" "$CELERY_PID" 2>/dev/null || true
wait

exit 1
