FROM node:18-alpine AS build

RUN mkdir -p /app && chown -R node:node /app

WORKDIR /app

# Copy the application files
COPY --chown=node:node . .

USER node

# Install dependencies
RUN npm i --legacy-peer-deps

# Run Build Script
RUN yarn run build

EXPOSE 3000

# CMD node server.js
CMD ["yarn", "start"]
