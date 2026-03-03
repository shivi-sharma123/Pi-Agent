FROM node:20-alpine

# System deps for native modules (none needed here, but good practice)
RUN apk add --no-cache curl

WORKDIR /app

# Install dependencies (cached layer)
COPY package.json .
RUN npm install --production

# Application source
COPY src/ ./src/

EXPOSE 8004

HEALTHCHECK --interval=10s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8004/health || exit 1

CMD ["node", "src/index.js"]
