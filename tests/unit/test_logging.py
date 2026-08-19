import logging

from jarvis.logging_config import configure_logging


def test_logging_configuration_limits_http_client_verbosity() -> None:
    configure_logging("DEBUG")

    assert logging.getLogger().level == logging.DEBUG
    assert logging.getLogger("httpx").level == logging.WARNING
    assert logging.getLogger("httpcore").level == logging.WARNING
