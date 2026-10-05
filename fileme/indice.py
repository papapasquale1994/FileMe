"""Indice: il database (Chroma) dove salviamo, per ogni chunk, il suo vettore,
il suo testo e il percorso del file da cui viene.

Accanto ai chunk salviamo anche le loro frasi, ognuna con il suo vettore:
sono i candidati per l'estratto mostrato nei risultati. Prepararle qui,
durante l'indicizzazione, evita di ricalcolarle a ogni ricerca.

L'indice sta in ~/.fileme/indice, sul tuo computer. Contiene i pezzi di testo
estratti (servono a mostrarti l'estratto nei risultati), non i file originali.
Se cancelli quella cartella, l'indice sparisce e i tuoi file restano dove sono.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import chromadb
from chromadb.config import Settings

from fileme import config
from fileme.embedding import Modello
from fileme.estrazione import dividi_in_frasi, estrai_documento, trova_file

# Una frase già pronta per l'estratto: il testo e il suo vettore.
Frase = tuple[str, list[float]]


@dataclass
class InfoFile:
    """Ciò che ricordiamo di un file per capire, la volta dopo, se è cambiato."""

    dimensione: int  # in byte
    modificato: float  # data di ultima modifica
    impronta: str  # "hash" del contenuto: cambia se cambia anche un solo byte
    # False per i file indicizzati prima che FileMe preparasse le frasi degli
    # estratti: alla prossima indicizzazione vengono completati.
    estratti_pronti: bool = True


@dataclass
class ChunkTrovato:
    """Un chunk restituito da una ricerca nell'indice."""

    id: str  # serve a ritrovare le frasi già pronte del chunk
    percorso: Path
    tipo: str
    testo: str
    somiglianza: float  # 1 = identico; più è basso, meno c'entra con la domanda


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
        # Le frasi dei chunk, per gli estratti. Non si cercano direttamente:
        # si leggono solo quelle dei chunk trovati.
        self._frasi = client.get_or_create_collection(
            name=nome_raccolta(modello, "frasi"),
            metadata={"hnsw:space": "cosine", "modello": modello},
            embedding_function=None,
        )
        self._max_per_volta = client.get_max_batch_size()  # limite di Chroma per ogni "add"

    def file_indicizzati(self) -> dict[str, InfoFile]:
        """Tutti i file nell'indice: percorso -> dimensione, data, impronta."""
        # Basta guardare il primo chunk (posizione 0) di ogni file.
        risultato = self._raccolta.get(where={"posizione": 0}, include=["metadatas"])
        return {
            m["percorso"]: InfoFile(
                m["dimensione"], m["modificato"], m["impronta"], m.get("estratti_pronti", False)
            )
            for m in risultato["metadatas"]
        }

    def aggiungi(
        self,
        percorso: Path,
        info: InfoFile,
        tipo: str,
        chunk: list[str],
        vettori: list[list[float]],
        frasi: list[list[Frase]],
    ) -> None:
        """Salva i chunk di un file e, per ogni chunk, le sue frasi già pronte."""
        chiave = str(percorso)
        codice = hashlib.sha1(chiave.encode()).hexdigest()[:16]
        ids_chunk = [f"{codice}-{n}" for n in range(len(chunk))]
        self._raccolta.add(
            ids=ids_chunk,
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
                    "estratti_pronti": True,
                }
                for n in range(len(chunk))
            ],
        )

        righe = [
            (f"{id_chunk}-{k}", testo, vettore, {"percorso": chiave, "chunk": id_chunk, "posizione": k})
            for id_chunk, frasi_chunk in zip(ids_chunk, frasi)
            for k, (testo, vettore) in enumerate(frasi_chunk)
        ]
        # Un documento lungo può avere migliaia di frasi: le salviamo a blocchi.
        for inizio in range(0, len(righe), self._max_per_volta):
            ids, testi, vettori_frasi, metadati = zip(*righe[inizio : inizio + self._max_per_volta])
            self._frasi.add(
                ids=list(ids), documents=list(testi), embeddings=list(vettori_frasi), metadatas=list(metadati)
            )

    def rimuovi(self, percorso: str) -> None:
        """Toglie dall'indice tutti i chunk di un file (il file vero non si tocca)."""
        self._raccolta.delete(where={"percorso": percorso})
        self._frasi.delete(where={"percorso": percorso})

    def aggiorna_data(self, percorso: str, modificato: float) -> None:
        ids = self._raccolta.get(where={"percorso": percorso}, include=[])["ids"]
        self._raccolta.update(ids=ids, metadatas=[{"modificato": modificato}] * len(ids))

    def numero_chunk(self) -> int:
        return self._raccolta.count()

    def chunk_simili(self, vettore: list[float], quanti: int) -> list[ChunkTrovato]:
        """I chunk più vicini al vettore dato, dal più simile al meno simile."""
        quanti = min(quanti, self.numero_chunk())
        if quanti == 0:
            return []
        risultato = self._raccolta.query(
            query_embeddings=[vettore],
            n_results=quanti,
            include=["documents", "metadatas", "distances"],
        )
        return [
            # Chroma restituisce una "distanza" (0 = identico): la trasformiamo
            # in somiglianza (1 = identico), più intuitiva.
            ChunkTrovato(id_chunk, Path(m["percorso"]), m["tipo"], testo, 1 - distanza)
            for id_chunk, testo, m, distanza in zip(
                risultato["ids"][0],
                risultato["documents"][0],
                risultato["metadatas"][0],
                risultato["distances"][0],
            )
        ]

    def frasi_dei_chunk(self, ids_chunk: list[str]) -> dict[str, list[Frase]]:
        """Le frasi già pronte di ogni chunk, nell'ordine in cui compaiono.

        I chunk indicizzati prima che FileMe preparasse le frasi non compaiono
        nel risultato.
        """
        if not ids_chunk:
            return {}
        risultato = self._frasi.get(
            where={"chunk": {"$in": list(ids_chunk)}}, include=["documents", "embeddings", "metadatas"]
        )
        righe = sorted(
            zip(risultato["metadatas"], risultato["documents"], risultato["embeddings"]),
            key=lambda riga: (riga[0]["chunk"], riga[0]["posizione"]),
        )
        frasi: dict[str, list[Frase]] = {}
        for m, testo, vettore in righe:
            frasi.setdefault(m["chunk"], []).append((testo, list(vettore)))
        return frasi


