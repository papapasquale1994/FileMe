"""Ricerca: da una descrizione in linguaggio naturale ai file più pertinenti.

Come funziona:
1. la domanda diventa un vettore, con lo stesso modello usato per i documenti;
2. l'indice restituisce i chunk con il vettore più vicino;
3. i chunk vengono raggruppati per file: il punteggio di un file è quello
   del suo chunk migliore;
4. per ogni file scegliamo, dentro il chunk migliore, la frase più vicina alla
   domanda: è l'estratto che ti mostriamo.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path

from fileme.embedding import Modello
from fileme.indice import ChunkTrovato, Indice


@dataclass
class Risultato:
    percorso: Path
    tipo: str
    punteggio: float  # più è alto (massimo 1), più il file è vicino alla descrizione
    estratto: str  # la frase del file più vicina alla descrizione


def cerca(domanda: str, indice: Indice, modello: Modello, numero: int = 5) -> list[Risultato]:
    """I `numero` file più pertinenti per la domanda, dal migliore al peggiore."""
    vettore = modello.codifica_domanda(domanda)
    primi = file_piu_simili(vettore, indice, numero)
    estratti = frasi_piu_vicine([vettore] * len(primi), [c.testo for c in primi], modello)
    return [
        Risultato(c.percorso, c.tipo, c.somiglianza, estratto)
        for c, estratto in zip(primi, estratti)
    ]


def file_piu_simili(vettore: list[float], indice: Indice, numero: int) -> list[ChunkTrovato]:
    """Il chunk migliore di ciascuno dei `numero` file più vicini al vettore."""
    # Chiediamo più chunk dei file che ci servono: un file lungo può
    # occupare da solo molte delle prime posizioni.
    chunk = indice.chunk_simili(vettore, quanti=max(50, numero * 10))

    migliori: dict[Path, ChunkTrovato] = {}
    for trovato in chunk:  # sono già in ordine, dal più simile
        migliori.setdefault(trovato.percorso, trovato)  # teniamo solo il primo di ogni file
    return list(migliori.values())[:numero]


def frasi_piu_vicine(vettori_domanda: list[list[float]], testi: list[str], modello: Modello) -> list[str]:
    """Per ogni testo, la frase più vicina al vettore della domanda corrispondente.

    Tutte le frasi passano dal modello in un colpo solo: è molto più veloce
    che un testo alla volta.
    """
    frasi_per_testo = [dividi_in_frasi(testo) for testo in testi]
    tutte = [frase for frasi in frasi_per_testo for frase in frasi]
    if not tutte:
        return [""] * len(testi)
    vettori = iter(modello.codifica_documenti(tutte))

    scelte = []
    for vettore_domanda, frasi in zip(vettori_domanda, frasi_per_testo):
        punteggi = [somiglianza(vettore_domanda, next(vettori)) for _ in frasi]
        scelte.append(frasi[punteggi.index(max(punteggi))] if frasi else "")
    return scelte


def dividi_in_frasi(testo: str, min_parole: int = 8, max_parole: int = 30) -> list[str]:
    """Divide un testo in frasi leggibili come estratto.

    Taglia dopo . ! ? ;  — unisce i pezzi troppo corti (es. "Art. 1 -") al
    successivo e spezza quelli troppo lunghi (es. righe di tabelle senza punti).
    """
    frasi: list[str] = []
    corrente: list[str] = []
    for pezzo in re.split(r"(?<=[.!?;])\s+", testo):
        corrente += pezzo.split()
        if len(corrente) >= min_parole:
            # Se è troppo lunga la taglio in parti uguali (es. 35 parole -> 18 + 17,
            # non 30 + 5), così non restano frammenti minuscoli.
            parti = math.ceil(len(corrente) / max_parole)
            lunghezza = math.ceil(len(corrente) / parti)
            frasi += [" ".join(corrente[i : i + lunghezza]) for i in range(0, len(corrente), lunghezza)]
            corrente = []
    if corrente:
        frasi.append(" ".join(corrente))
    return frasi


def somiglianza(a: list[float], b: list[float]) -> float:
    # I vettori hanno lunghezza 1, quindi il prodotto scalare è la somiglianza.
    return sum(x * y for x, y in zip(a, b))
