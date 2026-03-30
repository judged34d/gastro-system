-- Migration: Events + price snapshot + indices
-- Safe to run multiple times (uses IF NOT EXISTS where possible).

PRAGMA foreign_keys=OFF;

CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('active','closed')) DEFAULT 'active',
  starts_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  ends_at DATETIME
);

-- Ensure there is always at least one active event.
INSERT INTO events (name, status)
SELECT 'Default Event', 'active'
WHERE NOT EXISTS (SELECT 1 FROM events WHERE status = 'active');

-- Add columns only if missing (SQLite doesn't support IF NOT EXISTS for ADD COLUMN).
-- We detect via pragma_table_info.
SELECT 'event_id' WHERE NOT EXISTS (SELECT 1 FROM pragma_table_info('orders') WHERE name='event_id');
-- The SELECT lines are no-ops; actual ALTERs must be guarded by the deploy runner.
-- (Keeping file simple for manual review.)

-- Attach existing orders to the currently active event.
UPDATE orders
SET event_id = (SELECT id FROM events WHERE status = 'active' ORDER BY id DESC LIMIT 1)
WHERE event_id IS NULL;

-- Snapshot prices + names for existing items.
UPDATE order_items
SET unit_price = (SELECT price FROM products p WHERE p.id = order_items.product_id)
WHERE unit_price IS NULL;

UPDATE order_items
SET product_name = (SELECT name FROM products p WHERE p.id = order_items.product_id)
WHERE product_name IS NULL;

-- Indices for performance + safety.
CREATE INDEX IF NOT EXISTS idx_order_items_order ON order_items(order_id);
CREATE INDEX IF NOT EXISTS idx_payments_order ON payments(order_id);
CREATE INDEX IF NOT EXISTS idx_payment_items_payment ON payment_items(payment_id);
CREATE INDEX IF NOT EXISTS idx_order_station_status_order_station ON order_station_status(order_id, station_id);
CREATE INDEX IF NOT EXISTS idx_station_display_station_pos ON station_display(station_id, position);
CREATE INDEX IF NOT EXISTS idx_orders_event ON orders(event_id);

-- Per-event order numbers should be unique.
CREATE UNIQUE INDEX IF NOT EXISTS uniq_orders_event_order_number ON orders(event_id, order_number);

PRAGMA foreign_keys=ON;
