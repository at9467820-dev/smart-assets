"""
Depreciation-based cost estimation and risk scoring.
"""
from datetime import date
import math


# ── Depreciation Rates by Category ────────────────────────────
DEPRECIATION_RATES = {
    "Computer":      0.25,   # 25% per year (rapid)
    "Projector":     0.20,
    "Networking":    0.20,
    "Lab Equipment": 0.15,
    "Electrical":    0.12,
    "HVAC":          0.10,
    "Furniture":     0.08,
    "Vehicle":       0.15,
    "Other":         0.12,
}

# Maintenance cost as % of current book value per year
MAINTENANCE_RATE = {
    "Computer":      0.10,
    "Projector":     0.08,
    "Networking":    0.08,
    "Lab Equipment": 0.12,
    "Electrical":    0.10,
    "HVAC":          0.12,
    "Furniture":     0.05,
    "Vehicle":       0.15,
    "Other":         0.08,
}

USEFUL_LIFE = {
    "Computer": 5, "Projector": 7, "Networking": 6, "Lab Equipment": 10,
    "Electrical": 10, "HVAC": 15, "Furniture": 15, "Vehicle": 10, "Other": 8,
}


def current_book_value(asset) -> float:
    """Calculate current book value using straight-line depreciation."""
    cost = float(asset.purchase_cost or 0)
    if not asset.purchase_date or cost == 0:
        return cost
    age = asset.age_years
    rate = DEPRECIATION_RATES.get(asset.category, 0.12)
    life = USEFUL_LIFE.get(asset.category, 8)
    # Straight-line: value = cost * max(0, 1 - age/life)
    remaining_ratio = max(0.0, 1 - age / life)
    return round(cost * remaining_ratio, 2)


def estimated_maintenance_cost(asset) -> float:
    """Annual estimated maintenance cost for this asset."""
    book = current_book_value(asset)
    rate = MAINTENANCE_RATE.get(asset.category, 0.08)
    return round(book * rate, 2)


def estimated_replacement_cost(asset) -> float:
    """
    Estimate replacement cost.
    For young assets: original cost + ~5% inflation/year.
    For old/fully-depreciated: original cost * 1.15 (replacement premium).
    """
    cost = float(asset.purchase_cost or 0)
    age = asset.age_years
    inflation_rate = 0.05
    inflated = cost * ((1 + inflation_rate) ** age)
    book = current_book_value(asset)
    if book < cost * 0.1:
        # Nearly fully depreciated — replacement cost is full inflated price
        return round(inflated, 2)
    return 0.0  # Not yet due for replacement


def compute_risk_score(asset) -> int:
    """
    Compute a 0–100 risk-of-failure score.

    Factors:
    - Age relative to useful life (0–35 pts)
    - Repair frequency / year (0–35 pts)
    - Days since last service (0–30 pts)
    """
    score = 0

    # Factor 1: Age vs. useful life
    life = USEFUL_LIFE.get(asset.category, 8)
    age = asset.age_years
    age_ratio = min(age / life, 1.5)  # cap at 150% of life
    score += int(age_ratio * 35)

    # Factor 2: Repair frequency (repairs per year)
    repairs = asset.repair_count
    if age > 0:
        repairs_per_year = repairs / max(age, 0.5)
    else:
        repairs_per_year = repairs
    repair_score = min(repairs_per_year * 10, 35)
    score += int(repair_score)

    # Factor 3: Days since last service
    days = asset.days_since_last_service
    # Penalise after 180 days, max at 540+ days
    service_score = min(max(days - 180, 0) / 360 * 30, 30)
    score += int(service_score)

    return min(score, 100)


def risk_label(score: int) -> str:
    if score >= 70:
        return "High Risk"
    elif score >= 40:
        return "Moderate"
    return "Low Risk"


def risk_badge_class(score: int) -> str:
    if score >= 70:
        return "badge-danger"
    elif score >= 40:
        return "badge-warning"
    return "badge-success"
