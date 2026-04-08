from datetime import timedelta
import hashlib
import random

from django.core.management.base import BaseCommand
from django.db import connection, transaction
from django.utils import timezone
from zoneinfo import ZoneInfo


class Command(BaseCommand):
    help = "Backfill demo_orders and demo_billing for last N days with peak traffic between 09:00 and 18:00 IST."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=7)
        parser.add_argument("--daily-transactions", type=int, default=1000)
        parser.add_argument("--failure-rate", type=float, default=0.08)
        parser.add_argument("--avg-amount", type=float, default=1499.0)
        parser.add_argument("--reset-window", action="store_true")
        parser.add_argument("--seed", type=int, default=20260404)

    def _stable_noise(self, seed: str) -> float:
        digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:8]
        return int(digest, 16) / 0xFFFFFFFF

    def _hour_weight(self, hour: int) -> float:
        if 9 <= hour < 18:
            return 2.8
        if 7 <= hour < 9 or 18 <= hour < 21:
            return 1.35
        return 0.55

    def _hourly_distribution(self, total: int, day_key: str):
        weighted = []
        for hour in range(24):
            jitter = 0.9 + (self._stable_noise(f"{day_key}:{hour}") * 0.2)
            weighted.append(self._hour_weight(hour) * jitter)

        total_weight = sum(weighted) or 1.0
        raw = [(weight / total_weight) * total for weight in weighted]
        distributed = [int(value) for value in raw]
        remainder = total - sum(distributed)

        if remainder > 0:
            remainders = sorted(
                ((idx, raw[idx] - distributed[idx]) for idx in range(24)),
                key=lambda item: item[1],
                reverse=True,
            )
            for idx, _ in remainders[:remainder]:
                distributed[idx] += 1
        return distributed

    def handle(self, *args, **options):
        days = max(1, int(options["days"]))
        daily_transactions = max(1, int(options["daily_transactions"]))
        failure_rate = min(max(float(options["failure_rate"]), 0.0), 0.95)
        avg_amount = max(1.0, float(options["avg_amount"]))
        reset_window = bool(options["reset_window"])
        rng = random.Random(int(options["seed"]))

        ist = ZoneInfo("Asia/Kolkata")
        now_ist = timezone.localtime(timezone.now(), ist)
        start_date = now_ist.date() - timedelta(days=days - 1)
        start_dt_ist = timezone.datetime.combine(start_date, timezone.datetime.min.time(), tzinfo=ist)
        start_dt_utc = start_dt_ist.astimezone(ZoneInfo("UTC"))

        created_orders = 0
        created_billings = 0
        failed_orders = 0

        with transaction.atomic():
            with connection.cursor() as cursor:
                if reset_window:
                    cursor.execute("DELETE FROM demo_billing WHERE created_at >= %s", [start_dt_utc])
                    cursor.execute("DELETE FROM demo_orders WHERE created_at >= %s", [start_dt_utc])

                for day_offset in range(days):
                    day = start_date + timedelta(days=day_offset)
                    day_key = day.isoformat()
                    hourly_counts = self._hourly_distribution(daily_transactions, day_key)

                    for hour, tx_count in enumerate(hourly_counts):
                        for tx_idx in range(tx_count):
                            order_ref = f"ord-{day.strftime('%Y%m%d')}-{hour:02d}-{tx_idx:04d}-{rng.randint(1000,9999)}"
                            minute = rng.randint(0, 59)
                            second = rng.randint(0, 59)
                            created_at_ist = timezone.datetime(day.year, day.month, day.day, hour, minute, second, tzinfo=ist)
                            created_at_utc = created_at_ist.astimezone(ZoneInfo("UTC"))

                            sku = rng.choice(["SKU-100", "SKU-200", "SKU-300"])
                            quantity = rng.randint(1, 3)

                            cursor.execute(
                                """
                                INSERT INTO demo_orders (order_ref, customer_name, sku, quantity, status, created_at)
                                VALUES (%s, %s, %s, %s, %s, %s)
                                ON CONFLICT (order_ref) DO NOTHING
                                """,
                                [order_ref, "Ajith Demo User", sku, quantity, "created", created_at_utc],
                            )
                            if cursor.rowcount == 0:
                                continue
                            created_orders += 1

                            hour_failure_boost = 0.015 if (9 <= hour < 18) else 0.0
                            effective_failure_rate = min(0.95, failure_rate + hour_failure_boost)
                            is_failed = rng.random() < effective_failure_rate
                            if is_failed:
                                failed_orders += 1
                                continue

                            amount_multiplier = 0.85 + (rng.random() * 0.3)
                            amount = round(avg_amount * quantity * amount_multiplier, 2)

                            cursor.execute(
                                """
                                INSERT INTO demo_billing (order_ref, amount, status, created_at)
                                VALUES (%s, %s, %s, %s)
                                """,
                                [order_ref, amount, "authorized", created_at_utc + timedelta(seconds=rng.randint(5, 180))],
                            )
                            created_billings += 1

        self.stdout.write(self.style.SUCCESS("Demo transaction backfill completed."))
        self.stdout.write(f"days={days} daily_transactions={daily_transactions} failure_rate={failure_rate:.3f} avg_amount={avg_amount:.2f}")
        self.stdout.write(f"orders_inserted={created_orders} billings_inserted={created_billings} orders_without_authorization={failed_orders}")
        self.stdout.write("traffic_profile=all_hours_with_peak_09:00-18:00_IST")
