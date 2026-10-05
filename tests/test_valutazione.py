"""Test della valutazione: lettura del file di query, conteggi, soglia
consigliata e comando `fileme valuta`."""

from pathlib import Path

import pytest
from conftest import ModelloFinto

from fileme import config
from fileme.cli import main
from fileme.embedding import ModelloEmbedding, modello_presente
from fileme.indice import Indice, indicizza
from fileme.ricerca import Risultato
from fileme.valutazione import (
    EsitoQuery,
    Query,
    attesi_non_indicizzati,
    corrisponde,
    leggi_query,
    riepiloga,
    soglia_consigliata,
    valuta,
)

RADICE = Path(__file__).parent.parent
CARTELLA_ESEMPI = RADICE / "esempi" / "documenti"
QUERY_ESEMPI = RADICE / "valutazione" / "query_esempi.csv"


@pytest.fixture(scope="module")
def indice_esempi(tmp_path_factory):
    indice = Indice(tmp_path_factory.mktemp("indice"))
    list(indicizza(CARTELLA_ESEMPI, indice, ModelloFinto()))
    return indice


def scrivi_query(cartella: Path, testo: str, codifica: str = "utf-8") -> Path:
    percorso = cartella / "query.csv"
    percorso.write_bytes(testo.encode(codifica))
    return percorso


# --- Il file di query ------------------------------------------------------------------


def test_file_di_query_degli_esempi():
    queries = leggi_query(QUERY_ESEMPI)
    assert len([q for q in queries if q.attesi]) == 20  # le 20 query del brief
    assert len([q for q in queries if not q.attesi]) == 4  # documenti che non esistono
    assert queries[0].domanda == "il curriculum per candidature nel turismo"
    assert queries[0].attesi == ["CV_2024_def.pdf", "Resume_Giulia_Ferri_EN.pdf"]


def test_i_file_attesi_degli_esempi_esistono_davvero(indice_esempi):
    # Protegge da errori di battitura nel file di query
    assert attesi_non_indicizzati(leggi_query(QUERY_ESEMPI), indice_esempi) == []


def test_commenti_righe_vuote_e_codifica_di_excel(tmp_path):
    testo = "# commento\n\ndomanda;file_attesi;note\nla bolletta più cara;bolletta.pdf;\n"
    queries = leggi_query(scrivi_query(tmp_path, testo, codifica="cp1252"))  # come la salva Excel
    assert queries == [Query(4, "la bolletta più cara", ["bolletta.pdf"])]


def test_nessuno_vuol_dire_documento_inesistente(tmp_path):
    queries = leggi_query(scrivi_query(tmp_path, "domanda;file_attesi\nil passaporto;nessuno\n"))
    assert queries[0].attesi == []


@pytest.mark.parametrize(
    "testo, errore",
    [
        ("domanda;file_attesi\n;cv.pdf\n", "riga 2: manca la domanda"),
        ("domanda;file_attesi\nil mio cv\n", "riga 2: manca il file atteso"),
        ("domanda;file_attesi\nil mio cv;\n", "riga 2: manca il file atteso"),
        ("query;file\nil mio cv;cv.pdf\n", "riga 1: la prima riga deve essere"),
        ("# solo commenti\n", "vuoto"),
    ],
)
def test_errori_spiegati_con_il_numero_di_riga(tmp_path, testo, errore):
    with pytest.raises(ValueError, match=errore):
        leggi_query(scrivi_query(tmp_path, testo))


# --- Confronto tra file trovato e file atteso ------------------------------------------------


@pytest.mark.parametrize(
    "atteso, giusto",
    [
        ("CV.pdf", True),
        ("cv.PDF", True),  # maiuscole e minuscole non contano
        ("lavoro/CV.pdf", True),  # con la cartella
        ("lavoro\\CV.pdf", True),  # con la barra di Windows
        ("casa/CV.pdf", False),  # cartella sbagliata
        ("V.pdf", False),  # non basta la fine del nome
    ],
)
def test_corrisponde(atteso, giusto):
    assert corrisponde(Path("/home/mario/lavoro/CV.pdf"), atteso) is giusto


# --- Conteggi e soglia ------------------------------------------------------------------------


def esito(posizione: int | None, punteggi: list[float], attesi=("x.pdf",)) -> EsitoQuery:
    """Un esito costruito a mano: `posizione` è dove compare il file giusto."""
    risultati = [Risultato(Path(f"/doc/{i}.pdf"), "pdf", p, "") for i, p in enumerate(punteggi)]
    return EsitoQuery(Query(1, "domanda", list(attesi)), risultati, posizione, secondi=0.1)


