// Inventory Worker — Go NATS consumer for stock management.
//
// Subscribes:
//   orders.created   → reserve stock (decrement inventory)
// Publishes:
//   inventory.low    → when stock < LOW_STOCK_THRESHOLD
//
// HTTP endpoints:
//   GET /health    → liveness probe
//   GET /metrics   → Prometheus metrics

package main

import (
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"strconv"
	"time"

	_ "github.com/lib/pq"
	"github.com/nats-io/nats.go"
	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promhttp"
)

// ---------------------------------------------------------------------------
// Config
// ---------------------------------------------------------------------------

var (
	natsURL           = getenv("NATS_URL", "nats://localhost:4222")
	dbURL             = getenv("DATABASE_URL", "postgres://postgres:postgres@localhost:5435/inventory?sslmode=disable")
	httpPort          = getenv("PORT", "8008")
	lowStockThreshold = getenvInt("LOW_STOCK_THRESHOLD", 10)
)

func getenv(key, def string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return def
}

func getenvInt(key string, def int) int {
	if v := os.Getenv(key); v != "" {
		if n, err := strconv.Atoi(v); err == nil {
			return n
		}
	}
	return def
}

// ---------------------------------------------------------------------------
// Prometheus metrics
// ---------------------------------------------------------------------------

var (
	stockReservations = prometheus.NewCounterVec(prometheus.CounterOpts{
		Name: "inventory_stock_reservations_total",
		Help: "Total stock reservation attempts",
	}, []string{"status"}) // status: success | insufficient | error

	lowStockAlerts = prometheus.NewCounter(prometheus.CounterOpts{
		Name: "inventory_low_stock_alerts_total",
		Help: "Total low stock alerts published",
	})

	natsMessages = prometheus.NewCounterVec(prometheus.CounterOpts{
		Name: "inventory_nats_messages_total",
		Help: "Total NATS messages processed",
	}, []string{"subject"})
)

func init() {
	prometheus.MustRegister(stockReservations, lowStockAlerts, natsMessages)
}

// ---------------------------------------------------------------------------
// Database
// ---------------------------------------------------------------------------

// bootstrapSchema creates the inventory table if it doesn't exist.
func bootstrapSchema(db *sql.DB) error {
	_, err := db.Exec(`
		CREATE TABLE IF NOT EXISTS inventory (
			product_id  TEXT PRIMARY KEY,
			sku         TEXT NOT NULL DEFAULT '',
			stock       INTEGER NOT NULL DEFAULT 0,
			reserved    INTEGER NOT NULL DEFAULT 0,
			updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
		);
		-- Seed some demo products if table is empty
		INSERT INTO inventory (product_id, sku, stock)
		SELECT 'demo-product-1', 'SKU-001', 100
		WHERE NOT EXISTS (SELECT 1 FROM inventory WHERE product_id = 'demo-product-1');
	`)
	return err
}

// reserveStock decrements stock for each item in the order.
// Returns ErrInsufficientStock if stock is not available.
func reserveStock(ctx context.Context, db *sql.DB, items []OrderItem) error {
	tx, err := db.BeginTx(ctx, nil)
	if err != nil {
		return fmt.Errorf("begin tx: %w", err)
	}
	defer tx.Rollback()

	for _, item := range items {
		var stock int
		err := tx.QueryRowContext(ctx,
			`SELECT stock FROM inventory WHERE product_id=$1 FOR UPDATE`,
			item.ProductID,
		).Scan(&stock)
		if err == sql.ErrNoRows {
			// Product not tracked — skip (graceful degradation)
			log.Printf("INFO: product %s not in inventory; skipping reservation", item.ProductID)
			continue
		}
		if err != nil {
			return fmt.Errorf("query stock for %s: %w", item.ProductID, err)
		}
		if stock < item.Quantity {
			stockReservations.WithLabelValues("insufficient").Inc()
			return fmt.Errorf("insufficient stock for product %s (have %d, need %d)",
				item.ProductID, stock, item.Quantity)
		}
		_, err = tx.ExecContext(ctx,
			`UPDATE inventory SET stock=stock-$1, reserved=reserved+$1, updated_at=NOW() WHERE product_id=$2`,
			item.Quantity, item.ProductID,
		)
		if err != nil {
			return fmt.Errorf("update stock for %s: %w", item.ProductID, err)
		}
	}
	return tx.Commit()
}

