#!/bin/bash

# Define the application directory for configuration and .env file
APP_DIR=$(pwd)
CONF_DIR=${APP_DIR}/conf

echo "Loading .env file from ${APP_DIR}/.env"
# Source the .env file if it exists to load environment variables
if [[ -f ".env" ]]; then
  source "${APP_DIR}/.env"
fi
if [ "${TA_GITHUB}" == "true" ]; then
  WORK_DIR=$(mktemp -d)
  echo "Creating temp dir ${WORK_DIR}"
  cd ${WORK_DIR} || exit
  echo "Cloning ${TA_GH_ORG}/${TA_GH_REPO}#${TA_GH_BRANCH} to ${WORK_DIR}"
  git clone --no-checkout --depth=1 --branch=${TA_GH_BRANCH} https://oauth2:${TA_GH_TOKEN}@github.com/${TA_GH_ORG}/${TA_GH_REPO}.git
  cd ${TA_GH_REPO} || exit
  echo "Checking out ${TA_GH_BRANCH} to ${WORK_DIR}"
  git checkout ${TA_GH_BRANCH} -- ${TA_AO_NAME}

  echo "Copying contents of ${TA_AO_NAME} to ${CONF_DIR}"
  cd ${TA_AO_NAME} || exit
  cp -r . ${CONF_DIR}
  cd ${CONF_DIR} || exit
  echo "Removing temp dir ${WORK_DIR}"
  rm -rf ${WORK_DIR}
fi

echo "Starting Collab Orchestrator"
cd "${APP_DIR}" || exit

# Run the FastAPI application using uv run.
uv run -- fastapi run src/collab_orchestrator/app.py --port 8000