/**
 * Auth Service — Express application.
 *
 * Provides JWT-based authentication with Redis for token blacklisting.
 *
 * Endpoints:
 *   GET  /health           → liveness + dependency check
 *   POST /auth/login       → authenticate and return JWT access + refresh tokens
 *   POST /auth/verify      → validate an access token
 *   POST /auth/refresh     → exchange refresh token for new access token
 *   POST /auth/logout      → blacklist the current access token
 */

"use strict";

const express = require("express");
const jwt = require("jsonwebtoken");
const bcrypt = require("bcrypt");
const { createClient } = require("redis");
const promClient = require("prom-client");

// Bcrypt work factor — 12 is a good balance of security vs. latency (~200ms)
const BCRYPT_ROUNDS = parseInt(process.env.BCRYPT_ROUNDS || "12", 10);

// ---------------------------------------------------------------------------
// Prometheus metrics
// ---------------------------------------------------------------------------
const register = new promClient.Registry();
promClient.collectDefaultMetrics({ register });

const httpRequestCount = new promClient.Counter({
  name: "http_requests_total",
  help: "Total HTTP requests",
  labelNames: ["method", "route", "status_code"],
  registers: [register],
});

const httpRequestDuration = new promClient.Histogram({
  name: "http_request_duration_seconds",
  help: "HTTP request latency",
  labelNames: ["method", "route"],
  registers: [register],
});

// ---------------------------------------------------------------------------
// Config from environment
// ---------------------------------------------------------------------------
const PORT = parseInt(process.env.PORT || "8004", 10);
const JWT_SECRET = process.env.JWT_SECRET || "dev-secret-change-in-prod";
const JWT_ACCESS_EXPIRY = process.env.JWT_ACCESS_EXPIRY || "15m";
const JWT_REFRESH_EXPIRY = process.env.JWT_REFRESH_EXPIRY || "7d";
const REDIS_URL = process.env.REDIS_URL || "redis://localhost:6379/1";
const USER_SVC_URL = process.env.USER_SVC_URL || "http://user-svc:8001";

// ---------------------------------------------------------------------------
// Redis client
// ---------------------------------------------------------------------------
let redisClient;

async function getRedis() {
  if (!redisClient) {
    redisClient = createClient({ url: REDIS_URL });
    redisClient.on("error", (err) => console.error("Redis error:", err));
    await redisClient.connect();
  }
  return redisClient;
}

// ---------------------------------------------------------------------------
// App setup
// ---------------------------------------------------------------------------
const app = express();
app.use(express.json());

// Timing middleware
app.use((req, res, next) => {
  const end = httpRequestDuration.startTimer({ method: req.method, route: req.path });
  res.on("finish", () => {
    end();
    httpRequestCount.inc({ method: req.method, route: req.path, status_code: res.statusCode });
  });
  next();
});

// ---------------------------------------------------------------------------
// Routes
// ---------------------------------------------------------------------------

/** Liveness + Redis connectivity probe. */
app.get("/health", async (req, res) => {
  let redisOk = false;
  try {
    const r = await getRedis();
    await r.ping();
    redisOk = true;
  } catch (_) {}

  const status = redisOk ? "healthy" : "degraded";
  res.status(redisOk ? 200 : 503).json({
    status,
    service: "auth-svc",
    version: "0.1.0",
    dependencies: { redis: redisOk ? "ok" : "down" },
  });
});

/** Prometheus metrics endpoint. */
app.get("/metrics", async (req, res) => {
  res.set("Content-Type", register.contentType);
  res.send(await register.metrics());
});

/**
 * POST /auth/login
 * Body: { email, password }
 * Returns: { access_token, refresh_token, user }
 *
 * NOTE: In Phase 1 we do a simplified credential check against a demo user
 * in Redis. In Phase 2+, this delegates to user-svc for lookup + bcrypt compare.
 */
app.post("/auth/login", async (req, res) => {
  const { email, password } = req.body;
  if (!email || !password) {
    return res.status(400).json({ error: "email and password are required" });
  }

  try {
    const r = await getRedis();

    // Look up user ID by email (stored by user-svc)
    const userId = await r.get(`user:email:${email}`);
    if (!userId) {
      // Use a constant-time fake compare to prevent timing attacks on user enumeration
      await bcrypt.compare(password, "$2b$12$invalidhashfortimingattackprevention");
      return res.status(401).json({ error: "Invalid credentials" });
    }

    const userDataRaw = await r.get(`user:${userId}`);
    if (!userDataRaw) {
      return res.status(401).json({ error: "User not found" });
    }
    const user = JSON.parse(userDataRaw);

    // Verify password using bcrypt.
    // If the user was created before password hashing was added (no password_hash field),
    // reject and ask them to reset. This prevents the old plaintext bypass.
    if (!user.password_hash) {
      return res.status(401).json({
        error: "Password reset required. Please re-register or use the reset endpoint.",
      });
    }
    const passwordMatch = await bcrypt.compare(password, user.password_hash);
    if (!passwordMatch) {
      return res.status(401).json({ error: "Invalid credentials" });
    }

    // Issue access + refresh tokens
    const accessToken = jwt.sign(
      { sub: userId, email: user.email, type: "access" },
      JWT_SECRET,
      { expiresIn: JWT_ACCESS_EXPIRY }
    );
    const refreshToken = jwt.sign(
      { sub: userId, email: user.email, type: "refresh" },
      JWT_SECRET,
      { expiresIn: JWT_REFRESH_EXPIRY }
    );

    // Store refresh token in Redis (7 days)
    await r.set(`refresh:${userId}`, refreshToken, { EX: 7 * 24 * 3600 });

    return res.json({
      access_token: accessToken,
      refresh_token: refreshToken,
      token_type: "bearer",
      user: { id: user.id, email: user.email, name: user.name },
    });
  } catch (err) {
    console.error("Login error:", err);
    return res.status(500).json({ error: "Internal server error" });
  }
});

