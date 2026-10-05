"""Test dell'interfaccia web: la pagina, le risposte di ricerca e suggerimento,
e le protezioni (solo questo computer, "Apri" solo per i file dell'indice)."""

import http.client
import json
import threading
from pathlib import Path

import pytest
from conftest import ModelloFinto

from fileme import config, web
from fileme.indice import Indice, indicizza

CARTELLA_ESEMPI = Path(__file__).parent.parent / "esempi" / "documenti"


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    """Un server FileMe vero, su una porta libera, con i documenti di esempio."""
    indice = Indice(tmp_path_factory.mktemp("indice"))
    list(indicizza(CARTELLA_ESEMPI, indice, ModelloFinto()))
    server = web.ServerFileMe(web.App(indice, ModelloFinto()), porta=0)  # 0 = una porta libera qualsiasi
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield server
    server.shutdown()
    server.server_close()


def richiesta(server, metodo, percorso, corpo=None, intestazioni=None):
    """Fa una richiesta al server come farebbe il browser; restituisce (codice, testo)."""
    porta = server.server_address[1]
    connessione = http.client.HTTPConnection("127.0.0.1", porta, timeout=10)
    intestazioni = {"Host": f"127.0.0.1:{porta}", **(intestazioni or {})}
    connessione.request(metodo, percorso, body=corpo, headers=intestazioni)
    risposta = connessione.getresponse()
    return risposta.status, risposta.read().decode("utf-8"), dict(risposta.getheaders())


def apri(server, percorso, **intestazioni):
    corpo = json.dumps({"percorso": percorso, "cartella": False})
    base = {"Content-Type": "application/json", "X-FileMe": "1"}
    return richiesta(server, "POST", "/api/apri", corpo, {**base, **intestazioni})


# --- La pagina ------------------------------------------------------------------------


def test_la_pagina_si_apre_e_non_usa_internet(server):
    codice, html, intestazioni = richiesta(server, "GET", "/")
    assert codice == 200
    assert "<title>FileMe</title>" in html
    # Nessun font, script o immagine scaricato da internet
    assert "http://" not in html and "https://" not in html
    assert "default-src 'none'" in intestazioni["Content-Security-Policy"]


def test_ascolta_solo_su_questo_computer(server):
    assert server.server_address[0] == "127.0.0.1"


def test_stato(server):
    codice, testo, _ = richiesta(server, "GET", "/api/stato")
    assert codice == 200
    assert json.loads(testo) == {"file": 24, "chunk": 27}


# --- Ricerca e suggerimento --------------------------------------------------------------


def test_cerca(server):
    codice, testo, _ = richiesta(server, "GET", "/api/cerca?q=ricetta%20rag%C3%B9%20tagliatelle")
    assert codice == 200
    dati = json.loads(testo)
    primo = dati["risultati"][0]
    assert primo["nome"] == "ricetta_nonna.txt"
    assert primo["estratto"] == "Servire con tagliatelle fresche all'uovo, mai con gli spaghetti!"
    assert primo["esiste"] is True
    assert Path(primo["cartella"]) == Path(primo["percorso"]).parent
    assert len(dati["risultati"]) == 5
    assert dati["secondi"] >= 0


def test_suggerisci_con_situazione(server, monkeypatch):
    monkeypatch.setattr(config, "SOGLIA_SUGGERIMENTO", 0.0)
    codice, testo, _ = richiesta(server, "GET", "/api/suggerisci?q=mi%20chiedono%20il%20curriculum")
    dati = json.loads(testo)
    assert codice == 200
    assert dati["situazione"] == "candidatura di lavoro"
    assert dati["parole"] == ["curriculum"]
    assert [d["documento"] for d in dati["documenti"]][0] == "Curriculum vitae"
    assert not any(d["incerto"] for d in dati["documenti"])


def test_suggerisci_senza_situazione(server):
    _, testo, _ = richiesta(server, "GET", "/api/suggerisci?q=ricetta%20della%20torta")
    dati = json.loads(testo)
    assert dati["situazione"] is None
    assert dati["risultati"][0]["nome"] == "ricetta_nonna.txt"


def test_gli_esempi_della_pagina_vengono_riconosciuti(server):
    _, html, _ = richiesta(server, "GET", "/")
    for esempio in ["un'azienda mi chiede il curriculum", "devo fare il 730", "vado in vacanza in Giappone"]:
        assert esempio in html
        _, testo, _ = richiesta(server, "GET", "/api/suggerisci?q=" + esempio.replace(" ", "%20"))
        assert json.loads(testo)["situazione"] is not None, esempio


def test_domanda_vuota(server):
    codice, testo, _ = richiesta(server, "GET", "/api/cerca?q=%20")
    assert codice == 400
    assert json.loads(testo) == {"errore": "Scrivi cosa cerchi."}


# --- Protezioni -------------------------------------------------------------------------


def test_rifiuta_chi_finge_di_essere_questo_computer(server):
    codice, _, _ = richiesta(server, "GET", "/api/stato", intestazioni={"Host": "sito-cattivo.example"})
    assert codice == 403


def test_apri_un_file_dell_indice(server, monkeypatch):
    aperti = []
    monkeypatch.setattr(web, "apri_nel_sistema", lambda file, cartella: aperti.append((file, cartella)))
    percorso = str((CARTELLA_ESEMPI / "Desktop" / "ricetta_nonna.txt").resolve())
    codice, _, _ = apri(server, percorso)
    assert codice == 200
    assert aperti == [(Path(percorso), False)]


def test_apri_rifiuta_file_fuori_dall_indice(server, monkeypatch):
    aperti = []
    monkeypatch.setattr(web, "apri_nel_sistema", lambda file, cartella: aperti.append(file))
    codice, testo, _ = apri(server, str(Path(__file__).resolve()))  # esiste, ma non è nell'indice
    assert codice == 403
    assert "non è nell'indice" in json.loads(testo)["errore"]
    assert aperti == []


def test_apri_rifiuta_richieste_da_altri_siti(server, monkeypatch):
    aperti = []
    monkeypatch.setattr(web, "apri_nel_sistema", lambda file, cartella: aperti.append(file))
    percorso = str((CARTELLA_ESEMPI / "Desktop" / "ricetta_nonna.txt").resolve())
    # Senza l'intestazione speciale (un modulo di un altro sito non può aggiungerla)
    codice, _, _ = richiesta(server, "POST", "/api/apri", json.dumps({"percorso": percorso}),
                             {"Content-Type": "application/json"})
    assert codice == 403
    # Con l'origine di un altro sito
    codice, _, _ = apri(server, percorso, Origin="https://sito-cattivo.example")
    assert codice == 403
    assert aperti == []


def test_apri_richiesta_malformata(server):
    porta = server.server_address[1]
    codice, _, _ = richiesta(server, "POST", "/api/apri", "non è json",
                             {"X-FileMe": "1", "Host": f"127.0.0.1:{porta}"})
    assert codice == 400


def test_pagina_inesistente(server):
    codice, _, _ = richiesta(server, "GET", "/segreti")
    assert codice == 404
