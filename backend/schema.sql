-- activity_log
CREATE TABLE IF NOT EXISTS activity_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kind TEXT NOT NULL,
            message TEXT NOT NULL,
            order_id INTEGER,
            order_number INTEGER,
            amount REAL,
            actor TEXT,
            station_name TEXT,
            meta_json TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

-- app_settings
CREATE TABLE IF NOT EXISTS app_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

-- categories
CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL
, event_id INTEGER);

-- custom_icons
CREATE TABLE IF NOT EXISTS custom_icons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            filename TEXT NOT NULL UNIQUE,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

-- events
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('active','closed')) DEFAULT 'active',
  starts_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  ends_at DATETIME
, is_demo INTEGER NOT NULL DEFAULT 0);

-- order_item_cancellations
CREATE TABLE IF NOT EXISTS order_item_cancellations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            order_item_id INTEGER NOT NULL,
            event_id INTEGER NOT NULL,
            reason TEXT NOT NULL,
            quantity INTEGER NOT NULL CHECK(quantity > 0),
            unit_price REAL NOT NULL DEFAULT 0,
            amount REAL NOT NULL DEFAULT 0,
            created_by_role TEXT NOT NULL,
            created_by_user_id INTEGER,
            created_by_station_id INTEGER,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

-- order_item_changes
CREATE TABLE IF NOT EXISTS order_item_changes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_item_id INTEGER,
    change_type TEXT CHECK(change_type IN ('added','updated','removed')),
    quantity_change INTEGER,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- order_items
CREATE TABLE IF NOT EXISTS order_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER,
    product_id INTEGER,
    note TEXT,
    quantity_total INTEGER,
    quantity_open INTEGER,
    quantity_paid INTEGER
, unit_price REAL, product_name TEXT, vat_rate INTEGER);

-- order_station_status
CREATE TABLE IF NOT EXISTS order_station_status (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER,
    station_id INTEGER,
    status TEXT CHECK(status IN ('new','preparing','ready')),
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- orders
CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_number INTEGER,
    table_id INTEGER,
    waiter_id INTEGER,
    status TEXT CHECK(status IN ('new','preparing','ready','paid')),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
, event_id INTEGER, source TEXT DEFAULT 'waiter', source_station_id INTEGER);

-- payment_items
CREATE TABLE IF NOT EXISTS payment_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    payment_id INTEGER,
    order_item_id INTEGER,
    quantity INTEGER
);

-- payments
CREATE TABLE IF NOT EXISTS payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER,
    amount REAL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
, payment_type TEXT DEFAULT 'paid');

-- products
CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    price REAL NOT NULL,
    category_id INTEGER,
    active INTEGER DEFAULT 1
, event_id INTEGER, display_category_id INTEGER, vat_rate INTEGER NOT NULL DEFAULT 19, icon_type TEXT NOT NULL DEFAULT 'none', icon_ref TEXT, sort_order INTEGER NOT NULL DEFAULT 0);

-- station_categories
CREATE TABLE IF NOT EXISTS station_categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    station_id INTEGER,
    category_id INTEGER
, event_id INTEGER);

-- station_display
CREATE TABLE IF NOT EXISTS station_display (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    station_id INTEGER,
    order_id INTEGER,
    position INTEGER,
    locked INTEGER DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- stations
CREATE TABLE IF NOT EXISTS stations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    pin TEXT,
    active INTEGER DEFAULT 1
);

-- tab_entries
CREATE TABLE IF NOT EXISTS tab_entries (id INTEGER PRIMARY KEY AUTOINCREMENT, tab_id INTEGER, order_id INTEGER, order_item_id INTEGER, quantity INTEGER, unit_price REAL, amount REAL, created_at DATETIME DEFAULT CURRENT_TIMESTAMP, created_by_role TEXT, created_by_user_id INTEGER, created_by_station_id INTEGER);

-- tab_payment_items
CREATE TABLE IF NOT EXISTS tab_payment_items (id INTEGER PRIMARY KEY AUTOINCREMENT, payment_id INTEGER, tab_entry_id INTEGER, quantity INTEGER, amount REAL);

-- tab_payments
CREATE TABLE IF NOT EXISTS tab_payments (id INTEGER PRIMARY KEY AUTOINCREMENT, tab_id INTEGER, amount REAL, created_at DATETIME DEFAULT CURRENT_TIMESTAMP, created_by_role TEXT, created_by_user_id INTEGER, created_by_station_id INTEGER, payment_type TEXT NOT NULL DEFAULT 'paid');

-- tables
CREATE TABLE IF NOT EXISTS tables (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    active INTEGER DEFAULT 1
, event_id INTEGER);

-- tabs
CREATE TABLE IF NOT EXISTS tabs (id INTEGER PRIMARY KEY AUTOINCREMENT, event_id INTEGER, name TEXT NOT NULL, active INTEGER DEFAULT 1, created_at DATETIME DEFAULT CURRENT_TIMESTAMP);

-- users
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    pin TEXT,
    role TEXT CHECK(role IN ('waiter','station','admin')),
    active INTEGER DEFAULT 1
, event_id INTEGER, opening_cash REAL NOT NULL DEFAULT 0, closing_cash REAL);

-- waiter_tables
CREATE TABLE IF NOT EXISTS waiter_tables (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    waiter_id INTEGER,
    table_id INTEGER
, event_id INTEGER);
