"""Mocks for Member 2 (Forecast) and Member 3 (Plan + explain_inputs).

NOT part of the LLM layer. Real implementations live in the teammates' repos and are
dropped in behind the same function signatures (see CONTRACT.md §5, §6).
"""

from __future__ import annotations


def get_mock_forecasts() -> dict[str, dict]:
    """Member 2 contract: {p10, p50, p90, mean, std, horizon_days}."""
    return {
        "SKU_MILK_1L": {"p10": 30.0, "p50": 52.0, "p90": 78.0, "mean": 53.0, "std": 18.8, "horizon_days": 14},
        "SKU_RICE_5KG": {"p10": 20.0, "p50": 34.0, "p90": 52.0, "mean": 35.0, "std": 12.5, "horizon_days": 14},
        "SKU_OIL_1L": {"p10": 18.0, "p50": 28.0, "p90": 44.0, "mean": 30.0, "std": 10.2, "horizon_days": 14},
        "SKU_TEA_250G": {"p10": 12.0, "p50": 22.0, "p90": 36.0, "mean": 23.0, "std": 9.4, "horizon_days": 14},
        "SKU_EXOTIC_SPICE": {"p10": 2.0, "p50": 9.0, "p90": 25.0, "mean": 11.0, "std": 9.0, "horizon_days": 14},
    }


def get_mock_plan() -> dict:
    """Member 3 contract: budget-constrained Plan."""
    return {
        "total_cost": 2980.50,
        "budget": 3000.00,
        "budget_used": 2980.50,
        "budget_remaining": 19.50,
        "total_expected_profit": 842.20,
        "total_items_ordered": 482,
        "binding_constraints": ["BUDGET"],
        "items": {
            "SKU_MILK_1L": {
                "product_id": "SKU_MILK_1L", "name": "Fresh Whole Milk 1L",
                "order_qty": 48, "cost": 57.60, "unit_cost": 1.20, "unit_price": 1.80,
                "expected_profit": 26.40, "expected_stockout_prob": 0.12,
                "expected_leftover": 3.4, "critical_ratio": 0.86,
                "binding_constraints": ["PACK_SIZE"],
                "reason_codes": ["ALLOCATED_OPTIMAL", "PACK_SIZE_ROUNDED"],
                "uncertainty_flag": False, "relative_uncertainty": 0.65,
            },
            "SKU_RICE_5KG": {
                "product_id": "SKU_RICE_5KG", "name": "Basmati Rice 5kg",
                "order_qty": 30, "cost": 240.00, "unit_cost": 8.00, "unit_price": 11.00,
                "expected_profit": 90.00, "expected_stockout_prob": 0.15,
                "expected_leftover": 2.1, "critical_ratio": 0.73,
                "binding_constraints": ["PACK_SIZE"],
                "reason_codes": ["ALLOCATED_OPTIMAL"],
                "uncertainty_flag": False, "relative_uncertainty": 0.36,
            },
            "SKU_OIL_1L": {
                "product_id": "SKU_OIL_1L", "name": "Cooking Oil 1L",
                "order_qty": 40, "cost": 360.00, "unit_cost": 9.00, "unit_price": 12.50,
                "expected_profit": 140.00, "expected_stockout_prob": 0.10,
                "expected_leftover": 1.8, "critical_ratio": 0.75,
                "binding_constraints": [],
                "reason_codes": ["ALLOCATED_OPTIMAL"],
                "uncertainty_flag": False, "relative_uncertainty": 0.42,
            },
            "SKU_TEA_250G": {
                "product_id": "SKU_TEA_250G", "name": "Black Tea 250g",
                "order_qty": 24, "cost": 168.00, "unit_cost": 7.00, "unit_price": 9.50,
                "expected_profit": 60.00, "expected_stockout_prob": 0.18,
                "expected_leftover": 2.6, "critical_ratio": 0.70,
                "binding_constraints": ["MOQ"],
                "reason_codes": ["ALLOCATED_TRIMMED_BUDGET", "MOQ_PROMOTED"],
                "uncertainty_flag": False, "relative_uncertainty": 0.51,
            },
            "SKU_EXOTIC_SPICE": {
                "product_id": "SKU_EXOTIC_SPICE", "name": "Saffron Spice 5g",
                "order_qty": 0, "cost": 0.00, "unit_cost": 18.00, "unit_price": 24.00,
                "expected_profit": 0.00, "expected_stockout_prob": 0.85,
                "expected_leftover": 0.0, "critical_ratio": 0.45,
                "binding_constraints": ["BUDGET"],
                "reason_codes": ["DROPPED_HIGH_UNCERTAINTY", "DROPPED_LOW_CAPITAL_EFFICIENCY"],
                "uncertainty_flag": True, "relative_uncertainty": 2.10,
            },
        },
        "sensitivity": {
            "100_percent": {"budget_level": "100%", "budget_amount": 3000.00,
                            "total_cost": 2980.50, "total_expected_profit": 842.20,
                            "items_ordered_count": 4},
            "80_percent": {"budget_level": "80%", "budget_amount": 2400.00,
                           "total_cost": 2390.00, "total_expected_profit": 718.50,
                           "items_ordered_count": 4},
            "60_percent": {"budget_level": "60%", "budget_amount": 1800.00,
                           "total_cost": 1785.00, "total_expected_profit": 572.10,
                           "items_ordered_count": 3},
        },
    }


