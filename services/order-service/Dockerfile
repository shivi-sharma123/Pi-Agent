FROM golang:1.22-alpine AS builder

# Install build dependencies
RUN apk add --no-cache git

WORKDIR /app

# Copy dependency files and download modules (cached layer)
COPY go.mod go.sum* ./
RUN go mod download

# Copy source and build static binary
COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -o /order-service .

# ---------------------------------------------------------------------------
# Final minimal image
# ---------------------------------------------------------------------------
FROM alpine:3.19

RUN apk add --no-cache curl ca-certificates

COPY --from=builder /order-service /order-service

EXPOSE 8002

HEALTHCHECK --interval=10s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8002/health || exit 1

ENTRYPOINT ["/order-service"]
