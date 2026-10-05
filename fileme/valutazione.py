"""Valutazione: quanto è brava la ricerca a trovare il file giusto?

Legge un file di query (domanda + file atteso), esegue ogni ricerca e misura:
- quante volte il file giusto è nei primi 3 risultati (il criterio dell'MVP);
- quante volte è al primo posto;
- quanto tempo richiede ogni ricerca;
- i punteggi dei file giusti e quelli dei documenti che non esistono, per
  tarare la soglia "INCERTO" di `fileme suggerisci`.
"""

from __future__ import annotations

import csv
import math
import time
from dataclasses import dataclass
from pathlib import Path

from fileme.embedding import Modello
from fileme.estrazione import decodifica_testo
from fileme.indice import Indice
from fileme.ricerca import Risultato, cerca

PRIMI = 3  # il file giusto deve essere tra i primi 3 risultati
TRAGUARDO = 0.7  # criterio dell'MVP: almeno 14 query su 20 (70%)
NESSUNO = "NESSUNO"  # nel file di query: "questo documento non esiste"


@dataclass
class Query:
    riga: int  # numero di riga nel file, per i messaggi di errore
    domanda: str
    attesi: list[str]  # vuota = il documento non esiste (NESSUNO)


@dataclass
class EsitoQuery:
    query: Query
    risultati: list[Risultato]
    posizione: int | None  # posizione del file giusto (1 = primo), None se non trovato
    secondi: float

    @property
    def nei_primi(self) -> bool:
        return self.posizione is not None and self.posizione <= PRIMI


@dataclass
class Riepilogo:
    query_valutate: int  # senza contare quelle NESSUNO
    nei_primi: int
    al_primo_posto: int
    tempo_medio: float
    tempo_massimo: float
    punteggi_giusti: list[float]  # punteggio del file giusto, quando è stato trovato
    punteggi_inesistenti: list[float]  # punteggio del primo risultato, per le query NESSUNO

    @property
    def obiettivo(self) -> int:
        """Quante query devono riuscire: 14 su 20."""
        return math.ceil(TRAGUARDO * self.query_valutate)


# --- Lettura del file di query ----------------------------------------------------


def leggi_query(percorso: Path) -> list[Query]:
    """Legge il file di query (CSV con ; come separatore). ValueError se è scritto male."""
    righe = decodifica_testo(percorso.read_bytes()).splitlines()
    utili = [(numero, riga) for numero, riga in enumerate(righe, start=1)
             if riga.strip() and not riga.lstrip().startswith("#")]
    if not utili:
        raise ValueError("il file è vuoto")

    numeri = [numero for numero, _ in utili]
    celle = list(csv.reader([riga for _, riga in utili], delimiter=";"))
    intestazione = [c.strip().lower() for c in celle[0]]
    if intestazione[:2] != ["domanda", "file_attesi"]:
        raise ValueError(f"riga {numeri[0]}: la prima riga deve essere  domanda;file_attesi;note")

    queries = []
    for numero, valori in zip(numeri[1:], celle[1:]):
        domanda = valori[0].strip() if valori else ""
        attesi = [a.strip() for a in valori[1].split("|") if a.strip()] if len(valori) > 1 else []
        if not domanda:
            raise ValueError(f"riga {numero}: manca la domanda")
        if not attesi:
            raise ValueError(f"riga {numero}: manca il file atteso (scrivi {NESSUNO} se non esiste)")
        if [a.upper() for a in attesi] == [NESSUNO]:
            attesi = []
        queries.append(Query(numero, domanda, attesi))
    return queries


# --- Esecuzione ----------------------------------------------------------------------


def corrisponde(percorso: Path, atteso: str) -> bool:
    """Il file trovato è quello atteso? Basta il nome ("CV.pdf") o la parte
    finale del percorso ("lavoro/CV.pdf"). Maiuscole e minuscole non contano."""
    trovato = percorso.as_posix().lower()
    atteso = atteso.replace("\\", "/").strip("/").lower()
    return trovato == atteso or trovato.endswith("/" + atteso)


def attesi_non_indicizzati(queries: list[Query], indice: Indice) -> list[tuple[Query, str]]:
    """File attesi che non sono nell'indice: di solito un nome scritto male."""
    indicizzati = [Path(p) for p in indice.file_indicizzati()]
    return [
        (query, atteso)
        for query in queries
        for atteso in query.attesi
        if not any(corrisponde(p, atteso) for p in indicizzati)
    ]


def valuta(queries: list[Query], indice: Indice, modello: Modello, numero: int = 5) -> list[EsitoQuery]:
    esiti = []
    for query in queries:
        inizio = time.perf_counter()
        risultati = cerca(query.domanda, indice, modello, numero)
        secondi = time.perf_counter() - inizio
        posizione = next(
            (i for i, r in enumerate(risultati, start=1)
             if any(corrisponde(r.percorso, atteso) for atteso in query.attesi)),
            None,
        )
        esiti.append(EsitoQuery(query, risultati, posizione, secondi))
    return esiti


def riepiloga(esiti: list[EsitoQuery]) -> Riepilogo:
    valutati = [e for e in esiti if e.query.attesi]
    inesistenti = [e for e in esiti if not e.query.attesi]
    tempi = [e.secondi for e in esiti] or [0.0]
    return Riepilogo(
        query_valutate=len(valutati),
        nei_primi=sum(e.nei_primi for e in valutati),
        al_primo_posto=sum(e.posizione == 1 for e in valutati),
        tempo_medio=sum(tempi) / len(tempi),
        tempo_massimo=max(tempi),
        punteggi_giusti=[e.risultati[e.posizione - 1].punteggio for e in valutati if e.posizione],
        punteggi_inesistenti=[e.risultati[0].punteggio for e in inesistenti if e.risultati],
    )


def soglia_consigliata(riepilogo: Riepilogo) -> float | None:
    """A metà strada tra il punteggio più alto di un documento inesistente e il
    più basso di un file giusto. None se i due gruppi si sovrappongono (o mancano)."""
    if not riepilogo.punteggi_giusti or not riepilogo.punteggi_inesistenti:
        return None
    massimo_sbagliato = max(riepilogo.punteggi_inesistenti)
    minimo_giusto = min(riepilogo.punteggi_giusti)
    if massimo_sbagliato >= minimo_giusto:
        return None
    return (massimo_sbagliato + minimo_giusto) / 2
