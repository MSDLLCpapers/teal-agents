#!/bin/bash

APP_DIR=$(pwd)
CONF_DIR=${APP_DIR}/conf
echo "Loading .env file from ${APP_DIR}/.env"
if [[ -f ".env" ]]; then
  source ${APP_DIR}/.env
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

echo "Running Assistant Orchestrator ${TA_AO_NAME}"
cd ${APP_DIR} || exit
uv run -- fastapi run jose.py --port 8000
#uv run -- uvicorn jose:app --reload --host 0.0.0.0 --port 8000 --log-level trace
