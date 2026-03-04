# Inventory Worker — Go multi-stage build
FROM golang:1.22-alpine AS builder

WORKDIR /build

RUN apk add --no-cache git

COPY go.mod go.sum ./
RUN go mod download

COPY main.go .
RUN CGO_ENABLED=0 GOOS=linux go build -ldflags="-s -w" -o inventory-worker .

# ─── Final image ───────────────────────────────────────────────────────────
FROM alpine:3.19

RUN apk add --no-cache ca-certificates curl

WORKDIR /app
COPY --from=builder /build/inventory-worker .

ENV PORT=8008

EXPOSE 8008

HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=5 \
  CMD curl -sf http://localhost:8008/health || exit 1

ENTRYPOINT ["./inventory-worker"]
