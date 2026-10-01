"""Indice: il database (Chroma) dove salviamo, per ogni chunk, il suo vettore,
il suo testo e il percorso del file da cui viene.

L'indice sta in ~/.fileme/indice, sul tuo computer. Contiene i pezzi di testo
estratti (servono a mostrarti l'estratto nei risultati), non i file originali.
Se cancelli quella cartella, l'indice sparisce e i tuoi file restano dove sono.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Protocol

import chromadb
from chromadb.config import Settings

from fileme import config
from fileme.estrazione import estrai_documento, trova_file


class Modello(Protocol):
    """Quello che ci serve da un modello di embedding (vero o, nei test, finto)."""

    def codifica_documenti(self, testi: list[str]) -> list[list[float]]: ...


@dataclass
class InfoFile:
    """Ciò che ricordiamo di un file per capire, la volta dopo, se è cambiato."""

    dimensione: int  # in byte
    modificato: float  # data di ultima modifica
    impronta: str  # "hash" del contenuto: cambia se cambia anche un solo byte


# --- Il database ----------------------------------------------------------------


class Indice:
    def __init__(self, cartella: Path, modello: str = config.MODELLO_EMBEDDING):
        client = chromadb.PersistentClient(
            path=str(cartella),
            settings=Settings(anonymized_telemetry=False),  # niente statistiche inviate
        )
        # Una raccolta separata per ogni modello: vettori di modelli diversi
        # non sono confrontabili tra loro.
        self._raccolta = client.get_or_create_collection(
            name=nome_raccolta(modello),
            metadata={"hnsw:space": "cosine", "modello": modello},
            embedding_function=None,  # i vettori li calcoliamo noi
        )

    def file_indicizzati(self) -> dict[str, InfoFile]:
        """Tutti i file nell'indice: percorso -> dimensione, data, impronta."""
        # Basta guardare il primo chunk (posizione 0) di ogni file.
        risultato = self._raccolta.get(where={"posizione": 0}, include=["metadatas"])
        return {
            m["percorso"]: InfoFile(m["dimensione"], m["modificato"], m["impronta"])
            for m in risultato["metadatas"]
        }

    def aggiungi(
        self, percorso: Path, info: InfoFile, tipo: str, chunk: list[str], vettori: list[list[float]]
    ) -> None:
        chiave = str(percorso)
        codice = hashlib.sha1(chiave.encode()).hexdigest()[:16]
        self._raccolta.add(
            ids=[f"{codice}-{n}" for n in range(len(chunk))],
            embeddings=vettori,
            documents=chunk,
            metadatas=[
                {
                    "percorso": chiave,
                    "nome": percorso.name,
                    "tipo": tipo,
                    "posizione": n,  # numero del chunk nel file
                    "dimensione": info.dimensione,
                    "modificato": info.modificato,
                    "impronta": info.impronta,
                }
                for n in range(len(chunk))
            ],
        )

    def rimuovi(self, percorso: str) -> None:
        """Toglie dall'indice tutti i chunk di un file (il file vero non si tocca)."""
        self._raccolta.delete(where={"percorso": percorso})

    def aggiorna_data(self, percorso: str, modificato: float) -> None:
        ids = self._raccolta.get(where={"percorso": percorso}, include=[])["ids"]
        self._raccolta.update(ids=ids, metadatas=[{"modificato": modificato}] * len(ids))

    def numero_chunk(self) -> int:
        return self._raccolta.count()


def nome_raccolta(modello: str) -> str:
    """Es. "intfloat/multilingual-e5-base" -> "documenti-multilingual-e5-base"."""
    return "documenti-" + re.sub(r"[^a-zA-Z0-9._-]", "-", modello.split("/")[-1])


# --- L'indicizzazione -----------------------------------------------------------


@dataclass
class Esito:
    """Cosa è successo a un file durante l'indicizzazione."""

    stato: str  # "nuovo", "modificato", "invariato", "rimosso", "senza testo", "errore"
    percorso: Path
    n_chunk: int = 0
    errore: str | None = None


def indicizza(percorso: Path, indice: Indice, modello: Modello) -> Iterator[Esito]:
    """Aggiorna l'indice con i file di una cartella, un file alla volta.

    - file nuovi              -> estratti, trasformati in vettori e aggiunti
    - file modificati         -> la versione vecchia viene sostituita
    - file invariati          -> saltati (nessun lavoro)
    - file spariti dal disco  -> tolti dall'indice
    """
    percorso = percorso.expanduser().resolve()
    gia_indicizzati = indice.file_indicizzati()
    visti = set()

    for file in trova_file(percorso):
        chiave = str(file)
        visti.add(chiave)
        try:
            yield _indicizza_file(file, gia_indicizzati.get(chiave), indice, modello)
        except OSError as errore:  # es. file sparito nel frattempo o senza permessi
            yield Esito("errore", file, errore=f"{type(errore).__name__}: {errore}")

    # File che erano nell'indice ma non ci sono più su disco.
    # Guardiamo solo dentro la cartella indicizzata ora: le altre non si toccano.
    for chiave in sorted(gia_indicizzati.keys() - visti):
        if Path(chiave).is_relative_to(percorso):
            indice.rimuovi(chiave)
            yield Esito("rimosso", Path(chiave))


def _indicizza_file(
    file: Path, precedente: InfoFile | None, indice: Indice, modello: Modello
) -> Esito:
    stat = file.stat()

    # Controllo veloce: stessa dimensione e stessa data -> non è cambiato.
    if precedente and (precedente.dimensione, precedente.modificato) == (stat.st_size, stat.st_mtime):
        return Esito("invariato", file)

    # La data è cambiata: controlliamo il contenuto con l'impronta.
    info = InfoFile(stat.st_size, stat.st_mtime, calcola_impronta(file))
    if precedente and precedente.impronta == info.impronta:
        indice.aggiorna_data(str(file), info.modificato)  # così la prossima volta basta il controllo veloce
        return Esito("invariato", file)

    doc = estrai_documento(file)
    if doc.errore:
        return Esito("errore", file, errore=doc.errore)
    if not doc.chunk:
        if precedente:
            indice.rimuovi(str(file))
        return Esito("senza testo", file)

    vettori = modello.codifica_documenti([testo_per_embedding(file, c) for c in doc.chunk])
    if precedente:
        indice.rimuovi(str(file))
    indice.aggiungi(file, info, doc.tipo, doc.chunk, vettori)
    return Esito("modificato" if precedente else "nuovo", file, n_chunk=len(doc.chunk))


def testo_per_embedding(file: Path, chunk: str) -> str:
    """Aggiunge al chunk il nome del file e della sua cartella.

    Spesso dicono molto ("CV_2024", "Bollette") e aiutano a ritrovare il documento.
    """
    nome = re.sub(r"[_\-.]+", " ", file.stem).strip()
    return f"File: {nome} (cartella {file.parent.name})\n{chunk}"


def calcola_impronta(file: Path) -> str:
    """Impronta (hash SHA-256) del contenuto del file, letto in sola lettura."""
    impronta = hashlib.sha256()
    with open(file, "rb") as f:
        for blocco in iter(lambda: f.read(1024 * 1024), b""):
            impronta.update(blocco)
    return impronta.hexdigest()
