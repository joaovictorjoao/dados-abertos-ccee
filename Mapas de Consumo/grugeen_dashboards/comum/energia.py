"""Impede a suspensão do Windows durante execuções longas (no-op fora do Windows)."""

_ES_CONTINUOUS = 0x80000000
_ES_SYSTEM_REQUIRED = 0x00000001


def prevent_sleep() -> None:
    """Impede que o Windows entre em espera/hibernação durante a execução."""
    try:
        import ctypes
        ctypes.windll.kernel32.SetThreadExecutionState(
            _ES_CONTINUOUS | _ES_SYSTEM_REQUIRED
        )
    except Exception:
        pass  # não-Windows ou sem permissão — ignora silenciosamente


def restore_sleep() -> None:
    """Restaura a gestão de energia normal do Windows."""
    try:
        import ctypes
        ctypes.windll.kernel32.SetThreadExecutionState(_ES_CONTINUOUS)
    except Exception:
        pass