def test_riepilogo_conta_bene():
    esiti = [
        esito(1, [0.9, 0.8, 0.7]),
        esito(3, [0.9, 0.8, 0.7]),
        esito(4, [0.9, 0.8, 0.7, 0.6]),  # trovato, ma non nei primi 3
        esito(None, [0.9, 0.8, 0.7]),
        esito(None, [0.75, 0.7], attesi=()),  # documento inesistente: non conta nel punteggio
    ]
    riepilogo = riepiloga(esiti)
    assert riepilogo.query_valutate == 4
    assert riepilogo.nei_primi == 2
    assert riepilogo.al_primo_posto == 1
    assert riepilogo.obiettivo == 3  # 70% di 4, arrotondato per eccesso
    assert riepilogo.punteggi_giusti == [0.9, 0.7, 0.6]
    assert riepilogo.punteggi_inesistenti == [0.75]


def test_obiettivo_14_su_20():
    assert riepiloga([esito(1, [0.9])] * 20).obiettivo == 14


def test_soglia_consigliata_a_meta_strada():
    riepilogo = riepiloga([esito(1, [0.86]), esito(1, [0.90]), esito(None, [0.78], attesi=())])
    assert soglia_consigliata(riepilogo) == pytest.approx(0.82)


def test_nessuna_soglia_se_i_gruppi_si_sovrappongono():
    riepilogo = riepiloga([esito(1, [0.80]), esito(None, [0.85], attesi=())])
    assert soglia_consigliata(riepilogo) is None


# --- Valutazione vera e propria (modello finto) ------------------------------------------------


def test_valuta_trova_le_posizioni(indice_esempi):
    queries = [
        Query(1, "ricetta del sugo di carne della nonna", ["ricetta_nonna.txt"]),
        Query(2, "ricetta del sugo di carne della nonna", ["file_che_non_esiste.pdf"]),
    ]
    trovato, mancato = valuta(queries, indice_esempi, ModelloFinto())
    assert trovato.posizione == 1 and trovato.nei_primi
    assert mancato.posizione is None and not mancato.nei_primi
    assert len(trovato.risultati) == 5


def test_segnala_i_file_attesi_scritti_male(indice_esempi):
    queries = [Query(7, "ricetta", ["ricetta_nona.txt"])]  # manca una "n"
    assert attesi_non_indicizzati(queries, indice_esempi) == [(queries[0], "ricetta_nona.txt")]


# --- Comando da terminale ---------------------------------------------------------------------


@pytest.fixture
def cli_con_modello_finto(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CARTELLA_INDICE", tmp_path / "indice_principale")
    monkeypatch.setattr("fileme.cli.ModelloEmbedding", ModelloFinto)
    return tmp_path / "indice_principale"


def test_comando_valuta_sugli_esempi(cli_con_modello_finto, capsys):
    main(["valuta", str(QUERY_ESEMPI), "--cartella", str(CARTELLA_ESEMPI)])
    uscita = capsys.readouterr().out
    assert "24 file, 27 chunk" in uscita
    assert "[OK]  1°  ricetta del sugo di carne della nonna" in uscita
    assert "Risultato: " in uscita and " su 20 nei primi 3" in uscita
    assert "Traguardo MVP (almeno 14 su 20 nei primi 3)" in uscita
    assert "il mio passaporto  ->  primo risultato:" in uscita
    assert "Tempo per ricerca: media" in uscita
    assert "ATTENZIONE" not in uscita
    # L'indice principale non è stato toccato
    assert not cli_con_modello_finto.exists()


def test_comando_valuta_segnala_nomi_sbagliati(cli_con_modello_finto, tmp_path, capsys):
    query = scrivi_query(tmp_path, "domanda;file_attesi\nricetta;ricetta_nona.txt\n")
    main(["valuta", str(query), "--cartella", str(CARTELLA_ESEMPI)])
    assert "riga 2: ricetta_nona.txt" in capsys.readouterr().out


def test_comando_valuta_errori(cli_con_modello_finto, tmp_path):
    with pytest.raises(SystemExit, match="non esiste"):
        main(["valuta", str(tmp_path / "manca.csv")])
    with pytest.raises(SystemExit, match="riga 2: manca la domanda"):
        main(["valuta", str(scrivi_query(tmp_path, "domanda;file_attesi\n;cv.pdf\n"))])
    with pytest.raises(SystemExit, match="L'indice è vuoto"):
        main(["valuta", str(QUERY_ESEMPI)])  # senza --cartella usa l'indice principale, vuoto


# --- Con il modello vero (solo dove è stato scaricato) -----------------------------------------


@pytest.mark.skipif(not modello_presente(), reason="modello non scaricato (fileme scarica-modello)")
def test_modello_vero_traguardo_mvp_sugli_esempi(tmp_path, rete_bloccata):
    modello = ModelloEmbedding()
    indice = Indice(tmp_path / "indice")
    list(indicizza(CARTELLA_ESEMPI, indice, modello))
    riepilogo = riepiloga(valuta(leggi_query(QUERY_ESEMPI), indice, modello))
    assert riepilogo.nei_primi >= riepilogo.obiettivo  # almeno 14 su 20 nei primi 3
    assert riepilogo.tempo_massimo < 3
    assert rete_bloccata == []
