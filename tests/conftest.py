"""Strumenti condivisi dai test (pytest carica questo file automaticamente)."""

import hashlib
import math
import re
import socket

import pytest


class ModelloFinto:
    """Sostituisce il modello vero nei test: istantaneo e senza download.

    Ogni parola "accende" una casella del vettore: testi con parole in comune
    hanno vettori simili. Non capisce i sinonimi come il modello vero, ma
    basta per verificare che indicizzazione e ricerca funzionino.
    """

    DIMENSIONI = 256

    def __init__(self):
        self.testi_codificati: list[str] = []  # per controllare cosa è stato ricalcolato

    def codifica_documenti(self, testi: list[str]) -> list[list[float]]:
        self.testi_codificati += testi
        return [self._vettore(testo) for testo in testi]

    def codifica_domanda(self, testo: str) -> list[float]:
        return self._vettore(testo)

    def _vettore(self, testo: str) -> list[float]:
        vettore = [0.0] * self.DIMENSIONI
        for parola in re.findall(r"\w+", testo.lower()):
            vettore[int(hashlib.md5(parola.encode()).hexdigest(), 16) % self.DIMENSIONI] += 1
        norma = math.sqrt(sum(x * x for x in vettore)) or 1.0
        return [x / norma for x in vettore]


@pytest.fixture
def modello_finto():
    return ModelloFinto()


@pytest.fixture
def rete_bloccata(monkeypatch):
    """Durante il test ogni tentativo di connessione fallisce e viene annotato.

    Il test controlla poi che la lista dei tentativi sia vuota.
    """
    tentativi = []

    def connessione_vietata(self, indirizzo, *args, **kwargs):
        tentativi.append(indirizzo)
        raise OSError(f"FileMe ha provato a collegarsi a {indirizzo}")

    monkeypatch.setattr(socket.socket, "connect", connessione_vietata)
    monkeypatch.setattr(socket.socket, "connect_ex", connessione_vietata)
    return tentativi
