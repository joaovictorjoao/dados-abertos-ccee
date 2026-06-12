"""Funções auxiliares compartilhadas entre as seções do dashboard."""

from .formato import (
    formatar_br, fmt_gwh, fmt_mwh, fmt_mwh_hab, fmt_cons_100k, fmt_pop,
)
from .geo import normalizar, geocodificar
from .http import fetch, baixar_recurso
from .logging_setup import setup_logging
from .marca import logo_data_uri
from .energia import prevent_sleep, restore_sleep

__all__ = [
    "formatar_br", "fmt_gwh", "fmt_mwh", "fmt_mwh_hab", "fmt_cons_100k", "fmt_pop",
    "normalizar", "geocodificar",
    "fetch", "baixar_recurso",
    "setup_logging",
    "logo_data_uri",
    "prevent_sleep", "restore_sleep",
]
