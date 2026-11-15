import pytest

from app.detectors.response_scanner import ResponseScanner, luhn_valid, verhoeff_valid

rs = ResponseScanner(redact_emails=True)


@pytest.mark.parametrize(
    "text",
    [
        "key sk-proj-abcdefghijklmnopqrstuvwx",
        "AKIAIOSFODNN7EXAMPLE",
        "ghp_" + "a" * 36,
        "password=hunter2222",
        "-----BEGIN PRIVATE KEY-----\nabc\n-----END PRIVATE KEY-----",
    ],
)
def test_secrets_are_redacted(text):
    res = rs.scan(text)
    assert res["has_secret"] and res["score"] >= 80
    assert "hunter2222" not in res["sanitized_response"] and "AKIAIOSFODNN7" not in res["sanitized_response"]


def test_pii_validators_avoid_false_positives():
    assert luhn_valid("4111111111111111") and not luhn_valid("4111111111111112")
    assert verhoeff_valid("236323632360") and not verhoeff_valid("236323632361")
    assert rs.scan("revenue 4111 1111 1111 1112 units")["flagged"] is False
    res = rs.scan("card 4111 1111 1111 1111, mail bob@example.com")
    assert res["flagged"] and not res["has_secret"] and res["score"] == 40.0


def test_placeholders_not_redacted():
    assert not rs.scan("api_key=YOUR_API_KEY")["flagged"]


def test_own_credentials_are_never_echoed(monkeypatch):
    monkeypatch.setenv("SOME_SERVICE_TOKEN", "super-secret-value-12345")
    scanner = ResponseScanner()
    res = scanner.scan("The token is super-secret-value-12345 okay")
    assert "super-secret-value-12345" not in res["sanitized_response"] and res["has_secret"]
