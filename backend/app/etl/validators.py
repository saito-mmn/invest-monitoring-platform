from app.etl.models import PriceRecord, ValidationIssue


def validate_price(record: PriceRecord) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    key = f"{record.jpx_code}:{record.obs_date}"
    prices = [record.open_price, record.high_price, record.low_price, record.close_price]

    if all(value is None for value in prices):
        issues.append(ValidationIssue(key, "missing_ohlc", "OHLC is entirely missing"))
        return issues
    open_price, high_price, low_price, close_price = prices
    if open_price is None or high_price is None or low_price is None or close_price is None:
        issues.append(ValidationIssue(key, "partial_ohlc", "OHLC is partially missing"))
        return issues
    if any(value < 0 for value in (open_price, high_price, low_price, close_price)):
        issues.append(ValidationIssue(key, "negative_price", "Price must not be negative"))
    if high_price < max(open_price, low_price, close_price):
        issues.append(ValidationIssue(key, "invalid_high", "High is below another OHLC value"))
    if low_price > min(open_price, high_price, close_price):
        issues.append(ValidationIssue(key, "invalid_low", "Low is above another OHLC value"))
    if record.volume is not None and record.volume < 0:
        issues.append(ValidationIssue(key, "negative_volume", "Volume must not be negative"))
    return issues
