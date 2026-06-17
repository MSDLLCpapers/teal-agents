ARG NODE_VERSION=18

FROM node:${NODE_VERSION}-alpine

RUN npm i -g dynamodb-admin

CMD dynamodb-admin --port=8000 --dynamo-endpoint=http://dynamodb:8000