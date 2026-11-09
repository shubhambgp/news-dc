import logging

from pythonjsonlogger.json import JsonFormatter


def setup_logging(level: str = "INFO") -> None:
    """Route all logs (including uvicorn's) through one JSON handler on stdout."""
    handler = logging.StreamHandler()
    handler.setFormatter(
        JsonFormatter("%(asctime)s %(levelname)s %(name)s %(message)s", timestamp=True)
    )
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())
    # One line per outbound request drowns the ingest logs; failures are logged by the caller.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(name)
        lg.handlers = []
        lg.propagate = True
