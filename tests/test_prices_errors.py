from thirteenf.prices.errors import user_message_for_fetch_error


def test_yfinance_not_installed_message() -> None:
    assert "yfinance" in user_message_for_fetch_error("yfinance_not_installed")
