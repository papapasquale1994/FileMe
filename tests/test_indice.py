"""Test dell'indicizzazione: i file entrano nell'indice, al secondo giro si
rifà solo ciò che è cambiato, e nessuna connessione di rete viene tentata."""

import hashlib
import os
from pathlib import Path

import pytest
from conftest import ModelloFinto

from fileme import config
from fileme.cli import main
from fileme.embedding import ModelloEmbedding, ModelloMancante, modello_presente
from fileme.estrazione import dividi_in_frasi
from fileme.indice import Indice, indicizza

CARTELLA_ESEMPI = Path(__file__).parent.parent / "esempi" / "documenti"


@pytest.fixture
def documenti(tmp_path):
    """Una cartella con tre piccoli documenti di testo."""
    cartella = tmp_path / "documenti"
    (cartella / "casa").mkdir(parents=True)
    (cartella / "bolletta_luce.txt").write_text("Bolletta della luce di marzo: 63 euro.")
    (cartella / "casa" / "contratto.txt").write_text("Contratto di affitto dell'appartamento.")
    (cartella / "ricetta.txt").write_text("Ricetta del ragù della nonna.")
    return cartella


@pytest.fixture
def indice(tmp_path):
    return Indice(tmp_path / "indice")


def stati(esiti) -> dict[str, str]:
    """Da una lista di esiti a {nome file: stato}, comodo da confrontare."""
    return {e.percorso.name: e.stato for e in esiti}


def contenuto_indice(indice: Indice) -> list[str]:
    return indice._raccolta.get(include=["documents"])["documents"]


# --- Prima indicizzazione --------------------------------------------------------


def test_prima_indicizzazione(documenti, indice, modello_finto):
    esiti = list(indicizza(documenti, indice, modello_finto))
    assert stati(esiti) == {
        "bolletta_luce.txt": "nuovo",
        "contratto.txt": "nuovo",
        "ricetta.txt": "nuovo",
    }
    assert indice.numero_chunk() == 3
    # Il percorso completo di ogni file è salvato nell'indice
    assert set(indice.file_indicizzati()) == {
        str((documenti / "bolletta_luce.txt").resolve()),
        str((documenti / "casa" / "contratto.txt").resolve()),
        str((documenti / "ricetta.txt").resolve()),
    }
    # Nome del file e cartella entrano nel testo trasformato in vettore
    assert any(t.startswith("File: contratto (cartella casa)") for t in modello_finto.testi_codificati)
    # ...ma nell'indice resta il testo originale, da mostrare come estratto
    assert "Contratto di affitto dell'appartamento." in contenuto_indice(indice)


def frasi_nell_indice(indice: Indice) -> list[str]:
    return indice._frasi.get(include=["documents"])["documents"]


def test_le_frasi_degli_estratti_sono_preparate(tmp_path, indice):
    cartella = tmp_path / "doc"
    cartella.mkdir()
    (cartella / "contratto.txt").write_text(
        "Il contratto di locazione dura quattro anni a partire da settembre. "
        "Il canone mensile è di seicento euro da pagare entro il giorno cinque."
    )
    modello = ModelloFinto()
    list(indicizza(cartella, indice, modello))

    frasi = indice.frasi_dei_chunk([indice._raccolta.get()["ids"][0]])
    (testi_vettori,) = frasi.values()
    assert [testo for testo, _ in testi_vettori] == [
        "Il contratto di locazione dura quattro anni a partire da settembre.",
        "Il canone mensile è di seicento euro da pagare entro il giorno cinque.",
    ]
    # Ogni frase ha il suo vettore, calcolato dal modello sulla frase da sola
    assert testi_vettori[0][1] == pytest.approx(modello.codifica_documenti([testi_vettori[0][0]])[0])


def test_documento_lungo_frasi_salvate_a_blocchi(tmp_path, indice):
    cartella = tmp_path / "doc"
    cartella.mkdir()
    (cartella / "lungo.txt").write_text(" ".join(f"Questa è la frase numero {i} del documento." for i in range(60)))
    indice._max_per_volta = 7  # come un limite di Chroma molto basso
    list(indicizza(cartella, indice, ModelloFinto()))
    # Tutte le frasi di tutti i chunk (i chunk si sovrappongono: alcune frasi stanno in due)
    attese = [f for chunk in contenuto_indice(indice) for f in dividi_in_frasi(chunk)]
    assert indice.numero_chunk() > 1
    assert sorted(frasi_nell_indice(indice)) == sorted(attese)


