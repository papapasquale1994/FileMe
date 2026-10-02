"""Test del suggerimento contestuale: riconoscimento della situazione, un file
diverso per ogni documento necessario, ricerca diretta se non si riconosce nulla."""

from pathlib import Path

import pytest
from conftest import ModelloFinto

from fileme import config
from fileme.cli import main
from fileme.embedding import ModelloEmbedding, modello_presente
from fileme.indice import Indice, indicizza
from fileme.situazioni import SITUAZIONI
from fileme.suggerimento import parole_normalizzate, riconosci_situazione, suggerisci

CARTELLA_ESEMPI = Path(__file__).parent.parent / "esempi" / "documenti"


@pytest.fixture(scope="module")
def indice_esempi(tmp_path_factory):
    indice = Indice(tmp_path_factory.mktemp("indice"))
    list(indicizza(CARTELLA_ESEMPI, indice, ModelloFinto()))
    return indice


def proposti(suggerimento) -> dict[str, str | None]:
    """{documento necessario: nome del file proposto}"""
    return {doc: (r.percorso.name if r else None) for doc, r in suggerimento.documenti}


# --- Riconoscere la situazione -------------------------------------------------------


@pytest.mark.parametrize(
    "frase, situazione",
    [
        ("un'azienda mi chiede il curriculum", "candidatura di lavoro"),  # l'esempio del brief
        ("domani ho un colloquio in un hotel", "candidatura di lavoro"),
        ("devo fare il 730 al CAF", "dichiarazione dei redditi"),
        ("domani ho una visita dal medico", "salute e visite mediche"),
        ("prenoto il volo per il Giappone", "viaggio"),
        ("il padrone di casa vuole la caparra", "affitto e casa"),
        ("sto organizzando il trasloco", "trasloco"),
        ("quanto ho pagato di bolletta?", "bollette e consumi"),
        ("ho fatto un incidente con la macchina", "auto e incidenti"),
        ("chiedo un mutuo in banca", "mutuo o prestito"),
        ("Ho un COLLOQUIO", "candidatura di lavoro"),  # maiuscole
    ],
)
def test_riconosce_la_situazione(frase, situazione):
    trovata, parole = riconosci_situazione(frase)
    assert trovata.nome == situazione
    assert parole  # sappiamo dire quali parole l'hanno fatta riconoscere


def test_frase_senza_situazione():
    assert riconosci_situazione("ricetta della torta della nonna") is None


def test_parole_corte_devono_essere_identiche():
    # "auto" non deve scattare con "autore" o "automatico"
    assert riconosci_situazione("l'autore del libro automatico") is None


def test_vince_la_situazione_con_piu_parole():
    # "mediche" -> salute (1 parola); "detrarre" + "730" -> redditi (2 parole)
    trovata, parole = riconosci_situazione("devo detrarre le spese mediche nel 730")
    assert trovata.nome == "dichiarazione dei redditi"
    assert parole == ["detrarre", "730"]


def test_parole_normalizzate_senza_accenti():
    assert parole_normalizzate("Città d'Italia, PERCHÉ?") == ["citta", "d", "italia", "perche"]


# --- L'elenco delle situazioni è valido (utile se lo modifichi) -----------------------------


def test_elenco_situazioni_valido():
    nomi = [s.nome for s in SITUAZIONI]
    assert len(nomi) == len(set(nomi)), "due situazioni con lo stesso nome"
    gia_viste: dict[str, str] = {}
    for situazione in SITUAZIONI:
        assert situazione.parole_chiave, f"{situazione.nome}: nessuna parola chiave"
        assert situazione.documenti, f"{situazione.nome}: nessun documento"
        for chiave in situazione.parole_chiave:
            assert parole_normalizzate(chiave) == [chiave], (
                f"{situazione.nome}: '{chiave}' deve essere una parola sola, minuscola, senza accenti"
            )
            assert chiave not in gia_viste, f"'{chiave}' è sia in {gia_viste.get(chiave)} sia in {situazione.nome}"
            gia_viste[chiave] = situazione.nome


# --- Suggerire i file -------------------------------------------------------------------


def test_candidatura_un_file_diverso_per_ogni_documento(indice_esempi):
    suggerimento = suggerisci("un'azienda mi chiede il curriculum", indice_esempi, ModelloFinto())
    assert suggerimento.situazione.nome == "candidatura di lavoro"
    file = proposti(suggerimento)
    assert list(file) == ["Curriculum vitae", "Lettera di presentazione", "Referenze", "Attestati e certificati"]
    assert len(set(file.values())) == 4  # nessun file ripetuto
    assert file["Curriculum vitae"] in {"CV_2024_def.pdf", "curriculum_vecchio.docx"}
    assert file["Lettera di presentazione"] == "lettera_presentazione_hotel.docx"
    assert file["Attestati e certificati"] == "attestato_haccp.pdf"
    assert all(r.estratto for _, r in suggerimento.documenti)


