"""持仓表 CUSIP 汇总与权重重算。"""

from __future__ import annotations

import pandas as pd

from thirteenf.gui.institutions import (
    aggregate_holdings_by_cusip,
    recalculate_holdings_weight,
)


def test_aggregate_by_cusip_sums_shares_and_value() -> None:
    df = pd.DataFrame(
        [
            {
                "line_no": 1,
                "issuer": "APPLE INC",
                "title_of_class": "COM",
                "cusip": "037833100",
                "shares": 100.0,
                "value_as_reported": 1000.0,
                "investment_discretion": "DFND",
                "other_manager": "4",
            },
            {
                "line_no": 2,
                "issuer": "APPLE INC",
                "title_of_class": "COM",
                "cusip": "037833100",
                "shares": 200.0,
                "value_as_reported": 2000.0,
                "investment_discretion": "DFND",
                "other_manager": "1,2",
            },
        ]
    )
    out = aggregate_holdings_by_cusip(df)
    assert len(out) == 1
    assert out.iloc[0]["shares"] == 300.0
    assert out.iloc[0]["value_as_reported"] == 3000.0
    assert out.iloc[0]["xml_line_count"] == 2
    assert "investment_discretion" not in out.columns


def test_recalculate_holdings_weight() -> None:
    df = pd.DataFrame(
        {"value_as_reported": [1000.0, 3000.0], "weight": [0.5, 0.5]}
    )
    out = recalculate_holdings_weight(df)
    assert abs(out.iloc[0]["weight"] - 0.25) < 1e-9
    assert abs(out.iloc[1]["weight"] - 0.75) < 1e-9
