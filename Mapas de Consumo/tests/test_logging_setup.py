import logging
from grugeen_dashboards.comum.logging_setup import setup_logging


def test_setup_logging_cria_arquivo_com_prefixo(tmp_path):
    logger = setup_logging("teste_dash", tmp_path)
    logger.info("linha de teste")
    for h in logger.handlers:
        h.flush()
    arquivos = list(tmp_path.glob("teste_dash_*.log"))
    assert len(arquivos) == 1
    assert "linha de teste" in arquivos[0].read_text(encoding="utf-8")


def test_setup_logging_retorna_logger():
    logger = setup_logging("x", None)
    assert isinstance(logger, logging.Logger)
