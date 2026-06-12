from grugeen_dashboards.comum import energia


def test_prevent_sleep_nao_levanta():
    # Em qualquer plataforma: não deve propagar exceção.
    energia.prevent_sleep()


def test_restore_sleep_nao_levanta():
    energia.restore_sleep()
