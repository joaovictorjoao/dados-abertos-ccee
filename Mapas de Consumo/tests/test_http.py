import gzip
import io
import logging
import pytest
from grugeen_dashboards.comum import http


class _FakeResp:
    def __init__(self, data: bytes):
        self._data = data
    def read(self):
        return self._data
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False


def test_fetch_descomprime_gzip(monkeypatch):
    payload = b"conteudo original"
    comprimido = gzip.compress(payload)
    monkeypatch.setattr(http.urllib.request, "urlopen",
                        lambda req, timeout=30: _FakeResp(comprimido))
    assert http.fetch("http://x") == payload


def test_fetch_passa_bytes_crus_quando_nao_gzip(monkeypatch):
    monkeypatch.setattr(http.urllib.request, "urlopen",
                        lambda req, timeout=30: _FakeResp(b"texto puro"))
    assert http.fetch("http://x") == b"texto puro"


def test_baixar_recurso_usa_cache_existente(tmp_path, monkeypatch):
    destino = tmp_path / "arq.bin"
    destino.write_bytes(b"ja existe")
    def _boom(*a, **k):
        raise AssertionError("não deveria baixar quando há cache")
    monkeypatch.setattr(http, "fetch", _boom)
    http.baixar_recurso("http://x", destino, logging.getLogger("t"))
    assert destino.read_bytes() == b"ja existe"


def test_baixar_recurso_grava_quando_ausente(tmp_path, monkeypatch):
    destino = tmp_path / "novo.bin"
    monkeypatch.setattr(http, "fetch", lambda url, timeout=30: b"baixado")
    http.baixar_recurso("http://x", destino, logging.getLogger("t"))
    assert destino.read_bytes() == b"baixado"


def test_baixar_recurso_propaga_erro(tmp_path, monkeypatch):
    destino = tmp_path / "falha.bin"
    def _erro(*a, **k):
        raise OSError("rede caiu")
    monkeypatch.setattr(http, "fetch", _erro)
    with pytest.raises(OSError):
        http.baixar_recurso("http://x", destino, logging.getLogger("t"))
