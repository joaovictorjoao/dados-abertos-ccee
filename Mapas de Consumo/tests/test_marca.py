from grugeen_dashboards.comum.marca import logo_data_uri


def test_logo_inexistente_retorna_vazio(tmp_path):
    assert logo_data_uri(tmp_path / "nao_existe.png") == ""


def test_logo_existente_retorna_data_uri(tmp_path):
    png = tmp_path / "logo.png"
    png.write_bytes(b"\x89PNG\r\n\x1a\nfake")
    uri = logo_data_uri(png)
    assert uri.startswith("data:image/png;base64,")
    assert len(uri) > len("data:image/png;base64,")
