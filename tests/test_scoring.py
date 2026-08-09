from stock_scout.models import TickerFacts
from stock_scout.score.composite import composite_score, manipulation_risk_v1, velocity_zscore

WEIGHTS = {"velocity": 3.0, "novelty": 3.0, "cross_source": 2.0, "author_quality": 2.0,
           "action_signal": 4.0, "mainstream_penalty": 5.0, "manipulation_risk": 4.0}


def test_velocity_zero_without_history():
    assert velocity_zscore(10.0, [], cap=10) == 0.0
    assert velocity_zscore(10.0, [1.0], cap=10) == 0.0


def test_velocity_spike_detected():
    baseline = [1.0, 1.5, 0.5, 1.0, 1.2, 0.8, 1.1] * 4
    z = velocity_zscore(10.0, baseline, cap=10)
    assert z > 3.0


def test_velocity_capped_and_non_negative():
    baseline = [1.0] * 30
    assert velocity_zscore(1000.0, baseline, cap=10) == 10.0
    assert velocity_zscore(0.0, baseline, cap=10) == 0.0


def test_manipulation_penny_and_otc():
    penny = TickerFacts(symbol="X", price=0.5)
    otc = TickerFacts(symbol="Y", price=5.0, is_otc=True)
    normal = TickerFacts(symbol="Z", price=50.0)
    assert manipulation_risk_v1(penny, 0.2) == 0.2
    assert manipulation_risk_v1(otc, 0.2) == 0.2
    assert manipulation_risk_v1(normal, 0.2) == 0.0


def test_mainstream_penalty_sinks_score():
    quiet = composite_score(velocity_z=3.0, novelty=1.0, cross_source=2, author_quality=0.6,
                            action_signal=0.0, mainstream_flag=False, manipulation_risk=0.0,
                            weights=WEIGHTS)
    viral = composite_score(velocity_z=3.0, novelty=1.0, cross_source=2, author_quality=0.6,
                            action_signal=0.0, mainstream_flag=True, manipulation_risk=0.0,
                            weights=WEIGHTS)
    assert quiet.total - viral.total == 5.0
    assert quiet.total > 8.0  # this profile should clear the default alert threshold


def test_components_survive_roundtrip():
    b = composite_score(velocity_z=2.0, novelty=0.0, cross_source=1, author_quality=0.5,
                        action_signal=0.0, mainstream_flag=False, manipulation_risk=0.2,
                        weights=WEIGHTS)
    d = b.as_dict()
    assert d["velocity_z"] == 2.0
    assert d["manipulation_risk"] == 0.2
    assert d["total"] == round(b.total, 2)
