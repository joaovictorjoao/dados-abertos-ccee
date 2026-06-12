"""Configuração de logging com arquivo por execução (timestamp) + stdout UTF-8."""

import logging
from datetime import datetime
from pathlib import Path


def setup_logging(prefixo: str, pasta_logs: Path | None) -> logging.Logger:
    """
    Configura logging em nível INFO. Se `pasta_logs` for informada, grava um
    arquivo `{prefixo}_{timestamp}.log` nela; sempre espelha em stdout (UTF-8).
    """
    handlers: list[logging.Handler] = []
    if pasta_logs is not None:
        pasta_logs = Path(pasta_logs)
        pasta_logs.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = pasta_logs / f"{prefixo}_{ts}.log"
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))

    handlers.append(logging.StreamHandler())

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        handlers=handlers,
        force=True,
    )
    return logging.getLogger(prefixo)
