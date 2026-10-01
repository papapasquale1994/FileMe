"""Comandi da terminale di FileMe.

Dopo l'installazione si usano così:  fileme <comando> [opzioni]
I comandi arrivano una fase alla volta: per ora `info` ed `estrai`.
"""

import argparse
import platform
import sys
import time
from pathlib import Path

from fileme import __version__, config
from fileme.estrazione import estrai_cartella


def comando_info(args: argparse.Namespace) -> None:
    """Mostra la configurazione attuale: utile per controllare l'installazione."""
    print(f"FileMe {__version__} (Python {platform.python_version()})")
    print(f"Cartella dati:   {config.CARTELLA_DATI}")
    print(f"Modello:         {config.MODELLO_EMBEDDING}")
    print(f"Formati letti:   {', '.join(sorted(config.ESTENSIONI_SUPPORTATE))}")


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
