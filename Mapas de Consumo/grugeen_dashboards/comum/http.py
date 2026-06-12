"""Download de recursos com cache em disco e detecção automática de gzip."""

import gzip
import logging
import urllib.request
from pathlib import Path


def fetch(url: str, timeout: int = 30) -> bytes:
    """Baixa a URL e retorna bytes crus (descomprime gzip se necessário)."""
    req = urllib.request.Request(url, headers={"Accept-Encoding": "identity"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    return raw


def baixar_recurso(url: str, destino: Path, logger: logging.Logger) -> None:
    """Baixa `url` para `destino` se ainda não existir; loga e propaga erros."""
    destino = Path(destino)
    if destino.exists():
        logger.info("Cache: %s", destino.name)
        return
    logger.info("Baixando %s ...", destino.name)
    destino.parent.mkdir(parents=True, exist_ok=True)
    try:
        destino.write_bytes(fetch(url))
        logger.info("  %.1f KB", destino.stat().st_size / 1024)
    except Exception as exc:
        logger.error("Falha: %s — %s", destino.name, exc)
        raise
