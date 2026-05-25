import sys
from datetime import datetime, timedelta

def generate(path: str, lines: int = 500):
    services = [
        "AuthService",
        "InventoryService",
        "PaymentService",
        "NotificationService",
        "OrderService",
        "ShippingService",
        "ReportingService",
    ]

    messages = [
        "User logged in",
        "Low stock on item SKU-45",
        "Payment failed for ID {}",
        "Session refreshed",
        "Email sent to user@example.com",
        "Order processing delayed",
        "Payment timeout for ID {}",
        "Stock check completed",
        "Push delivered",
        "Inventory mismatch detected",
        "Password check passed",
        "Chargeback reported for ID {}",
        "Restock scheduled",
        "SMS queued",
        "High latency in order API",
        "Two-factor auth initiated",
        "Payment gateway 502",
        "SKU-12 stock updated",
        "Email bounced",
        "Order #{} created",
    ]

    start = datetime(2026, 5, 13, 12, 0, 0)
    with open(path, "w", encoding="utf-8") as f:
        for i in range(1, lines + 1):
            ts = start + timedelta(seconds=i)
            service = services[i % len(services)]
            template = messages[i % len(messages)]
            if "{}" in template:
                msg = template.format(i)
            else:
                msg = template

            # Rotate levels for realism
            if i % 37 == 0:
                level = "ERROR"
            elif i % 11 == 0:
                level = "WARNING"
            else:
                level = "INFO"

            line = f"{ts.strftime('%Y-%m-%d %H:%M:%S')} {level} [{service}] {msg} (#{i})\n"
            f.write(line)

    print(f"Wrote {lines} lines to {path}")


if __name__ == '__main__':
    out = "app.log"
    n = 500
    if len(sys.argv) >= 2:
        try:
            n = int(sys.argv[1])
        except ValueError:
            pass
    if len(sys.argv) >= 3:
        out = sys.argv[2]

    generate(out, n)
