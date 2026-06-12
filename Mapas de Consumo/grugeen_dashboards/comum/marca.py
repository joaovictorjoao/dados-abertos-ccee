"""Recursos visuais da marca Grugeen (logo embutido)."""

import base64
from pathlib import Path


def logo_data_uri(logo_path: Path) -> str:
    """Retorna o logo PNG como data URI base64; string vazia se não existir."""
    try:
        data = base64.b64encode(Path(logo_path).read_bytes()).decode()
        return f"data:image/png;base64,{data}"
    except Exception:
        return ""
