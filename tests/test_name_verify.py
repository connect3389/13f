from thirteenf.scrape.name_verify import (
    extract_filing_manager_name_from_primary_html,
    verify_filer_identity,
)


def test_display_name_mismatch_does_not_block_in_fail_mode():
    nv = verify_filer_identity(
        expected_display="Cascade Investment (Bill Gates)",
        sec_submissions_name="CASCADE INVESTMENT LLC",
        cover_primary_name="CASCADE INVESTMENT LLC",
        mode="fail",
    )
    assert nv.allow_ingest is True
    assert nv.status == "ok"
    assert any("仅展示标签" in m for m in nv.messages)


def test_cover_sec_mismatch_blocks_in_fail_mode():
    nv = verify_filer_identity(
        expected_display="Foo",
        sec_submissions_name="BAR LLC",
        cover_primary_name="BAZ LLC",
        mode="fail",
    )
    assert nv.allow_ingest is False
    assert nv.status == "fail_cover"


def test_html_entity_in_cover_name():
    html = b"""
    <table summary="Filing Manager Information">
    <tr><td class="FormText">Name:</td><td class="FormData">H&amp;H International Investment, LLC</td></tr>
    </table>
    """
    assert extract_filing_manager_name_from_primary_html(html) == (
        "H&H International Investment, LLC"
    )
    nv = verify_filer_identity(
        expected_display="H&H International Investment (段永平)",
        sec_submissions_name="H&H International Investment, LLC",
        cover_primary_name=extract_filing_manager_name_from_primary_html(html),
        mode="fail",
    )
    assert nv.allow_ingest is True