def nome_raccolta(modello: str, contenuto: str = "documenti") -> str:
    """Es. "intfloat/multilingual-e5-base" -> "documenti-multilingual-e5-base"."""
    return f"{contenuto}-" + re.sub(r"[^a-zA-Z0-9._-]", "-", modello.split("/")[-1])


# --- L'indicizzazione -----------------------------------------------------------


@dataclass
class Esito:
    """Cosa è successo a un file durante l'indicizzazione."""

    # "nuovo", "modificato", "invariato", "rimosso", "senza testo", "errore",
    # oppure "aggiornato": stesso contenuto, ma mancavano le frasi per gli estratti
    stato: str
    percorso: Path
    n_chunk: int = 0
    errore: str | None = None


def indicizza(percorso: Path, indice: Indice, modello: Modello) -> Iterator[Esito]:
    """Aggiorna l'indice con i file di una cartella, un file alla volta.

    - file nuovi              -> estratti, trasformati in vettori e aggiunti
    - file modificati         -> la versione vecchia viene sostituita
    - file invariati          -> saltati (nessun lavoro)
    - file indicizzati da una versione precedente di FileMe, senza le frasi
      per gli estratti -> rifatti una volta ("aggiornato")
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
    # Un file indicizzato senza le frasi degli estratti va rifatto anche se non è cambiato.
    completo = precedente is not None and precedente.estratti_pronti

    # Controllo veloce: stessa dimensione e stessa data -> non è cambiato.
    if completo and (precedente.dimensione, precedente.modificato) == (stat.st_size, stat.st_mtime):
        return Esito("invariato", file)

    # La data è cambiata: controlliamo il contenuto con l'impronta.
    info = InfoFile(stat.st_size, stat.st_mtime, calcola_impronta(file))
    if completo and precedente.impronta == info.impronta:
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
    frasi = prepara_frasi(doc.chunk, modello)
    if precedente:
        indice.rimuovi(str(file))
    indice.aggiungi(file, info, doc.tipo, doc.chunk, vettori, frasi)
    if precedente is None:
        stato = "nuovo"
    elif precedente.impronta == info.impronta:
        stato = "aggiornato"
    else:
        stato = "modificato"
    return Esito(stato, file, n_chunk=len(doc.chunk))


def prepara_frasi(chunk: list[str], modello: Modello) -> list[list[Frase]]:
    """Per ogni chunk, le sue frasi con il loro vettore: i candidati per l'estratto.

    Le frasi di tutti i chunk passano dal modello in un colpo solo: è molto
    più veloce che un chunk alla volta.
    """
    frasi_per_chunk = [dividi_in_frasi(testo) for testo in chunk]
    tutte = [frase for frasi in frasi_per_chunk for frase in frasi]
    vettori = iter(modello.codifica_documenti(tutte) if tutte else [])
    return [[(frase, next(vettori)) for frase in frasi] for frasi in frasi_per_chunk]


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
