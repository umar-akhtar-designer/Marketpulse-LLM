"""Component E: routing, grounded replies, number guard, and adversarial refusal."""

from llm.client import MockLLMClient
from llm.explainer import explain, route_question
from llm.guard import check_numbers
from mocks import explain_inputs, get_mock_forecasts, get_mock_plan


def _srcs(plan):
    return {"plan": plan, "explain_inputs": explain_inputs(plan), "forecasts": get_mock_forecasts()}


ROUTING = [
    ("Why fewer units of rice?", "why_fewer_units"),
    ("What if the budget changes?", "what_if_budget"),
    ("What could go wrong?", "what_could_be_wrong"),
    ("Why was the spice excluded?", "why_excluded"),
    ("Tell me about the plan", "general"),
    ("چاول کے کم یونٹ کیوں؟", "why_fewer_units"),
    ("اگر بجٹ کم ہو جائے تو؟", "what_if_budget"),
    ("لماذا أقل وحدات؟", "why_fewer_units"),
    ("Por que menos unidades?", "why_fewer_units"),
    ("¿Qué pasa si cambia el presupuesto?", "what_if_budget"),
    ("ماذا لو تغيرت الميزانية؟", "what_if_budget"),
]


def test_routing():
    for q, expected in ROUTING:
        assert route_question(q) == expected, q


def test_offline_replies_all_languages_and_grounded():
    plan = get_mock_plan()
    fc = get_mock_forecasts()
    for lang in ["en", "ur", "es", "sw", "hi", "ar"]:
        ans = explain("What if the budget changes?", plan, fc, lang, offline=True)
        assert ans.text.strip()
        assert ans.language == lang
        assert ans.guard_passed
        assert check_numbers(ans.text, _srcs(plan)).ok


def test_grounding_every_figure_traces_to_source():
    plan = get_mock_plan()
    ans = explain("Why fewer units of Basmati Rice 5kg?", plan, get_mock_forecasts(), "en", offline=True)
    assert ans.figures_cited
    assert all(f.source_path for f in ans.figures_cited)


def test_adversarial_estimate_is_refused_and_redirected():
    plan = get_mock_plan()
    for q in ["Just estimate how much milk I will sell",
              "roughly how many units will sell next month?",
              "please predict my profit"]:
        ans = explain(q, plan, get_mock_forecasts(), "en", offline=True)
        assert ans.refused is True
        assert ans.guard_passed
        assert check_numbers(ans.text, _srcs(plan)).ok


def test_llm_grounded_output_accepted():
    plan = get_mock_plan()
    good = "The plan orders 48 units of Fresh Whole Milk 1L for a cost of 57.6."
    client = MockLLMClient(responder=good)
    ans = explain("Why milk?", plan, get_mock_forecasts(), "en", offline=False, client=client)
    assert ans.guard_passed
    assert "48" in ans.text


def test_llm_fake_figure_is_rejected_and_fallback_grounded():
    plan = get_mock_plan()
    fake = "You should order 8888888 units and expect 7777777 profit."
    client = MockLLMClient(responder=fake)
    ans = explain("Why milk?", plan, get_mock_forecasts(), "en", offline=False, client=client)
    assert ans.guard_passed is False          # model output was rejected
    assert "8888888" not in ans.text
    assert "7777777" not in ans.text
    assert check_numbers(ans.text, _srcs(plan)).ok


def test_what_if_uses_sensitivity_numbers():
    plan = get_mock_plan()
    ans = explain("what if the budget is lower?", plan, get_mock_forecasts(), "en", offline=True)
    # sensitivity 80% budget 2400 / profit 718.5 must appear
    assert "2400" in ans.text
    assert "718.5" in ans.text
