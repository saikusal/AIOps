CREATE TABLE IF NOT EXISTS demo_service_state (
    id SERIAL PRIMARY KEY,
    service_name TEXT NOT NULL,
    state TEXT NOT NULL,
    notes TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS demo_service_state_service_idx
    ON demo_service_state (service_name, updated_at DESC);

CREATE TABLE IF NOT EXISTS demo_inventory (
    sku TEXT PRIMARY KEY,
    product_name TEXT NOT NULL,
    available_quantity INTEGER NOT NULL,
    reserved_quantity INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS demo_orders (
    id SERIAL PRIMARY KEY,
    order_ref TEXT NOT NULL UNIQUE,
    customer_name TEXT NOT NULL,
    sku TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    status TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS demo_billing (
    id SERIAL PRIMARY KEY,
    order_ref TEXT NOT NULL,
    amount NUMERIC(10,2) NOT NULL,
    status TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO demo_service_state (service_name, state, notes)
SELECT service_name, state, notes
FROM (
    VALUES
        ('app-orders', 'healthy', 'Orders pipeline is serving checkout and returns data.'),
        ('app-orders', 'healthy', 'Background order reconciliation completed successfully.'),
        ('app-inventory', 'healthy', 'Inventory sync completed and stock numbers are current.'),
        ('app-inventory', 'healthy', 'Warehouse sync is within latency objectives.'),
        ('app-billing', 'healthy', 'Billing queue is processing invoices without retries.'),
        ('app-billing', 'healthy', 'Payment gateway callbacks are being reconciled correctly.')
) AS seed(service_name, state, notes)
WHERE NOT EXISTS (
    SELECT 1 FROM demo_service_state existing WHERE existing.service_name = seed.service_name
);

INSERT INTO demo_inventory (sku, product_name, available_quantity, reserved_quantity)
SELECT sku, product_name, available_quantity, reserved_quantity
FROM (
    VALUES
        ('SKU-100', 'Database Recovery Guide', 25, 0),
        ('SKU-200', 'Prometheus Troubleshooting Pack', 18, 0),
        ('SKU-300', 'On-Call Runbook Bundle', 12, 0)
) AS seed(sku, product_name, available_quantity, reserved_quantity)
WHERE NOT EXISTS (
    SELECT 1 FROM demo_inventory existing WHERE existing.sku = seed.sku
);
