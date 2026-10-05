"""Test della ricerca: i file giusti escono per primi, una volta sola, con un
estratto sensato; il comando funziona anche in modalità interattiva."""

import time
from pathlib import Path

import pytest
from conftest import ModelloFinto

from fileme import config
from fileme.cli import main
from fileme.embedding import ModelloEmbedding, modello_presente
from fileme.indice import Indice, indicizza
from fileme.ricerca import cerca

CARTELLA_ESEMPI = Path(__file__).parent.parent / "esempi" / "documenti"


@pytest.fixture(scope="module")
def indice_esempi(tmp_path_factory):
    """I 24 documenti di esempio, indicizzati una volta per tutti i test del file."""
    indice = Indice(tmp_path_factory.mktemp("indice"))
    list(indicizza(CARTELLA_ESEMPI, indice, ModelloFinto()))
    return indice


def nomi(risultati) -> list[str]:
    return [r.percorso.name for r in risultati]


# --- Qualità e forma dei risultati ---------------------------------------------------


@pytest.mark.parametrize(
    "domanda, file_atteso",
    [
        ("bolletta del gas per il riscaldamento", "documento(3).pdf"),
        ("ricetta del ragù con le tagliatelle", "ricetta_nonna.txt"),
        ("turni della reception a luglio", "turni_reception_luglio.xlsx"),
        ("washing machine pump filter", "WM-7400_manual_EN.pdf"),
    ],
)
def test_il_file_giusto_esce_per_primo(indice_esempi, domanda, file_atteso):
    risultati = cerca(domanda, indice_esempi, ModelloFinto())
    assert nomi(risultati)[0] == file_atteso


def test_cinque_file_diversi_in_ordine_di_punteggio(indice_esempi):
    # La tesi è divisa in 3 chunk: deve comparire comunque una volta sola
    risultati = cerca("turismo sostenibile stagionalità destinazioni costiere", indice_esempi, ModelloFinto())
    assert len(risultati) == 5
    assert len(set(nomi(risultati))) == 5
    assert nomi(risultati)[0] == "tesi_cap2_turismo_sostenibile.docx"
    punteggi = [r.punteggio for r in risultati]
    assert punteggi == sorted(punteggi, reverse=True)
    assert all(0 <= p <= 1 for p in punteggi)


def test_numero_di_risultati(indice_esempi):
    assert len(cerca("bolletta", indice_esempi, ModelloFinto(), numero=2)) == 2


def test_l_estratto_e_la_frase_piu_pertinente(indice_esempi):
    primo = cerca("tagliatelle fresche", indice_esempi, ModelloFinto())[0]
    assert primo.estratto == "Servire con tagliatelle fresche all'uovo, mai con gli spaghetti!"


def test_gli_estratti_sono_gia_pronti_nell_indice(indice_esempi):
    """Le frasi degli estratti sono state preparate durante l'indicizzazione:
    cercare non deve più passare dal modello per calcolarne i vettori."""
    modello = ModelloFinto()
    risultati = cerca("tagliatelle fresche", indice_esempi, modello)
    assert risultati[0].estratto == "Servire con tagliatelle fresche all'uovo, mai con gli spaghetti!"
    assert modello.testi_codificati == []  # solo la domanda è diventata un vettore


def test_indice_di_una_versione_precedente_funziona_ancora(tmp_path):
    """Un indice senza frasi pronte (creato prima di questa versione):
    l'estratto si calcola al momento, come si faceva prima."""
    indice = Indice(tmp_path / "indice")
    list(indicizza(CARTELLA_ESEMPI, indice, ModelloFinto()))
    indice._frasi.delete(where={"percorso": {"$ne": ""}})  # come se le frasi non ci fossero mai state

    modello = ModelloFinto()
    primo = cerca("tagliatelle fresche", indice, modello)[0]
    assert primo.estratto == "Servire con tagliatelle fresche all'uovo, mai con gli spaghetti!"
    assert modello.testi_codificati  # le frasi sono passate dal modello


