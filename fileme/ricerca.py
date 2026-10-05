"""Ricerca: da una descrizione in linguaggio naturale ai file più pertinenti.

Come funziona:
1. la domanda diventa un vettore, con lo stesso modello usato per i documenti;
2. l'indice restituisce i chunk con il vettore più vicino;
3. i chunk vengono raggruppati per file: il punteggio di un file è quello
   del suo chunk migliore;
4. per ogni file scegliamo, dentro il chunk migliore, la frase più vicina alla
   domanda: è l'estratto che ti mostriamo. Le frasi e i loro vettori sono già
   nell'indice, preparati durante l'indicizzazione: qui basta confrontarli.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from fileme.embedding import Modello
from fileme.indice import ChunkTrovato, Indice, prepara_frasi


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
    estratti = frasi_piu_vicine([vettore] * len(primi), primi, indice, modello)
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


def frasi_piu_vicine(
    vettori_domanda: list[list[float]], chunk: list[ChunkTrovato], indice: Indice, modello: Modello
) -> list[str]:
    """Per ogni chunk, la sua frase più vicina al vettore della domanda corrispondente.

    Le frasi si leggono già pronte dall'indice. Passano dal modello solo quelle
    dei chunk indicizzati da una versione precedente di FileMe, che non le
    hanno ancora (finché non si rilancia `fileme indicizza`).
    """
    pronte = indice.frasi_dei_chunk([c.id for c in chunk])
    mancanti = [c for c in chunk if c.id not in pronte]
    if mancanti:
        pronte.update(zip([c.id for c in mancanti], prepara_frasi([c.testo for c in mancanti], modello)))

    scelte = []
    for vettore_domanda, trovato in zip(vettori_domanda, chunk):
        frasi = pronte[trovato.id]
        punteggi = [somiglianza(vettore_domanda, vettore) for _, vettore in frasi]
        scelte.append(frasi[punteggi.index(max(punteggi))][0] if frasi else "")
    return scelte


def somiglianza(a: list[float], b: list[float]) -> float:
    # I vettori hanno lunghezza 1, quindi il prodotto scalare è la somiglianza.
    return sum(x * y for x, y in zip(a, b))