# --- Indicizzazioni successive: solo ciò che è cambiato -------------------------------


def test_seconda_volta_non_rifa_nulla(documenti, indice):
    list(indicizza(documenti, indice, ModelloFinto()))
    secondo_modello = ModelloFinto()
    esiti = list(indicizza(documenti, indice, secondo_modello))
    assert set(stati(esiti).values()) == {"invariato"}
    assert secondo_modello.testi_codificati == []  # nessun vettore ricalcolato
    assert indice.numero_chunk() == 3


def test_file_modificato_viene_sostituito(documenti, indice):
    list(indicizza(documenti, indice, ModelloFinto()))
    (documenti / "ricetta.txt").write_text("Ricetta del tiramisù.")
    esiti = list(indicizza(documenti, indice, ModelloFinto()))
    assert stati(esiti)["ricetta.txt"] == "modificato"
    testi = contenuto_indice(indice)
    assert "Ricetta del tiramisù." in testi
    assert "Ricetta del ragù della nonna." not in testi  # la versione vecchia è sparita
    assert indice.numero_chunk() == 3
    assert "Ricetta del tiramisù." in frasi_nell_indice(indice)
    assert "Ricetta del ragù della nonna." not in frasi_nell_indice(indice)


def test_file_con_nuova_data_ma_stesso_contenuto(documenti, indice):
    list(indicizza(documenti, indice, ModelloFinto()))
    ricetta = documenti / "ricetta.txt"
    os.utime(ricetta, (1_700_000_000, 1_700_000_000))  # cambia solo la data
    modello = ModelloFinto()
    esiti = list(indicizza(documenti, indice, modello))
    assert stati(esiti)["ricetta.txt"] == "invariato"
    assert modello.testi_codificati == []
    # La nuova data è stata memorizzata: la prossima volta basta il controllo veloce
    assert indice.file_indicizzati()[str(ricetta.resolve())].modificato == 1_700_000_000


def test_indice_di_una_versione_precedente_viene_completato(documenti, indice):
    """File indicizzati prima che FileMe preparasse le frasi degli estratti:
    alla prossima indicizzazione vengono rifatti una volta, poi basta."""
    list(indicizza(documenti, indice, ModelloFinto()))
    # Riporto l'indice com'era nella versione precedente: niente frasi e niente segno
    indice._frasi.delete(where={"percorso": {"$ne": ""}})
    ids = indice._raccolta.get()["ids"]
    indice._raccolta.update(ids=ids, metadatas=[{"estratti_pronti": False}] * len(ids))

    esiti = list(indicizza(documenti, indice, ModelloFinto()))
    assert set(stati(esiti).values()) == {"aggiornato"}
    assert len(frasi_nell_indice(indice)) == 3
    assert indice.numero_chunk() == 3

    modello = ModelloFinto()
    assert set(stati(indicizza(documenti, indice, modello)).values()) == {"invariato"}
    assert modello.testi_codificati == []


def test_file_cancellato_esce_dall_indice(documenti, indice):
    list(indicizza(documenti, indice, ModelloFinto()))
    (documenti / "ricetta.txt").unlink()
    esiti = list(indicizza(documenti, indice, ModelloFinto()))
    assert stati(esiti)["ricetta.txt"] == "rimosso"
    assert indice.numero_chunk() == 2
    assert "Ricetta del ragù della nonna." not in frasi_nell_indice(indice)  # anche le sue frasi


def test_le_altre_cartelle_non_vengono_toccate(tmp_path, documenti, indice):
    altra = tmp_path / "altra"
    altra.mkdir()
    (altra / "nota.txt").write_text("Una nota in un'altra cartella.")
    list(indicizza(documenti, indice, ModelloFinto()))
    list(indicizza(altra, indice, ModelloFinto()))
    # Reindicizzo solo la prima cartella: la nota dell'altra deve restare
    esiti = list(indicizza(documenti, indice, ModelloFinto()))
    assert "nota.txt" not in stati(esiti)
    assert str((altra / "nota.txt").resolve()) in indice.file_indicizzati()


def test_file_senza_testo_o_rotti_non_entrano(documenti, indice):
    (documenti / "vuoto.txt").write_text("   ")
    (documenti / "rotto.docx").write_bytes(b"non sono un docx")
    esiti = list(indicizza(documenti, indice, ModelloFinto()))
    assert stati(esiti)["vuoto.txt"] == "senza testo"
    assert stati(esiti)["rotto.docx"] == "errore"
    assert indice.numero_chunk() == 3  # solo i tre file buoni


