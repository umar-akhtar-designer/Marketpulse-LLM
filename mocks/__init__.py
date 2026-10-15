"""Mocks for OTHER members' outputs, kept clearly separated so they can be swapped
for the real modules at integration time.

These follow the contracts exactly:
  * mocks.mock_data.get_mock_forecasts()  -> Member 2's `Forecast` dicts
  * mocks.mock_data.get_mock_plan()       -> Member 3's `Plan`
  * mocks.mock_data.explain_inputs(plan)  -> Member 3's `explain_inputs()`
"""

from .mock_data import get_mock_forecasts, get_mock_plan, explain_inputs

__all__ = ["get_mock_forecasts", "get_mock_plan", "explain_inputs"]