_REASON_TEXT = {
    "ALLOCATED_OPTIMAL": "it is funded to its optimal quantity with a good expected margin",
    "ALLOCATED_HIGH_MARGIN": "it has a high margin and reliable demand",
    "ALLOCATED_TRIMMED_BUDGET": "it was trimmed because the budget was limited",
    "PACK_SIZE_ROUNDED": "the quantity was rounded up to the supplier pack size",
    "MOQ_PROMOTED": "the quantity was rounded up to the supplier minimum order quantity",
    "DROPPED_BUDGET_EXHAUSTED": "the budget ran out before it could be funded",
    "DROPPED_HIGH_UNCERTAINTY": "its demand uncertainty is too high relative to its cost",
    "DROPPED_LOW_CAPITAL_EFFICIENCY": "its expected profit per currency unit is low",
    "CAPPED_SHELF_LIFE": "the quantity was capped to prevent spoilage before expiry",
}


def explain_inputs(plan: dict) -> dict:
    """Deterministic mock of Member 3's ``explain_inputs()``."""
    items = plan.get("items", {})
    funded = {k: v for k, v in items.items() if v.get("order_qty", 0) > 0}
    dropped = {k: v for k, v in items.items() if v.get("order_qty", 0) <= 0}
    budget = float(plan.get("budget", 0.0)) or 1.0

    top = sorted(funded.values(), key=lambda v: v.get("expected_profit", 0.0), reverse=True)[:3]
    top_allocations = [{
        "name": it["name"],
        "qty": it["order_qty"],
        "spend": it["cost"],
        "profit": it["expected_profit"],
        "reason": "; ".join(_REASON_TEXT.get(c, c) for c in it.get("reason_codes", [])),
    } for it in top]

    dropped_items = [{
        "name": it["name"],
        "cost_to_order": it["unit_cost"],
        "reason_code": (it.get("reason_codes") or ["DROPPED_LOW_CAPITAL_EFFICIENCY"])[0],
        "explanation": "; ".join(_REASON_TEXT.get(c, c) for c in it.get("reason_codes", [])),
    } for it in dropped.values()]

    uncertainty_alerts = [{
        "name": it["name"],
        "relative_uncertainty": it["relative_uncertainty"],
        "note": "high forecast uncertainty relative to expected demand",
    } for it in items.values() if it.get("uncertainty_flag")]

    sens = plan.get("sensitivity", {})
    bottleneck = ""
    if "100_percent" in sens and "80_percent" in sens:
        d_budget = sens["100_percent"]["budget_amount"] - sens["80_percent"]["budget_amount"]
        d_profit = sens["100_percent"]["total_expected_profit"] - sens["80_percent"]["total_expected_profit"]
        bottleneck = (f"At {sens['100_percent']['budget_amount']} the budget is binding; "
                      f"{len(dropped)} product(s) were not funded. "
                      f"The final {d_budget} of budget adds {round(d_profit, 2)} in expected profit.")

    return {
        "summary": {
            "budget": plan.get("budget"),
            "total_spend": plan.get("total_cost"),
            "expected_profit": plan.get("total_expected_profit"),
            "budget_utilization_pct": round(100.0 * plan.get("total_cost", 0.0) / budget, 2),
            "num_products_funded": len(funded),
            "num_products_dropped": len(dropped),
        },
        "top_allocations": top_allocations,
        "dropped_items": dropped_items,
        "uncertainty_alerts": uncertainty_alerts,
        "budget_bottleneck": bottleneck,
    }