def test_viaggio(indice_esempi):
    file = proposti(suggerisci("prenoto il volo per il Giappone", indice_esempi, ModelloFinto()))
    assert file["Biglietti e prenotazioni"] == "e-ticket_7F3KQ.pdf"
    assert file["Programma del viaggio"] == "itinerario_giappone.docx"


def test_senza_situazione_ricerca_diretta(indice_esempi):
    suggerimento = suggerisci("ricetta della torta della nonna", indice_esempi, ModelloFinto())
    assert suggerimento.situazione is None
    assert suggerimento.documenti == []
    assert suggerimento.risultati_diretti[0].percorso.name == "ricetta_nonna.txt"


def test_pochi_file_nell_indice(tmp_path):
    cartella = tmp_path / "doc"
    cartella.mkdir()
    (cartella / "cv.txt").write_text("Curriculum vitae: esperienze di lavoro.")
    indice = Indice(tmp_path / "indice")
    list(indicizza(cartella, indice, ModelloFinto()))
    file = proposti(suggerisci("mi chiedono il curriculum", indice, ModelloFinto()))
    assert file["Curriculum vitae"] == "cv.txt"
    assert list(file.values()).count(None) == 3  # gli altri documenti: nessun file disponibile


def test_nessuna_connessione_di_rete(indice_esempi, rete_bloccata):
    suggerisci("devo fare il 730", indice_esempi, ModelloFinto())
    assert rete_bloccata == []


# --- Comando da terminale ------------------------------------------------------------------


@pytest.fixture
def cli_con_modello_finto(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(config, "CARTELLA_INDICE", tmp_path / "indice")
    monkeypatch.setattr("fileme.cli.ModelloEmbedding", ModelloFinto)
    main(["indicizza", str(CARTELLA_ESEMPI)])
    capsys.readouterr()


def test_comando_suggerisci(cli_con_modello_finto, capsys, monkeypatch):
    monkeypatch.setattr(config, "SOGLIA_SUGGERIMENTO", 0.0)  # nessun file "incerto"
    main(["suggerisci", "un'azienda", "mi", "chiede", "il", "curriculum"])
    uscita = capsys.readouterr().out
    assert "Situazione riconosciuta: candidatura di lavoro (dalle parole «curriculum»)" in uscita
    assert "Lettera di presentazione\n   -> lettera_presentazione_hotel.docx" in uscita
    assert "INCERTO" not in uscita
    assert "s per il suggerimento" in uscita


def test_comando_suggerisci_segnala_i_file_incerti(cli_con_modello_finto, capsys, monkeypatch):
    monkeypatch.setattr(config, "SOGLIA_SUGGERIMENTO", 0.99)  # tutti sotto soglia
    main(["suggerisci", "mi chiedono il curriculum"])
    assert "INCERTO: forse non hai questo documento" in capsys.readouterr().out


def test_comando_suggerisci_senza_situazione(cli_con_modello_finto, capsys):
    main(["suggerisci", "ricetta della torta"])
    uscita = capsys.readouterr().out
    assert "Nessuna situazione dell'elenco riconosciuta" in uscita
    assert "1. ricetta_nonna.txt" in uscita


def test_comando_suggerisci_senza_frase_mostra_le_situazioni(capsys):
    main(["suggerisci"])
    uscita = capsys.readouterr().out
    for situazione in SITUAZIONI:
        assert f"- {situazione.nome}" in uscita


# --- Con il modello vero (solo dove è stato scaricato) ---------------------------------------


@pytest.mark.skipif(not modello_presente(), reason="modello non scaricato (fileme scarica-modello)")
def test_modello_vero_suggerisce_il_curriculum(tmp_path, rete_bloccata):
    modello = ModelloEmbedding()
    indice = Indice(tmp_path / "indice")
    list(indicizza(CARTELLA_ESEMPI, indice, modello))
    file = proposti(suggerisci("un'azienda chiede il curriculum", indice, modello))
    assert file["Curriculum vitae"] in {"CV_2024_def.pdf", "curriculum_vecchio.docx", "Resume_Giulia_Ferri_EN.pdf"}
    assert rete_bloccata == []
