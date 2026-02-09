#!/bin/bash

APP_DIR=$(pwd)
echo "Starting AO-Celery in ${APP_DIR}"

# Load .env if it exists
if [[ -f "${APP_DIR}/.env" ]]; then
  echo "Loading environment variables from .env"
  source "${APP_DIR}/.env"
fi

# Optional: pull code from GitHub if needed
if [[ "${TA_GITHUB}" == "true" ]]; then
  WORK_DIR=$(mktemp -d)
  echo "Cloning ${TA_GH_ORG}/${TA_GH_REPO} branch ${TA_GH_BRANCH}"
  git clone --no-checkout --depth=1 --branch=${TA_GH_BRANCH} https://oauth2:${TA_GH_TOKEN}@github.com/${TA_GH_ORG}/${TA_GH_REPO}.git ${WORK_DIR}
  cp -r ${WORK_DIR}/${TA_AO_NAME} ${APP_DIR}/conf
  rm -rf ${WORK_DIR}
fi

# Run Celery worker
echo "Running Celery worker for ${TA_AO_NAME}"
cd "${APP_DIR}" || exit

# Replace `celery_app.celery` with your actual Celery app path
uv run -- celery -A content_update.celery_app.celery_app worker -l info

