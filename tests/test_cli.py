"""Test di base: il comando `fileme` si avvia e mostra la configurazione."""

from fileme import config
from fileme.cli import main


def test_info_mostra_modello_e_formati(capsys):
    main(["info"])
    uscita = capsys.readouterr().out
    assert config.MODELLO_EMBEDDING in uscita
    assert ".pdf" in uscita


def test_senza_comando_mostra_aiuto(capsys):
    main([])
    assert "comandi" in capsys.readouterr().out
