"""Interfaccia web locale: una pagina nel browser per cercare i documenti.

Il server ascolta SOLO sull'indirizzo 127.0.0.1, cioè sul tuo computer:
nessun altro dispositivo può collegarsi. La pagina non scarica nulla da
internet. Il modello si carica una volta all'avvio e resta in memoria, così
ogni ricerca successiva è veloce.

Usa solo la libreria standard di Python (http.server): nessun pacchetto in più.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from fileme import config
from fileme.embedding import Modello
from fileme.indice import Indice
from fileme.ricerca import Risultato, cerca
from fileme.suggerimento import suggerisci

PAGINA = Path(__file__).parent / "pagina.html"
INDIRIZZO = "127.0.0.1"  # solo questo computer

# La pagina può usare solo codice e stili scritti dentro di sé, e parlare
# solo con questo server: niente font, script o immagini da internet.
POLITICA_CONTENUTI = (
    "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
    "connect-src 'self'; img-src 'self' data:; base-uri 'none'; form-action 'none'"
)


class App:
    """Tiene in memoria indice e modello e risponde alle richieste della pagina."""

    def __init__(self, indice: Indice, modello: Modello):
        self.indice = indice
        self.modello = modello
        self._lucchetto = threading.Lock()  # una ricerca alla volta: il modello lavora meglio così

    def stato(self) -> dict:
        return {"file": len(self.indice.file_indicizzati()), "chunk": self.indice.numero_chunk()}

    def cerca(self, domanda: str) -> dict:
        with self._lucchetto:
            inizio = time.perf_counter()
            risultati = cerca(domanda, self.indice, self.modello)
            secondi = time.perf_counter() - inizio
        return {"risultati": [_come_dizionario(r) for r in risultati], "secondi": round(secondi, 2)}

    def suggerisci(self, contesto: str) -> dict:
        with self._lucchetto:
            inizio = time.perf_counter()
            esito = suggerisci(contesto, self.indice, self.modello)
            secondi = time.perf_counter() - inizio
        return {
            "situazione": esito.situazione.nome if esito.situazione else None,
            "parole": esito.parole_riconosciute,
            "documenti": [
                {
                    "documento": documento,
                    "risultato": _come_dizionario(r) if r else None,
                    "incerto": bool(r) and r.punteggio < config.SOGLIA_SUGGERIMENTO,
                }
                for documento, r in esito.documenti
            ],
            "risultati": [_come_dizionario(r) for r in esito.risultati_diretti],
            "secondi": round(secondi, 2),
        }

    def apri(self, percorso: str, cartella: bool) -> None:
        """Apre un file dell'indice (o la sua cartella) con i programmi del computer.

        Solo i file presenti nell'indice: così nessuno può usare questa
        funzione per aprire altro.
        """
        if percorso not in self.indice.file_indicizzati():
            raise PermissionError(percorso)
        file = Path(percorso)
        if not file.exists():
            raise FileNotFoundError(percorso)
        apri_nel_sistema(file, cartella)


def _come_dizionario(risultato: Risultato) -> dict:
    return {
        "nome": risultato.percorso.name,
        "percorso": str(risultato.percorso),
        "cartella": str(risultato.percorso.parent),
        "tipo": risultato.tipo,
        "punteggio": round(risultato.punteggio, 2),
        "estratto": risultato.estratto,
        "esiste": risultato.percorso.exists(),
    }


def apri_nel_sistema(file: Path, cartella: bool) -> None:
    """Apre il file con il suo programma predefinito, o la cartella che lo contiene."""
    if sys.platform == "win32":
        if cartella:
            subprocess.Popen(f'explorer /select,"{file}"')
        else:
            os.startfile(file)  # type: ignore[attr-defined]  # esiste solo su Windows
    elif sys.platform == "darwin":
        subprocess.Popen(["open", "-R", str(file)] if cartella else ["open", str(file)])
    else:
        subprocess.Popen(["xdg-open", str(file.parent if cartella else file)])


class Gestore(BaseHTTPRequestHandler):
    """Riceve le richieste del browser e risponde con la pagina o con dati JSON."""

    server: ServerFileMe

    def do_GET(self) -> None:
        if not self._host_valido():
            return self._errore(403, "Accesso consentito solo da questo computer.")
        url = urlparse(self.path)
        domanda = parse_qs(url.query).get("q", [""])[0].strip()
        app = self.server.app

        if url.path == "/":
            return self._invia(200, PAGINA.read_bytes(), "text/html; charset=utf-8")
        if url.path == "/api/stato":
            return self._json(200, app.stato())
        if url.path in ("/api/cerca", "/api/suggerisci"):
            if not domanda:
                return self._errore(400, "Scrivi cosa cerchi.")
            dati = app.cerca(domanda) if url.path == "/api/cerca" else app.suggerisci(domanda)
            return self._json(200, dati)
        return self._errore(404, "Pagina inesistente.")

    def do_POST(self) -> None:
        if not self._host_valido() or not self._origine_valida():
            return self._errore(403, "Accesso consentito solo da questo computer.")
        if urlparse(self.path).path != "/api/apri":
            return self._errore(404, "Pagina inesistente.")
        # Un'intestazione speciale che un sito esterno non può aggiungere da solo.
        if self.headers.get("X-FileMe") != "1":
            return self._errore(403, "Richiesta non valida.")
        lunghezza = int(self.headers.get("Content-Length") or 0)
        if not 0 < lunghezza <= 10_000:
            return self._errore(400, "Richiesta non valida.")
        try:
            dati = json.loads(self.rfile.read(lunghezza))
            self.server.app.apri(str(dati["percorso"]), cartella=bool(dati.get("cartella")))
        except (ValueError, KeyError, TypeError):
            return self._errore(400, "Richiesta non valida.")
        except PermissionError:
            return self._errore(403, "Questo file non è nell'indice.")
        except FileNotFoundError:
            return self._errore(404, "Il file non è più qui: rilancia fileme indicizza.")
        return self._json(200, {"ok": True})

    # --- controlli di sicurezza ---------------------------------------------------

    def _indirizzi_validi(self) -> set[str]:
        porta = self.server.server_address[1]
        return {f"127.0.0.1:{porta}", f"localhost:{porta}"}

    def _host_valido(self) -> bool:
        # Blocca i siti che provano a farsi passare per "questo computer".
        return self.headers.get("Host", "") in self._indirizzi_validi()

    def _origine_valida(self) -> bool:
        origine = self.headers.get("Origin")
        return origine is None or origine in {f"http://{h}" for h in self._indirizzi_validi()}

    # --- risposte -------------------------------------------------------------------

    def _invia(self, codice: int, corpo: bytes, tipo: str) -> None:
        self.send_response(codice)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(corpo)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", POLITICA_CONTENUTI)
        self.end_headers()
        self.wfile.write(corpo)

    def _json(self, codice: int, dati: dict) -> None:
        corpo = json.dumps(dati, ensure_ascii=False).encode("utf-8")
        self._invia(codice, corpo, "application/json; charset=utf-8")

    def _errore(self, codice: int, messaggio: str) -> None:
        self._json(codice, {"errore": messaggio})

    def log_message(self, formato: str, *args) -> None:
        pass  # niente righe di log nel terminale a ogni richiesta


class ServerFileMe(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, app: App, porta: int):
        super().__init__((INDIRIZZO, porta), Gestore)
        self.app = app


def avvia(app: App, porta: int, apri_browser: bool = True) -> None:
    """Accende il server e lo tiene acceso finché non premi Ctrl+C."""
    server = ServerFileMe(app, porta)
    indirizzo = f"http://{INDIRIZZO}:{server.server_address[1]}"
    print(f"\nFileMe è pronto: {indirizzo}")
    print("Lascia aperta questa finestra. Per spegnere FileMe premi Ctrl+C.")
    if apri_browser:
        threading.Timer(1.0, webbrowser.open, [indirizzo]).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nFileMe spento.")
    finally:
        server.server_close()
