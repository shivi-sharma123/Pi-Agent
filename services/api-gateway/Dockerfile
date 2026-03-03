FROM nginx:1.25-alpine

# Copy custom nginx config
COPY nginx.conf /etc/nginx/nginx.conf

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=5s --start-period=5s --retries=3 \
    CMD wget -q -O- http://localhost:8000/health || exit 1
