#!/usr/bin/env python3
"""
Daily demo transaction inserter  (standalone — no Django required).

Run once per day (manually or via cron).  On each run it:
  1. Scans every day from --start-date (default: 7 days ago) to today (IST).
  2. Counts existing orders per day.
  3. Inserts only the shortfall to reach --target per day.

Idempotent: uses ON CONFLICT (order_ref) DO NOTHING.

Examples
--------
  # inside the container
  python daily_demo_transactions.py

  # from the host
  docker compose exec web python daily_demo_transactions.py
  docker compose exec web python daily_demo_transactions.py --target 1000 --start-date 2026-03-28
"""

import argparse
import hashlib
import os
import random
import sys
from datetime import date, datetime, timedelta, timezone as tz
from zoneinfo import ZoneInfo

import psycopg2

# ── timezone helpers ─────────────────────────────────────────────────────────
IST = ZoneInfo("Asia/Kolkata")
UTC = tz.utc

# ── DB connection from env (same vars the Django container uses) ─────────────
DB_CONFIG = dict(
    host=os.getenv("POSTGRES_HOST", "db"),
    port=int(os.getenv("POSTGRES_PORT", "5432")),
    dbname=os.getenv("POSTGRES_DB", "aiops"),
    user=os.getenv("POSTGRES_USER", "user"),
    password=os.getenv("POSTGRES_PASSWORD", "password"),
)


# ── helpers ──────────────────────────────────────────────────────────────────
def _stable_noise(seed: str) -> float:
    digest = hashlib.sha256(seed.encode()).hexdigest()[:8]
    return int(digest, 16) / 0xFFFFFFFF


def _hour_weight(hour: int) -> float:
    """Business-hour weighting (IST): 09-18 peak."""
    if 9 <= hour < 18:
        return 2.8
    if 7 <= hour < 9 or 18 <= hour < 21:
        return 1.35
    return 0.55


def _hourly_distribution(total: int, day_key: str) -> list[int]:
    weighted = []
    for h in range(24):
        jitter = 0.9 + (_stable_noise(f"{day_key}:{h}") * 0.2)
        weighted.append(_hour_weight(h) * jitter)
    tw = sum(weighted) or 1.0
    raw = [(w / tw) * total for w in weighted]
    dist = [int(v) for v in raw]
    remainder = total - sum(dist)
    if remainder > 0:
        by_frac = sorted(
            ((i, raw[i] - dist[i]) for i in range(24)),
            key=lambda x: x[1],
            reverse=True,
        )
        for i, _ in by_frac[:remainder]:
            dist[i] += 1
    return dist


def _existing_counts(cur, start: date, end: date) -> dict[date, int]:
    """Return {date: order_count} for the date range (IST day boundaries)."""
    start_utc = datetime.combine(start, datetime.min.time(), tzinfo=IST).astimezone(UTC)
    end_utc = datetime.combine(end + timedelta(days=1), datetime.min.time(), tzinfo=IST).astimezone(UTC)
    cur.execute(
        """
        SELECT (created_at AT TIME ZONE 'Asia/Kolkata')::date AS day, COUNT(*)
          FROM demo_orders
         WHERE created_at >= %s AND created_at < %s
         GROUP BY day
        """,
        (start_utc, end_utc),
    )
    return {row[0]: row[1] for row in cur.fetchall()}


# ── main ─────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Insert demo transactions up to a daily target.")
    parser.add_argument("--target", type=int, default=1000, help="Orders per day (default 1000)")
    parser.add_argument("--start-date", type=str, default=None,
                        help="Earliest date YYYY-MM-DD (default: 7 days ago)")
    parser.add_argument("--failure-rate", type=float, default=0.08,
                        help="Fraction of orders without billing (default 0.08)")
    parser.add_argument("--avg-amount", type=float, default=1299.0,
                        help="Average order amount INR (default 1299)")
    args = parser.parse_args()

    target = max(1, args.target)
    failure_rate = min(max(args.failure_rate, 0.0), 0.95)
    avg_amount = max(1.0, args.avg_amount)

    now_ist = datetime.now(IST)
    today = now_ist.date()
    start_date = date.fromisoformat(args.start_date) if args.start_date else today - timedelta(days=6)

    if start_date > today:
        print("⚠  start-date is in the future — nothing to do.")
        return

    # ── connect ──────────────────────────────────────────────────────────────
    conn = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = False
    cur = conn.cursor()

    try:
        existing = _existing_counts(cur, start_date, today)

        # ── build plan ───────────────────────────────────────────────────────
        plan: list[tuple[date, int]] = []
        day = start_date
        while day <= today:
            current = existing.get(day, 0)
            shortfall = target - current
            if shortfall > 0:
                plan.append((day, shortfall))
            day += timedelta(days=1)

        if not plan:
            print(f"✓  All days {start_date} → {today} already have ≥ {target} orders.")
            return

        total_to_insert = sum(s for _, s in plan)
        print(f"Found {len(plan)} day(s) below target ({target}/day).  "
              f"Will insert {total_to_insert} orders total.\n")
        for d, shortfall in plan:
            print(f"  {d}:  {existing.get(d, 0):>5} existing  →  +{shortfall} needed")
        print()

        # ── insert ───────────────────────────────────────────────────────────
        rng = random.Random(int(now_ist.timestamp()))
        grand_orders = grand_bill = grand_fail = 0

        for d, shortfall in plan:
            hourly = _hourly_distribution(shortfall, d.isoformat() + ":fill")
            d_ord = d_bill = d_fail = 0

            for hour, count in enumerate(hourly):
                for idx in range(count):
                    order_ref = (
                        f"ord-{d.strftime('%Y%m%d')}-{hour:02d}-"
                        f"F{idx:04d}-{rng.randint(1000, 9999)}"
                    )
                    minute = rng.randint(0, 59)
                    second = rng.randint(0, 59)
                    created_ist = datetime(d.year, d.month, d.day,
                                           hour, minute, second, tzinfo=IST)
                    created_utc = created_ist.astimezone(UTC)

                    sku = rng.choice(["SKU-100", "SKU-200", "SKU-300"])
                    qty = rng.randint(1, 3)

                    cur.execute(
                        """
                        INSERT INTO demo_orders
                               (order_ref, customer_name, sku, quantity, status, created_at)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        ON CONFLICT (order_ref) DO NOTHING
                        """,
                        (order_ref, "Demo User", sku, qty, "created", created_utc),
                    )
                    if cur.rowcount == 0:
                        continue          # duplicate ref, skip
                    d_ord += 1

                    # failure?
                    boost = 0.015 if 9 <= hour < 18 else 0.0
                    if rng.random() < min(0.95, failure_rate + boost):
                        d_fail += 1
                        continue

                    # billing
                    amt_mult = 0.85 + (rng.random() * 0.3)
                    amount = round(avg_amount * qty * amt_mult, 2)
                    delay = timedelta(seconds=rng.randint(5, 180))

                    cur.execute(
                        """
                        INSERT INTO demo_billing
                               (order_ref, amount, status, created_at)
                        VALUES (%s, %s, %s, %s)
                        """,
                        (order_ref, amount, "authorized", created_utc + delay),
                    )
                    d_bill += 1

            grand_orders += d_ord
            grand_bill += d_bill
            grand_fail += d_fail
            print(f"  {d}:  +{d_ord} orders, +{d_bill} billings, {d_fail} failed")

        conn.commit()
        print(f"\n✓  Done.  {grand_orders} orders, {grand_bill} billings, "
              f"{grand_fail} without authorisation.")

    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
