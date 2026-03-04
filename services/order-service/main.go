// Order Service — Go/Gin application
//
// Handles order creation, status transitions, and publishes domain events
// to NATS JetStream when orders are created.
//
// Endpoints:
//   GET  /health              → liveness + DB check
//   POST /orders              → create a new order
//   GET  /orders/:id          → get order by ID
//   PUT  /orders/:id/status   → update order status
//   GET  /orders?user_id=     → list orders for a user
//
// NATS events published:
//   orders.created  → payload: { order_id, user_id, items, total }

package main

import (
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/google/uuid"
	_ "github.com/lib/pq"
	"github.com/nats-io/nats.go"
	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promhttp"
)

// Ensure promhttp is used (metrics endpoint).
var _ = promhttp.Handler

// ---------------------------------------------------------------------------
// Config
// ---------------------------------------------------------------------------

type Config struct {
	Port     string
	DBConn   string
	NATSConn string
}

func loadConfig() Config {
	return Config{
		Port:     getEnv("PORT", "8002"),
		DBConn:   getEnv("DATABASE_URL", "postgres://postgres:postgres@localhost:5433/orders?sslmode=disable"),
		NATSConn: getEnv("NATS_URL", "nats://localhost:4222"),
	}
}

func getEnv(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}

// ---------------------------------------------------------------------------
// Domain types
// ---------------------------------------------------------------------------

// OrderStatus represents the possible states of an order (state machine).
type OrderStatus string

const (
	StatusPending    OrderStatus = "pending"
	StatusConfirmed  OrderStatus = "confirmed"
	StatusProcessing OrderStatus = "processing"
	StatusShipped    OrderStatus = "shipped"
	StatusDelivered  OrderStatus = "delivered"
	StatusCancelled  OrderStatus = "cancelled"
	StatusRefunded   OrderStatus = "refunded"
)

// validTransitions defines which status transitions are allowed.
var validTransitions = map[OrderStatus][]OrderStatus{
	StatusPending:    {StatusConfirmed, StatusCancelled},
	StatusConfirmed:  {StatusProcessing, StatusCancelled},
	StatusProcessing: {StatusShipped, StatusCancelled},
	StatusShipped:    {StatusDelivered},
	StatusDelivered:  {StatusRefunded},
}

type OrderItem struct {
	ProductID string  `json:"product_id"`
	Quantity  int     `json:"quantity"`
	UnitPrice float64 `json:"unit_price"`
}

type Order struct {
	ID        string      `json:"id"`
	UserID    string      `json:"user_id"`
	Status    OrderStatus `json:"status"`
	Items     []OrderItem `json:"items"`
	Total     float64     `json:"total"`
	CreatedAt time.Time   `json:"created_at"`
	UpdatedAt time.Time   `json:"updated_at"`
}

// ---------------------------------------------------------------------------
// Prometheus metrics
// ---------------------------------------------------------------------------

var (
	httpRequestsTotal = prometheus.NewCounterVec(
		prometheus.CounterOpts{Name: "http_requests_total", Help: "Total HTTP requests"},
		[]string{"method", "route", "status_code"},
	)
	httpRequestDuration = prometheus.NewHistogramVec(
		prometheus.HistogramOpts{Name: "http_request_duration_seconds", Help: "Request latency"},
		[]string{"method", "route"},
	)
	ordersCreatedTotal = prometheus.NewCounter(
		prometheus.CounterOpts{Name: "orders_created_total", Help: "Total orders created"},
	)
)

func init() {
	prometheus.MustRegister(httpRequestsTotal, httpRequestDuration, ordersCreatedTotal)
}

// ---------------------------------------------------------------------------
// Server
// ---------------------------------------------------------------------------

type Server struct {
	db  *sql.DB
	nc  *nats.Conn
	cfg Config
}

