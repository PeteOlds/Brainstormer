"""Coverage for the small SMTP/console email helper."""

from unittest.mock import MagicMock, patch


def test_send_email_logs_in_dev_without_smtp(app, caplog):
    from app.services.email import send_email

    app.config["SMTP_HOST"] = None
    with app.app_context():
        send_email("to@example.com", "Subject", "Body")

    assert "Body" in caplog.text


def test_send_email_uses_smtp_tls_and_auth(app):
    from app.services.email import send_email

    app.config.update(
        SMTP_HOST="smtp.example.com",
        SMTP_PORT="2525",
        SMTP_FROM="from@example.com",
        SMTP_USER="user",
        SMTP_PASSWORD="pass",
        SMTP_USE_TLS="true",
    )
    smtp = MagicMock()
    smtp.__enter__.return_value = smtp
    with patch("app.services.email.smtplib.SMTP", return_value=smtp) as smtp_class:
        with app.app_context():
            send_email("to@example.com", "Subject", "Body", "<p>Body</p>")

    smtp_class.assert_called_once_with("smtp.example.com", 2525, timeout=15)
    smtp.starttls.assert_called_once()
    smtp.login.assert_called_once_with("user", "pass")
    message = smtp.send_message.call_args[0][0]
    assert message["Subject"] == "Subject"
    assert message["From"] == "from@example.com"
    assert message["To"] == "to@example.com"
    assert "Body" in message.as_string()


def test_send_email_skips_tls_and_auth_when_not_configured(app):
    from app.services.email import send_email

    app.config.update(
        SMTP_HOST="smtp.example.com",
        SMTP_PORT=None,
        SMTP_FROM=None,
        SMTP_USER=None,
        SMTP_PASSWORD=None,
        SMTP_USE_TLS="false",
    )
    smtp = MagicMock()
    smtp.__enter__.return_value = smtp
    with patch("app.services.email.smtplib.SMTP", return_value=smtp) as smtp_class:
        with app.app_context():
            send_email("to@example.com", "Subject", "Body")

    smtp_class.assert_called_once_with("smtp.example.com", 587, timeout=15)
    smtp.starttls.assert_not_called()
    smtp.login.assert_not_called()
    smtp.send_message.assert_called_once()


def test_config_falls_back_to_environment_outside_app_context(monkeypatch):
    from app.services.email import _config

    monkeypatch.delenv("SMTP_HOST", raising=False)
    assert _config("SMTP_HOST") is None
    monkeypatch.setenv("SMTP_HOST", "smtp.env.test")
    assert _config("SMTP_HOST") == "smtp.env.test"
