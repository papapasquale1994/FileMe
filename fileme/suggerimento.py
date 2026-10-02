"""Suggerimento contestuale: da una situazione ("un'azienda mi chiede il
curriculum") ai documenti che servono.

Come funziona:
1. cerchiamo nella frase le parole chiave delle situazioni conosciute
   (fileme/situazioni.py): vince la situazione con più parole trovate;
2. per ogni documento che serve in quella situazione cerchiamo il file più
   adatto, mescolando la descrizione del documento con la tua frase;
3. ogni documento riceve un file diverso;
4. se nessuna situazione è riconosciuta, cerchiamo direttamente la frase,
   come fa `fileme cerca`.
"""

from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from fileme import config
from fileme.embedding import Modello
from fileme.indice import ChunkTrovato, Indice
from fileme.ricerca import Risultato, cerca, file_piu_simili, frasi_piu_vicine
from fileme.situazioni import SITUAZIONI, Situazione


@dataclass
class Suggerimento:
    situazione: Situazione | None  # None = nessuna situazione riconosciuta
    parole_riconosciute: list[str] = field(default_factory=list)
    # Per ogni documento necessario: il file proposto (None se l'indice non ne ha abbastanza)
    documenti: list[tuple[str, Risultato | None]] = field(default_factory=list)
    # Solo se nessuna situazione è riconosciuta: la ricerca diretta della frase
    risultati_diretti: list[Risultato] = field(default_factory=list)


def suggerisci(
    contesto: str, indice: Indice, modello: Modello, situazioni: list[Situazione] = SITUAZIONI
) -> Suggerimento:
    riconosciuta = riconosci_situazione(contesto, situazioni)
    if riconosciuta is None:
        return Suggerimento(None, risultati_diretti=cerca(contesto, indice, modello))
    situazione, parole = riconosciuta

    vettore_contesto = modello.codifica_domanda(contesto)
    usati: set[Path] = set()
    scelte: list[tuple[str, list[float], ChunkTrovato | None]] = []
    for documento, descrizione in situazione.documenti.items():
        vettore = _mescola(modello.codifica_domanda(descrizione), vettore_contesto)
        # Chiediamo qualche file in più, per poter saltare quelli già proposti
        candidati = file_piu_simili(vettore, indice, numero=len(situazione.documenti) + 1)
        scelto = next((c for c in candidati if c.percorso not in usati), None)
        if scelto:
            usati.add(scelto.percorso)
        scelte.append((documento, vettore, scelto))

    # Estratti calcolati alla fine, tutti insieme e solo per i file scelti
    trovati = [(vettore, scelto) for _, vettore, scelto in scelte if scelto]
    estratti = iter(frasi_piu_vicine([v for v, _ in trovati], [c.testo for _, c in trovati], modello))
    documenti = [
        (documento, Risultato(c.percorso, c.tipo, c.somiglianza, next(estratti)) if c else None)
        for documento, _, c in scelte
    ]
    return Suggerimento(situazione, parole, documenti)


def riconosci_situazione(
    contesto: str, situazioni: list[Situazione] = SITUAZIONI
) -> tuple[Situazione, list[str]] | None:
    """La situazione con più parole chiave nella frase, e le parole trovate.

    A parità vince quella che viene prima nell'elenco. None se nessuna corrisponde.
    """
    parole = parole_normalizzate(contesto)
    migliore: Situazione | None = None
    trovate_migliore: list[str] = []
    for situazione in situazioni:
        trovate = [p for p in parole if any(_corrisponde(p, chiave) for chiave in situazione.parole_chiave)]
        if len(trovate) > len(trovate_migliore):
            migliore, trovate_migliore = situazione, trovate
    return (migliore, trovate_migliore) if migliore else None


def parole_normalizzate(testo: str) -> list[str]:
    """Parole minuscole e senza accenti: "Città d'Italia" -> ["citta", "d", "italia"]."""
    senza_accenti = unicodedata.normalize("NFKD", testo.lower())
    senza_accenti = "".join(c for c in senza_accenti if not unicodedata.combining(c))
    return re.findall(r"\w+", senza_accenti)


def _corrisponde(parola: str, chiave: str) -> bool:
    # Chiavi lunghe: basta l'inizio ("colloqu" -> "colloquio"). Chiavi corte: identiche.
    return parola.startswith(chiave) if len(chiave) >= 5 else parola == chiave


def _mescola(vettore_documento: list[float], vettore_contesto: list[float]) -> list[float]:
    """Media pesata dei due vettori, riportata a lunghezza 1."""
    peso = config.PESO_CONTESTO
    misto = [(1 - peso) * d + peso * c for d, c in zip(vettore_documento, vettore_contesto)]
    norma = math.sqrt(sum(x * x for x in misto)) or 1.0
    return [x / norma for x in misto]