func NewServer(cfg Config) (*Server, error) {
	// Connect to PostgreSQL
	db, err := sql.Open("postgres", cfg.DBConn)
	if err != nil {
		return nil, fmt.Errorf("db open: %w", err)
	}
	db.SetMaxOpenConns(20)
	db.SetMaxIdleConns(5)
	db.SetConnMaxLifetime(time.Minute * 5)

	// Verify connection
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	if err := db.PingContext(ctx); err != nil {
		return nil, fmt.Errorf("db ping: %w", err)
	}

	// Bootstrap schema if not exists
	if err := bootstrapSchema(db); err != nil {
		return nil, fmt.Errorf("schema init: %w", err)
	}

	// Connect to NATS
	nc, err := nats.Connect(cfg.NATSConn,
		nats.MaxReconnects(10),
		nats.ReconnectWait(2*time.Second),
	)
	if err != nil {
		// NATS failure is non-fatal for Phase 1 — log warning and continue
		log.Printf("WARN: NATS connection failed: %v — running without event publishing", err)
		nc = nil
	}

	return &Server{db: db, nc: nc, cfg: cfg}, nil
}

func bootstrapSchema(db *sql.DB) error {
	_, err := db.Exec(`
		CREATE TABLE IF NOT EXISTS orders (
			id         TEXT PRIMARY KEY,
			user_id    TEXT NOT NULL,
			status     TEXT NOT NULL DEFAULT 'pending',
			items      JSONB NOT NULL DEFAULT '[]',
			total      NUMERIC(12, 2) NOT NULL DEFAULT 0,
			created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
			updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
		);
		CREATE INDEX IF NOT EXISTS idx_orders_user_id ON orders(user_id);
	`)
	return err
}

// ---------------------------------------------------------------------------
// Route handlers
// ---------------------------------------------------------------------------

func (s *Server) health(c *gin.Context) {
	ctx, cancel := context.WithTimeout(c.Request.Context(), 2*time.Second)
	defer cancel()

	dbOK := s.db.PingContext(ctx) == nil
	natsOK := s.nc != nil && s.nc.IsConnected()

	status := "healthy"
	code := http.StatusOK
	if !dbOK {
		status = "degraded"
		code = http.StatusServiceUnavailable
	}

	c.JSON(code, gin.H{
		"status":  status,
		"service": "order-svc",
		"version": "0.1.0",
		"dependencies": gin.H{
			"postgres": map[bool]string{true: "ok", false: "down"}[dbOK],
			"nats":     map[bool]string{true: "ok", false: "down"}[natsOK],
		},
	})
}

type CreateOrderRequest struct {
	UserID string      `json:"user_id" binding:"required"`
	Items  []OrderItem `json:"items" binding:"required,min=1"`
}

func (s *Server) createOrder(c *gin.Context) {
	var req CreateOrderRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	// Calculate total
	var total float64
	for _, item := range req.Items {
		total += float64(item.Quantity) * item.UnitPrice
	}

	order := Order{
		ID:        uuid.New().String(),
		UserID:    req.UserID,
		Status:    StatusPending,
		Items:     req.Items,
		Total:     total,
		CreatedAt: time.Now().UTC(),
		UpdatedAt: time.Now().UTC(),
	}

	itemsJSON, _ := json.Marshal(order.Items)

	_, err := s.db.ExecContext(c.Request.Context(),
		`INSERT INTO orders (id, user_id, status, items, total, created_at, updated_at)
		 VALUES ($1, $2, $3, $4, $5, $6, $7)`,
		order.ID, order.UserID, string(order.Status), itemsJSON, order.Total, order.CreatedAt, order.UpdatedAt,
	)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to create order"})
		return
	}

	// Publish NATS event (best-effort)
	s.publishOrderCreated(order)
	ordersCreatedTotal.Inc()

	c.JSON(http.StatusCreated, order)
}

func (s *Server) getOrder(c *gin.Context) {
	id := c.Param("id")
	order, err := s.fetchOrder(c.Request.Context(), id)
	if err == sql.ErrNoRows {
		c.JSON(http.StatusNotFound, gin.H{"error": "Order not found"})
		return
	}
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, order)
}

func (s *Server) updateOrderStatus(c *gin.Context) {
	id := c.Param("id")
	var body struct {
		Status OrderStatus `json:"status" binding:"required"`
	}
	if err := c.ShouldBindJSON(&body); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	order, err := s.fetchOrder(c.Request.Context(), id)
	if err == sql.ErrNoRows {
		c.JSON(http.StatusNotFound, gin.H{"error": "Order not found"})
		return
	}
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	// Validate state transition
	allowed := validTransitions[order.Status]
	valid := false
	for _, s := range allowed {
		if s == body.Status {
			valid = true
			break
		}
	}
	if !valid {
		c.JSON(http.StatusBadRequest, gin.H{
			"error": fmt.Sprintf("Invalid transition from '%s' to '%s'", order.Status, body.Status),
		})
		return
	}

	_, err = s.db.ExecContext(c.Request.Context(),
		`UPDATE orders SET status=$1, updated_at=NOW() WHERE id=$2`,
		string(body.Status), id,
	)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to update order"})
		return
	}

	order.Status = body.Status
	c.JSON(http.StatusOK, order)
}

