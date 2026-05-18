from thirteenf.cik import parse_cik_input, validate_cik_input


def test_parse_cik() -> None:
    assert parse_cik_input("1697748") == "0001697748"
    assert parse_cik_input("0001697748") == "0001697748"


def test_reject_non_digits() -> None:
    assert parse_cik_input("0001697748a") is None
    ok, cik, err = validate_cik_input("ARK")
    assert not ok and cik is None and "字母" in err
