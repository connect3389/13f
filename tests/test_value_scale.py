from thirteenf.value_scale import infer_value_usd_multiplier


def test_infer_thousands_when_implied_price_tiny_as_dollars():
    # 669M shares, value 91.5M thousands -> ~$137/sh
    mult = infer_value_usd_multiplier([(91_524_356, 669_429_166)])
    assert mult == 1000.0


def test_infer_dollars_when_implied_price_reasonable():
    # Berkshire-style: $11.87B / 41.28M sh ~ $287
    mult = infer_value_usd_multiplier([(11_871_367_661, 41_283_098)])
    assert mult == 1.0


def test_infer_dollars_median_over_many_lines():
    holdings = [
        (11_871_367_661, 41_283_098),
        (1_797_250_000, 6_250_000),
        (1_926_652_000, 6_700_000),
    ]
    assert infer_value_usd_multiplier(holdings) == 1.0
