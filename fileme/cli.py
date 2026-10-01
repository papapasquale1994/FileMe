"""Comandi da terminale di FileMe.

Dopo l'installazione si usano così:  fileme <comando> [opzioni]
Per ora c'è solo `info`; gli altri comandi arrivano una fase alla volta.
"""

import argparse
import platform

from fileme import __version__, config


def comando_info(args: argparse.Namespace) -> None:
    """Mostra la configurazione attuale: utile per controllare l'installazione."""
    print(f"FileMe {__version__} (Python {platform.python_version()})")
    print(f"Cartella dati:   {config.CARTELLA_DATI}")
    print(f"Modello:         {config.MODELLO_EMBEDDING}")
    print(f"Formati letti:   {', '.join(sorted(config.ESTENSIONI_SUPPORTATE))}")


def crea_parser() -> argparse.ArgumentParser:
    """Descrive i comandi disponibili e le loro opzioni."""
    parser = argparse.ArgumentParser(
        prog="fileme",
        description="Ritrova i tuoi documenti descrivendoli a parole.",
    )
    sottocomandi = parser.add_subparsers(title="comandi", dest="comando")

    info = sottocomandi.add_parser("info", help="mostra la configurazione")
    info.set_defaults(funzione=comando_info)

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