def test_un_file_svuotato_esce_dall_indice(documenti, indice):
    list(indicizza(documenti, indice, ModelloFinto()))
    (documenti / "ricetta.txt").write_text("")
    esiti = list(indicizza(documenti, indice, ModelloFinto()))
    assert stati(esiti)["ricetta.txt"] == "senza testo"
    assert indice.numero_chunk() == 2


def test_l_indice_resta_salvato_su_disco(tmp_path, documenti):
    list(indicizza(documenti, Indice(tmp_path / "indice"), ModelloFinto()))
    riaperto = Indice(tmp_path / "indice")  # come chiudere e riaprire il programma
    assert riaperto.numero_chunk() == 3


# --- Sicurezza ------------------------------------------------------------------


def test_i_file_non_vengono_modificati(documenti, indice):
    file = sorted(documenti.rglob("*.txt"))
    prima = [(hashlib.sha256(f.read_bytes()).hexdigest(), f.stat().st_mtime) for f in file]
    list(indicizza(documenti, indice, ModelloFinto()))
    dopo = [(hashlib.sha256(f.read_bytes()).hexdigest(), f.stat().st_mtime) for f in file]
    assert prima == dopo
    assert len(list(documenti.rglob("*"))) == 4  # nessun file nuovo: 3 file + la sottocartella "casa"


def test_nessuna_connessione_di_rete(tmp_path, rete_bloccata):
    indice = Indice(tmp_path / "indice")
    esiti = list(indicizza(CARTELLA_ESEMPI, indice, ModelloFinto()))
    assert len(esiti) == 24
    assert rete_bloccata == []  # nessun tentativo di collegarsi a internet


def test_tutti_i_documenti_di_esempio(tmp_path):
    esiti = list(indicizza(CARTELLA_ESEMPI, Indice(tmp_path / "indice"), ModelloFinto()))
    assert {e.stato for e in esiti} == {"nuovo"}


# --- Modello ---------------------------------------------------------------------


def test_senza_modello_scaricato_un_messaggio_chiaro(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CARTELLA_MODELLI", tmp_path / "modelli_vuoti")
    with pytest.raises(ModelloMancante, match="fileme scarica-modello"):
        ModelloEmbedding().codifica_domanda("ciao")


@pytest.mark.skipif(not modello_presente(), reason="modello non scaricato (fileme scarica-modello)")
def test_modello_vero_funziona_offline(rete_bloccata):
    """Gira solo dove il modello è stato scaricato (es. sul tuo computer)."""
    modello = ModelloEmbedding()
    domanda = modello.codifica_domanda("contratto di affitto")
    simile, diverso = modello.codifica_documenti(
        ["Contratto di locazione dell'appartamento", "Ricetta del tiramisù"]
    )
    assert len(domanda) == 768
    prodotto = lambda a, b: sum(x * y for x, y in zip(a, b))  # noqa: E731
    assert prodotto(domanda, simile) > prodotto(domanda, diverso)  # "affitto" ~ "locazione"
    assert rete_bloccata == []


# --- Comando da terminale ----------------------------------------------------------


def test_comando_indicizza(tmp_path, documenti, monkeypatch, capsys):
    monkeypatch.setattr(config, "CARTELLA_INDICE", tmp_path / "indice")
    monkeypatch.setattr("fileme.cli.ModelloEmbedding", ModelloFinto)

    main(["indicizza", str(documenti)])
    uscita = capsys.readouterr().out
    # Path(...) scrive il percorso come il sistema in uso: casa\contratto.txt su Windows
    assert f"[nuovo]       {Path('casa', 'contratto.txt')} (1 chunk)" in uscita
    assert "nuovo: 3 | modificato: 0 | invariato: 0" in uscita
    assert "Chunk nell'indice: 3" in uscita

    main(["indicizza", str(documenti)])
    assert "nuovo: 0 | modificato: 0 | invariato: 3" in capsys.readouterr().out


def test_comando_indicizza_senza_modello(tmp_path, documenti, monkeypatch):
    monkeypatch.setattr(config, "CARTELLA_INDICE", tmp_path / "indice")
    monkeypatch.setattr(config, "CARTELLA_MODELLI", tmp_path / "modelli_vuoti")
    with pytest.raises(SystemExit, match="fileme scarica-modello"):
        main(["indicizza", str(documenti)])