def test_il_nome_del_file_aiuta_a_trovarlo(tmp_path):
    cartella = tmp_path / "doc"
    cartella.mkdir()
    # Il testo non dice "curriculum": lo dice solo il nome del file
    (cartella / "curriculum.txt").write_text("Esperienze: cameriera in pizzeria, barista.")
    (cartella / "spesa.txt").write_text("Latte, pane, uova, caffè.")
    indice = Indice(tmp_path / "indice")
    list(indicizza(cartella, indice, ModelloFinto()))
    assert nomi(cerca("curriculum", indice, ModelloFinto()))[0] == "curriculum.txt"


def test_indice_vuoto_nessun_risultato(tmp_path):
    assert cerca("qualsiasi cosa", Indice(tmp_path / "vuoto"), ModelloFinto()) == []


def test_nessuna_connessione_di_rete(indice_esempi, rete_bloccata):
    cerca("contratto di affitto", indice_esempi, ModelloFinto())
    assert rete_bloccata == []


# --- Comando da terminale -------------------------------------------------------------


@pytest.fixture
def cli_con_modello_finto(tmp_path, monkeypatch):
    """Il comando vero, con il modello finto e un indice in una cartella temporanea."""
    monkeypatch.setattr(config, "CARTELLA_INDICE", tmp_path / "indice")
    monkeypatch.setattr("fileme.cli.ModelloEmbedding", ModelloFinto)


def test_comando_cerca(cli_con_modello_finto, capsys):
    main(["indicizza", str(CARTELLA_ESEMPI)])
    capsys.readouterr()
    main(["cerca", "ricetta", "del", "ragù"])  # funziona anche senza virgolette
    uscita = capsys.readouterr().out
    assert 'Risultati per: "ricetta del ragù"' in uscita
    assert "1. ricetta_nonna.txt  (punteggio" in uscita
    assert f"Percorso: {CARTELLA_ESEMPI / 'Desktop' / 'ricetta_nonna.txt'}" in uscita
    assert "5. " in uscita
    assert "Tempo:" in uscita and "s per la ricerca" in uscita


def test_comando_cerca_interattivo(cli_con_modello_finto, capsys, monkeypatch):
    main(["indicizza", str(CARTELLA_ESEMPI)])
    capsys.readouterr()
    risposte = iter(["ricetta ragù", "gas riscaldamento", ""])  # riga vuota = esci
    monkeypatch.setattr("builtins.input", lambda _domanda: next(risposte))
    main(["cerca"])
    uscita = capsys.readouterr().out
    assert uscita.count("Risultati per:") == 2
    assert "1. ricetta_nonna.txt" in uscita
    assert "1. documento(3).pdf" in uscita


def test_comando_cerca_avvisa_se_il_file_non_c_e_piu(cli_con_modello_finto, tmp_path, capsys):
    cartella = tmp_path / "doc"
    cartella.mkdir()
    (cartella / "ricetta.txt").write_text("Ricetta del ragù.")
    main(["indicizza", str(cartella)])
    (cartella / "ricetta.txt").unlink()
    main(["cerca", "ricetta"])
    assert "il file non è più qui" in capsys.readouterr().out


def test_comando_cerca_con_indice_vuoto(cli_con_modello_finto):
    with pytest.raises(SystemExit, match="L'indice è vuoto"):
        main(["cerca", "qualcosa"])


# --- Con il modello vero (solo dove è stato scaricato) -------------------------------------


@pytest.mark.skipif(not modello_presente(), reason="modello non scaricato (fileme scarica-modello)")
def test_modello_vero_ricerca_veloce_e_pertinente(tmp_path, rete_bloccata):
    modello = ModelloEmbedding()
    indice = Indice(tmp_path / "indice")
    list(indicizza(CARTELLA_ESEMPI, indice, modello))

    inizio = time.perf_counter()
    risultati = cerca("il curriculum per candidature nel turismo", indice, modello)
    secondi = time.perf_counter() - inizio

    assert "CV_2024_def.pdf" in nomi(risultati)[:3]  # l'esempio del brief
    assert secondi < 3  # a modello già caricato
    assert rete_bloccata == []


def test_comando_cerca_numero_non_valido(cli_con_modello_finto):
    with pytest.raises(SystemExit, match="almeno 1"):
        main(["cerca", "-n", "0", "qualcosa"])
