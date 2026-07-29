"""
Purpose: Unit tests for HTML report render and write (no AWS).
Author(s): John Reed
"""

import datetime

from aws_tag_check import render_html_report, write_html_report


def _sample_violations():
    return [
        {
            "region": "us-west-2",
            "instance_id": "i-2",
            "name": "west",
            "tag_key": "Product",
            "tag_value": "missing product",
            "issue": "missing",
        },
        {
            "region": "us-east-1",
            "instance_id": "i-1",
            "name": '<script>x</script>',
            "tag_key": "Environment",
            "tag_value": "prod",
            "issue": "invalid",
        },
    ]


def test_render_clean_run_no_tables():
    html_body = render_html_report(
        [],
        datetime.date(2026, 7, 29),
        summary={"regions_scanned": 3, "instances_seen": 10},
    )
    assert "AWS Tag Check Report" in html_body
    assert "2026-07-29" in html_body
    assert "All tags clean" in html_body
    assert "<table" not in html_body
    assert "Region us-east-1" not in html_body


def test_render_only_regions_with_violations():
    html_body = render_html_report(
        _sample_violations(),
        datetime.date(2026, 7, 29),
        summary={
            "regions_scanned": 5,
            "instances_seen": 2,
            "region_skips": [
                {"region": "eu-west-1", "code": "UnauthorizedOperation"}
            ],
        },
    )
    assert "Region us-east-1" in html_body
    assert "Region us-west-2" in html_body
    assert "Region eu-west-1" not in html_body  # skip is not a table section
    assert "Skipped regions: eu-west-1" in html_body
    assert html_body.count("<table") == 2
    assert "i-1" in html_body
    assert "i-2" in html_body


def test_render_escapes_html():
    html_body = render_html_report(_sample_violations(), datetime.date.today())
    assert "<script>x</script>" not in html_body
    assert "&lt;script&gt;x&lt;/script&gt;" in html_body


def test_render_guidance_url():
    html_body = render_html_report(
        [],
        datetime.date.today(),
        guidance_url="https://example.com/tags",
    )
    assert "https://example.com/tags" in html_body
    assert "More detail:" in html_body


def test_write_html_report(tmp_path):
    path = tmp_path / "index.html"
    body = render_html_report([], datetime.date.today())
    write_html_report(str(path), body)
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    assert "AWS Tag Check Report" in text