/**
 * POST /auth/register
 * Body: { email, name, password }
 * Returns: { user_id, email }
 *
 * Hashes the password with bcrypt and stores the user in Redis.
 * This endpoint is the canonical way to create users with hashed passwords.
 */
app.post("/auth/register", async (req, res) => {
  const { email, name, password } = req.body;
  if (!email || !name || !password) {
    return res.status(400).json({ error: "email, name, and password are required" });
  }
  if (password.length < 8) {
    return res.status(400).json({ error: "Password must be at least 8 characters" });
  }

  try {
    const r = await getRedis();

    // Check for existing user
    if (await r.get(`user:email:${email}`)) {
      return res.status(409).json({ error: "Email already registered" });
    }

    const { randomUUID } = require("crypto");
    const userId = randomUUID();
    const passwordHash = await bcrypt.hash(password, BCRYPT_ROUNDS);
    const now = new Date().toISOString();

    const userData = {
      id: userId,
      email,
      name,
      phone: "",
      password_hash: passwordHash,
      created_at: now,
      updated_at: now,
    };

    await r.set(`user:${userId}`, JSON.stringify(userData));
    await r.set(`user:email:${email}`, userId);

    return res.status(201).json({ user_id: userId, email });
  } catch (err) {
    console.error("Register error:", err);
    return res.status(500).json({ error: "Internal server error" });
  }
});

/**
 * POST /auth/verify
 * Body: { token }
 * Returns: { valid, user_id, email } or 401
 */
app.post("/auth/verify", async (req, res) => {
  const { token } = req.body;
  if (!token) return res.status(400).json({ error: "token is required" });

  try {
    const r = await getRedis();

    // Check blacklist
    const blacklisted = await r.get(`blacklist:${token}`);
    if (blacklisted) {
      return res.status(401).json({ valid: false, error: "Token has been revoked" });
    }

    const decoded = jwt.verify(token, JWT_SECRET);
    if (decoded.type !== "access") {
      return res.status(401).json({ valid: false, error: "Not an access token" });
    }
    return res.json({ valid: true, user_id: decoded.sub, email: decoded.email });
  } catch (err) {
    if (err.name === "TokenExpiredError") {
      return res.status(401).json({ valid: false, error: "Token expired" });
    }
    return res.status(401).json({ valid: false, error: "Invalid token" });
  }
});

/**
 * POST /auth/refresh
 * Body: { refresh_token }
 * Returns: { access_token }
 */
app.post("/auth/refresh", async (req, res) => {
  const { refresh_token } = req.body;
  if (!refresh_token) return res.status(400).json({ error: "refresh_token is required" });

  try {
    const decoded = jwt.verify(refresh_token, JWT_SECRET);
    if (decoded.type !== "refresh") {
      return res.status(401).json({ error: "Not a refresh token" });
    }

    const r = await getRedis();
    const stored = await r.get(`refresh:${decoded.sub}`);
    if (stored !== refresh_token) {
      return res.status(401).json({ error: "Refresh token mismatch or expired" });
    }

    const accessToken = jwt.sign(
      { sub: decoded.sub, email: decoded.email, type: "access" },
      JWT_SECRET,
      { expiresIn: JWT_ACCESS_EXPIRY }
    );
    return res.json({ access_token: accessToken, token_type: "bearer" });
  } catch (err) {
    return res.status(401).json({ error: "Invalid or expired refresh token" });
  }
});

/**
 * POST /auth/logout
 * Header: Authorization: Bearer <token>
 * Blacklists the current access token.
 */
app.post("/auth/logout", async (req, res) => {
  const authHeader = req.headers.authorization || "";
  const token = authHeader.replace("Bearer ", "");
  if (!token) return res.status(400).json({ error: "No token provided" });

  try {
    const decoded = jwt.decode(token);
    const r = await getRedis();
    // Blacklist for the remaining TTL of the token
    const ttl = decoded?.exp ? decoded.exp - Math.floor(Date.now() / 1000) : 900;
    if (ttl > 0) await r.set(`blacklist:${token}`, "1", { EX: ttl });
    return res.json({ message: "Logged out successfully" });
  } catch {
    return res.status(400).json({ error: "Invalid token" });
  }
});

// ---------------------------------------------------------------------------
// Start server
// ---------------------------------------------------------------------------
async function main() {
  try {
    await getRedis();
    console.log(`Auth service connected to Redis at ${REDIS_URL}`);
  } catch (err) {
    console.error("Failed to connect to Redis at startup:", err.message);
    // Continue anyway — health endpoint will report degraded
  }

  app.listen(PORT, "0.0.0.0", () => {
    console.log(`Auth service running on port ${PORT}`);
  });
}

main().catch(console.error);
