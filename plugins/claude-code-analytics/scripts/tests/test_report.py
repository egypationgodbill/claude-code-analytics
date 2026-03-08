import pytest
from report import generate_report


def test_generate_report_injects_data(tmp_path):
    template = tmp_path / "template.html"
    template.write_text("<html>/*__REPORT_DATA__*/</html>")
    output = tmp_path / "report.html"

    data = {"key": "value", "count": 42}
    result = generate_report(data, str(output), str(template))

    assert result == str(output)
    content = output.read_text()
    assert "window.__REPORT_DATA__" in content
    assert '"key": "value"' in content


def test_generate_report_missing_template(tmp_path):
    output = tmp_path / "report.html"
    with pytest.raises(SystemExit):
        generate_report({}, str(output), str(tmp_path / "nonexistent.html"))