func (s *Server) listOrders(c *gin.Context) {
	userID := c.Query("user_id")
	query := `SELECT id, user_id, status, items, total, created_at, updated_at FROM orders`
	args := []any{}
	if userID != "" {
		query += ` WHERE user_id=$1`
		args = append(args, userID)
	}
	query += ` ORDER BY created_at DESC LIMIT 50`

	rows, err := s.db.QueryContext(c.Request.Context(), query, args...)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	defer rows.Close()

	orders := []Order{}
	for rows.Next() {
		var o Order
		var itemsJSON []byte
		if err := rows.Scan(&o.ID, &o.UserID, &o.Status, &itemsJSON, &o.Total, &o.CreatedAt, &o.UpdatedAt); err != nil {
			log.Printf("WARN: failed to scan order row: %v", err)
			continue
		}
		if err := json.Unmarshal(itemsJSON, &o.Items); err != nil {
			log.Printf("WARN: malformed items JSON for order %s: %v", o.ID, err)
			o.Items = []OrderItem{} // return empty slice rather than nil
		}
		orders = append(orders, o)
	}
	if err := rows.Err(); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Error iterating orders"})
		return
	}
	c.JSON(http.StatusOK, orders)
}

func (s *Server) fetchOrder(ctx context.Context, id string) (*Order, error) {
	row := s.db.QueryRowContext(ctx,
		`SELECT id, user_id, status, items, total, created_at, updated_at FROM orders WHERE id=$1`, id,
	)
	var o Order
	var itemsJSON []byte
	if err := row.Scan(&o.ID, &o.UserID, &o.Status, &itemsJSON, &o.Total, &o.CreatedAt, &o.UpdatedAt); err != nil {
		return nil, err
	}
	if err := json.Unmarshal(itemsJSON, &o.Items); err != nil {
		log.Printf("WARN: malformed items JSON for order %s: %v", id, err)
		o.Items = []OrderItem{}
	}
	return &o, nil
}

func (s *Server) publishOrderCreated(order Order) {
	if s.nc == nil {
		return
	}
	js, err := s.nc.JetStream()
	if err != nil {
		log.Printf("WARN: JetStream unavailable: %v", err)
		return
	}
	payload, _ := json.Marshal(map[string]any{
		"order_id": order.ID,
		"user_id":  order.UserID,
		"items":    order.Items,
		"total":    order.Total,
	})
	if _, err := js.Publish("orders.created", payload); err != nil {
		log.Printf("WARN: Failed to publish orders.created: %v", err)
	}
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

func main() {
	cfg := loadConfig()

	srv, err := NewServer(cfg)
	if err != nil {
		log.Fatalf("Failed to initialise server: %v", err)
	}

	gin.SetMode(gin.ReleaseMode)
	r := gin.New()
	r.Use(gin.Recovery())

	// Prometheus duration + count middleware
	r.Use(func(c *gin.Context) {
		start := time.Now()
		c.Next()
		elapsed := time.Since(start).Seconds()
		route := c.FullPath()
		if route == "" {
			route = c.Request.URL.Path
		}
		httpRequestDuration.WithLabelValues(c.Request.Method, route).Observe(elapsed)
		httpRequestsTotal.WithLabelValues(c.Request.Method, route, fmt.Sprintf("%d", c.Writer.Status())).Inc()
	})

	r.GET("/health", srv.health)
	r.GET("/metrics", gin.WrapH(promhttp.Handler()))
	r.POST("/orders", srv.createOrder)
	r.GET("/orders", srv.listOrders)
	r.GET("/orders/:id", srv.getOrder)
	r.PUT("/orders/:id/status", srv.updateOrderStatus)

	log.Printf("Order service starting on :%s", cfg.Port)
	if err := r.Run(":" + cfg.Port); err != nil {
		log.Fatalf("Server error: %v", err)
	}
}
