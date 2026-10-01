"""Comandi da terminale di FileMe.

Dopo l'installazione si usano così:  fileme <comando> [opzioni]
I comandi arrivano una fase alla volta: per ora `info`, `estrai`,
`scarica-modello` e `indicizza`.
"""

import argparse
import platform
import sys
import time
from pathlib import Path

from fileme import __version__, config
from fileme.embedding import (
    ModelloEmbedding,
    ModelloMancante,
    cartella_modello,
    modello_presente,
    scarica_modello,
)
from fileme.estrazione import estrai_cartella
from fileme.indice import Indice, indicizza


def comando_info(args: argparse.Namespace) -> None:
    """Mostra la configurazione attuale: utile per controllare l'installazione."""
    print(f"FileMe {__version__} (Python {platform.python_version()})")
    print(f"Cartella dati:   {config.CARTELLA_DATI}")
    print(f"Modello:         {config.MODELLO_EMBEDDING}")
    print(f"Modello scaricato: {'sì' if modello_presente() else 'no (usa: fileme scarica-modello)'}")
    print(f"Formati letti:   {', '.join(sorted(config.ESTENSIONI_SUPPORTATE))}")


def comando_scarica_modello(args: argparse.Namespace) -> None:
    """Scarica il modello di embedding: serve internet, una volta sola."""
    cartella = cartella_modello()
    if modello_presente():
        print(f"Il modello è già presente in {cartella}: non serve scaricarlo di nuovo.")
        return
    print(f"Scarico {config.MODELLO_EMBEDDING} (circa 1,1 GB) in {cartella} ...")
    try:
        scarica_modello()
    except Exception as errore:  # rete assente, sito irraggiungibile, disco pieno...
        sys.exit(
            "\nDownload non riuscito. Controlla la connessione a internet e lo spazio su disco,\n"
            "poi riprova: il download riprende da dove si era fermato.\n"
            f"(dettaglio tecnico: {type(errore).__name__}: {errore})"
        )
    dimensione = sum(f.stat().st_size for f in cartella.rglob("*") if f.is_file())
    print(f"\nFatto ({dimensione / 1e9:.1f} GB). Da ora FileMe funziona senza internet.")


def comando_indicizza(args: argparse.Namespace) -> None:
    """Aggiunge all'indice i file nuovi o modificati di una cartella."""
    percorso = Path(args.cartella).expanduser()
    if not percorso.exists():
        sys.exit(f"Errore: '{percorso}' non esiste.")
    base = percorso.resolve() if percorso.is_dir() else percorso.resolve().parent

    print(f"Indicizzo {percorso.resolve()}")
    print("(il primo file nuovo richiede qualche secondo in più: si carica il modello)\n")
    inizio = time.perf_counter()
    conteggi = dict.fromkeys(["nuovo", "modificato", "invariato", "rimosso", "senza testo", "errore"], 0)
    indice = Indice(config.CARTELLA_INDICE)
    try:
        for esito in indicizza(percorso, indice, ModelloEmbedding()):
            conteggi[esito.stato] += 1
            if esito.stato == "invariato":
                continue  # non li elenchiamo uno per uno: sarebbero troppi
            nome = esito.percorso.relative_to(base)
            dettaglio = f" ({esito.n_chunk} chunk)" if esito.n_chunk else ""
            if esito.errore:
                dettaglio = f" ({esito.errore})"
            print(f"[{esito.stato}]".ljust(14) + f"{nome}{dettaglio}")
    except ModelloMancante as errore:
        sys.exit(f"\n{errore}")

    secondi = time.perf_counter() - inizio
    print(
        "\nRiepilogo: "
        + " | ".join(f"{stato}: {numero}" for stato, numero in conteggi.items())
        + f" | tempo: {secondi:.1f} s"
    )
    print(f"Chunk nell'indice: {indice.numero_chunk()} (salvato in {config.CARTELLA_INDICE})")


def comando_estrai(args: argparse.Namespace) -> None:
    """Legge i file di una cartella e mostra cosa ne ricava, senza salvare nulla."""
    percorso = Path(args.cartella).expanduser()
    if not percorso.exists():
        sys.exit(f"Errore: '{percorso}' non esiste.")
    base = percorso if percorso.is_dir() else percorso.parent

    inizio = time.perf_counter()
    n_file = n_chunk = n_senza_testo = n_errori = 0
    for doc in estrai_cartella(percorso):
        n_file += 1
        n_chunk += len(doc.chunk)
        nome = doc.percorso.relative_to(base)
        etichetta = f"[{doc.tipo.upper():4}]"

        if doc.errore:
            n_errori += 1
            print(f"{etichetta} {nome}  ->  ERRORE, file non letto ({doc.errore})")
        elif not doc.chunk:
            n_senza_testo += 1
            print(f"{etichetta} {nome}  ->  ATTENZIONE: nessun testo (forse è una scansione?)")
        else:
            print(f"{etichetta} {nome}  ->  {len(doc.chunk)} chunk")
            if args.completo:
                for numero, testo in enumerate(doc.chunk, start=1):
                    print(f"\n    --- chunk {numero} ({len(testo.split())} parole) ---\n    {testo}")
                print()
            else:
                print(f"       «{_accorcia(doc.chunk[0], args.anteprima)}»")

    secondi = time.perf_counter() - inizio
    print(
        f"\nRiepilogo: file letti: {n_file} | chunk: {n_chunk} | "
        f"senza testo: {n_senza_testo} | errori: {n_errori} | tempo: {secondi:.1f} s"
    )


def _accorcia(testo: str, lunghezza: int) -> str:
    return testo if len(testo) <= lunghezza else testo[:lunghezza].rstrip() + "…"


def crea_parser() -> argparse.ArgumentParser:
    """Descrive i comandi disponibili e le loro opzioni."""
    parser = argparse.ArgumentParser(
        prog="fileme",
        description="Ritrova i tuoi documenti descrivendoli a parole.",
    )
    sottocomandi = parser.add_subparsers(title="comandi", dest="comando")

    info = sottocomandi.add_parser("info", help="mostra la configurazione")
    info.set_defaults(funzione=comando_info)

    estrai = sottocomandi.add_parser(
        "estrai",
        help="legge i file di una cartella e mostra il testo trovato (non salva nulla)",
    )
    estrai.add_argument("cartella", help="cartella (o singolo file) da leggere")
    estrai.add_argument(
        "--anteprima", type=int, default=150, metavar="N",
        help="quanti caratteri mostrare di anteprima (default: 150)",
    )
    estrai.add_argument(
        "--completo", action="store_true",
        help="mostra il testo completo di ogni chunk invece dell'anteprima",
    )
    estrai.set_defaults(funzione=comando_estrai)

    scarica = sottocomandi.add_parser(
        "scarica-modello",
        help="scarica il modello di embedding (serve internet, una volta sola)",
    )
    scarica.set_defaults(funzione=comando_scarica_modello)

    indicizzazione = sottocomandi.add_parser(
        "indicizza",
        help="aggiunge all'indice i file nuovi o modificati di una cartella",
    )
    indicizzazione.add_argument("cartella", help="cartella (o singolo file) da indicizzare")
    indicizzazione.set_defaults(funzione=comando_indicizza)

    return parser


def main(argv: list[str] | None = None) -> None:
    """Punto di ingresso: legge il comando scritto nel terminale e lo esegue."""
    parser = crea_parser()
    args = parser.parse_args(argv)
    if args.comando is None:
        parser.print_help()
        return
    args.funzione(args)


if __name__ == "__main__":
    main()