// checkLowStock publishes inventory.low for every product below threshold.
func checkLowStock(ctx context.Context, db *sql.DB, js nats.JetStreamContext) {
	rows, err := db.QueryContext(ctx,
		`SELECT product_id, sku, stock FROM inventory WHERE stock < $1`,
		lowStockThreshold,
	)
	if err != nil {
		log.Printf("WARN: checkLowStock query: %v", err)
		return
	}
	defer rows.Close()

	for rows.Next() {
		var pid, sku string
		var stock int
		if err := rows.Scan(&pid, &sku, &stock); err != nil {
			continue
		}
		alert := map[string]interface{}{
			"product_id": pid,
			"sku":        sku,
			"stock":      stock,
			"threshold":  lowStockThreshold,
			"timestamp":  time.Now().UTC().Format(time.RFC3339),
		}
		data, _ := json.Marshal(alert)
		if _, err := js.Publish("inventory.low", data); err != nil {
			log.Printf("WARN: publish inventory.low: %v", err)
		} else {
			log.Printf("INFO: Low stock alert: product=%s stock=%d", pid, stock)
			lowStockAlerts.Inc()
		}
	}
}

// ---------------------------------------------------------------------------
// NATS event types
// ---------------------------------------------------------------------------

type OrderItem struct {
	ProductID string `json:"product_id"`
	SKU       string `json:"sku"`
	Quantity  int    `json:"quantity"`
}

type OrderCreatedEvent struct {
	ID     string      `json:"id"`
	UserID string      `json:"user_id"`
	Items  []OrderItem `json:"items"`
	Total  float64     `json:"total"`
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

func main() {
	log.Printf("Inventory worker starting. NATS=%s DB=%s port=%s", natsURL, dbURL, httpPort)

	// --- Connect to PostgreSQL ---
	db, err := sql.Open("postgres", dbURL)
	if err != nil {
		log.Fatalf("DB open: %v", err)
	}
	db.SetMaxOpenConns(10)
	db.SetConnMaxLifetime(5 * time.Minute)

	// Retry DB connection (service may start before PG is ready)
	for i := 0; i < 30; i++ {
		if err := db.Ping(); err == nil {
			break
		}
		log.Printf("Waiting for DB... (%d/30)", i+1)
		time.Sleep(2 * time.Second)
	}
	if err := bootstrapSchema(db); err != nil {
		log.Fatalf("Schema bootstrap: %v", err)
	}
	log.Println("Database ready")

	// --- Connect to NATS ---
	nc, err := nats.Connect(natsURL,
		nats.MaxReconnects(-1),
		nats.ReconnectWait(2*time.Second),
	)
	if err != nil {
		log.Fatalf("NATS connect: %v", err)
	}
	defer nc.Drain()
	js, err := nc.JetStream()
	if err != nil {
		log.Fatalf("JetStream context: %v", err)
	}
	log.Println("NATS JetStream ready")

	// --- Subscribe: orders.created ---
	_, err = js.QueueSubscribe("orders.created", "inventory-workers", func(msg *nats.Msg) {
		natsMessages.WithLabelValues("orders.created").Inc()
		var event OrderCreatedEvent
		if err := json.Unmarshal(msg.Data, &event); err != nil {
			log.Printf("WARN: malformed orders.created payload: %v", err)
			msg.Nak()
			return
		}
		ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer cancel()

		if err := reserveStock(ctx, db, event.Items); err != nil {
			log.Printf("WARN: reserveStock for order %s: %v", event.ID, err)
			stockReservations.WithLabelValues("error").Inc()
			msg.Nak()
			return
		}
		stockReservations.WithLabelValues("success").Inc()
		msg.Ack()

		// Check for any products that are now low on stock
		checkLowStock(ctx, db, js)
	}, nats.Durable("inventory-orders-created"), nats.AckExplicit(), nats.MaxDeliver(3))
	if err != nil {
		// Fall back to core NATS if JetStream stream not created yet
		log.Printf("WARN: JetStream subscribe failed (%v); falling back to core NATS", err)
		nc.Subscribe("orders.created", func(msg *nats.Msg) {
			natsMessages.WithLabelValues("orders.created").Inc()
			log.Printf("orders.created (core): %s", string(msg.Data))
		})
	}

	// --- HTTP server ---
	mux := http.NewServeMux()
	mux.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
		dbOK := db.Ping() == nil
		status := "healthy"
		code := http.StatusOK
		if !dbOK {
			status = "degraded"
			code = http.StatusServiceUnavailable
		}
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(code)
		fmt.Fprintf(w, `{"status":%q,"service":"inventory-worker","version":"0.2.0","dependencies":{"postgres":%q}}`,
			status, map[bool]string{true: "ok", false: "down"}[dbOK])
	})
	mux.Handle("/metrics", promhttp.Handler())

	srv := &http.Server{
		Addr:         ":" + httpPort,
		Handler:      mux,
		ReadTimeout:  5 * time.Second,
		WriteTimeout: 5 * time.Second,
	}
	log.Printf("HTTP server listening on :%s", httpPort)
	if err := srv.ListenAndServe(); err != nil {
		log.Fatalf("HTTP server: %v", err)
	}
}
