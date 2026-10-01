"""Embedding: trasforma un testo in un vettore, cioè una lista di numeri che
ne rappresenta il significato. Testi con significato simile hanno vettori vicini.

Il modello si scarica UNA volta sola con `fileme scarica-modello` e viene
salvato in ~/.fileme/modelli. Da quel momento viene caricato soltanto dal
disco, con l'accesso a internet delle librerie disattivato.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Protocol

from fileme import config

# Il modello è pubblicato anche in altri formati (stessi pesi, file diversi):
# non ci servono, e saltarli fa risparmiare qualche GB di download.
FILE_DA_NON_SCARICARE = ["*.bin", "*.h5", "*.msgpack", "*.ot", "onnx/*", "openvino/*"]


class Modello(Protocol):
    """Quello che ci serve da un modello di embedding (vero o, nei test, finto)."""

    def codifica_documenti(self, testi: list[str]) -> list[list[float]]: ...

    def codifica_domanda(self, testo: str) -> list[float]: ...


class ModelloMancante(Exception):
    """Il modello non è ancora stato scaricato."""


def cartella_modello(nome: str = config.MODELLO_EMBEDDING) -> Path:
    """Dove sta il modello sul disco, es. ~/.fileme/modelli/multilingual-e5-base"""
    return config.CARTELLA_MODELLI / nome.split("/")[-1]


def modello_presente(nome: str = config.MODELLO_EMBEDDING) -> bool:
    cartella = cartella_modello(nome)
    return (cartella / "config.json").exists() and any(cartella.glob("*.safetensors"))


def scarica_modello(nome: str = config.MODELLO_EMBEDDING) -> Path:
    """Scarica il modello da Hugging Face. È l'UNICO punto che usa internet."""
    from huggingface_hub import snapshot_download

    cartella = cartella_modello(nome)
    snapshot_download(repo_id=nome, local_dir=cartella, ignore_patterns=FILE_DA_NON_SCARICARE)
    return cartella


class ModelloEmbedding:
    """Il modello vero. Viene caricato dal disco solo al primo utilizzo,
    perché il caricamento richiede qualche secondo."""

    def __init__(self, nome: str = config.MODELLO_EMBEDDING):
        self.nome = nome
        self._modello = None

    def codifica_documenti(self, testi: list[str]) -> list[list[float]]:
        """Vettori per i pezzi di documento da salvare nell'indice."""
        return self._codifica([config.PREFISSO_DOCUMENTO + testo for testo in testi])

    def codifica_domanda(self, testo: str) -> list[float]:
        """Vettore per una domanda di ricerca."""
        return self._codifica([config.PREFISSO_DOMANDA + testo])[0]

    def _codifica(self, testi: list[str]) -> list[list[float]]:
        vettori = self.carica().encode(
            testi,
            batch_size=16,
            normalize_embeddings=True,  # vettori di lunghezza 1: confronti più semplici
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return vettori.tolist()

    def carica(self):
        """Carica il modello dal disco (solo la prima volta: poi resta in memoria)."""
        if self._modello is None:
            cartella = cartella_modello(self.nome)
            if not modello_presente(self.nome):
                raise ModelloMancante(
                    f"Il modello non è ancora stato scaricato (manca in {cartella}).\n"
                    "Esegui prima, una volta sola:  fileme scarica-modello"
                )
            # Da qui in poi le librerie di Hugging Face non devono usare internet.
            os.environ["HF_HUB_OFFLINE"] = "1"
            os.environ["TRANSFORMERS_OFFLINE"] = "1"
            # Import qui dentro e non in cima al file: è una libreria pesante
            # (qualche secondo) e serve solo quando si calcolano davvero i vettori.
            from sentence_transformers import SentenceTransformer

            self._modello = SentenceTransformer(str(cartella), local_files_only=True)
        return self._modello
