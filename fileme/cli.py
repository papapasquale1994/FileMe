"""Comandi da terminale di FileMe.

Dopo l'installazione si usano così:  fileme <comando> [opzioni]
I comandi arrivano una fase alla volta: per ora `info`, `estrai`,
`scarica-modello`, `indicizza`, `cerca` e `suggerisci`.
"""

import argparse
import platform
import sys
import time
from pathlib import Path

# Momento di avvio, preso PRIMA di caricare le librerie pesanti: serve a
# misurare il tempo totale di `fileme cerca`, come lo percepisci tu.
INIZIO = time.perf_counter()

from fileme import __version__, config  # noqa: E402
from fileme.embedding import (  # noqa: E402
    ModelloEmbedding,
    ModelloMancante,
    cartella_modello,
    modello_presente,
    scarica_modello,
)
from fileme.estrazione import estrai_cartella  # noqa: E402
from fileme.indice import Indice, indicizza  # noqa: E402
from fileme.ricerca import Risultato, cerca  # noqa: E402
from fileme.situazioni import SITUAZIONI  # noqa: E402
from fileme.suggerimento import suggerisci  # noqa: E402


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


def comando_cerca(args: argparse.Namespace) -> None:
    """Cerca i file più pertinenti per una descrizione a parole."""
    if args.numero < 1:
        sys.exit("Errore: il numero di file da mostrare (-n) deve essere almeno 1.")
    indice, modello = _prepara_ricerca()

    domanda = " ".join(args.domanda).strip()
    if domanda:
        secondi = _mostra_ricerca(domanda, indice, modello, args.numero)
        totale = time.perf_counter() - INIZIO
        print(
            f"Tempo: {secondi:.2f} s per la ricerca | "
            f"{totale:.1f} s in totale, compreso l'avvio di FileMe e del modello"
        )
        return

    # Nessuna domanda scritta: modalità interattiva. Il modello si carica una
    # volta sola e resta in memoria, quindi ogni ricerca successiva è veloce.
    print("Ricerca interattiva: scrivi cosa cerchi e premi Invio.")
    print("Per uscire premi Invio su una riga vuota (oppure Ctrl+C).")
    while True:
        try:
            domanda = input("\nCosa cerchi? ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not domanda:
            break
        secondi = _mostra_ricerca(domanda, indice, modello, args.numero)
        print(f"Tempo: {secondi:.2f} s")


def _prepara_ricerca() -> tuple[Indice, ModelloEmbedding]:
    """Apre l'indice e carica il modello, oppure spiega cosa manca."""
    indice = Indice(config.CARTELLA_INDICE)
    if indice.numero_chunk() == 0:
        sys.exit("L'indice è vuoto: prima esegui  fileme indicizza <cartella>")
    modello = ModelloEmbedding()
    try:
        modello.carica()
    except ModelloMancante as errore:
        sys.exit(str(errore))
    return indice, modello


def _mostra_ricerca(domanda: str, indice: Indice, modello, numero: int) -> float:
    """Esegue una ricerca, stampa i risultati e restituisce quanti secondi ha impiegato."""
    inizio = time.perf_counter()
    risultati = cerca(domanda, indice, modello, numero)
    secondi = time.perf_counter() - inizio

    print(f'\nRisultati per: "{domanda}"\n')
    for posizione, risultato in enumerate(risultati, start=1):
        print(f"{posizione}. {risultato.percorso.name}  (punteggio {risultato.punteggio:.2f})")
        _stampa_dettagli(risultato, rientro="   ")
    return secondi


def _stampa_dettagli(risultato: Risultato, rientro: str) -> None:
    """Percorso ed estratto di un risultato (con avviso se il file è sparito)."""
    print(f"{rientro}Percorso: {risultato.percorso}")
    if not risultato.percorso.exists():
        print(f"{rientro}ATTENZIONE: il file non è più qui (rilancia fileme indicizza)")
    print(f"{rientro}«{_accorcia(risultato.estratto, 220)}»\n")


def comando_suggerisci(args: argparse.Namespace) -> None:
    """Dalla descrizione di una situazione ai documenti che servono."""
    contesto = " ".join(args.contesto).strip()
    if not contesto:
        _mostra_situazioni()
        return
    indice, modello = _prepara_ricerca()

    inizio = time.perf_counter()
    suggerimento = suggerisci(contesto, indice, modello)
    secondi = time.perf_counter() - inizio

    print(f'\nContesto: "{contesto}"')
    if suggerimento.situazione is None:
        print("Nessuna situazione dell'elenco riconosciuta: cerco direttamente la frase.")
        print("(Per vedere le situazioni conosciute scrivi solo: fileme suggerisci)\n")
        for posizione, risultato in enumerate(suggerimento.risultati_diretti, start=1):
            print(f"{posizione}. {risultato.percorso.name}  (punteggio {risultato.punteggio:.2f})")
            _stampa_dettagli(risultato, rientro="   ")
    else:
        parole = ", ".join(f"«{p}»" for p in suggerimento.parole_riconosciute)
        print(f"Situazione riconosciuta: {suggerimento.situazione.nome} (dalle parole {parole})\n")
        for documento, risultato in suggerimento.documenti:
            print(documento)
            if risultato is None:
                print("   -> nessun file disponibile nell'indice\n")
                continue
            incerto = ""
            if risultato.punteggio < config.SOGLIA_SUGGERIMENTO:
                incerto = "  INCERTO: forse non hai questo documento"
            print(f"   -> {risultato.percorso.name}  (punteggio {risultato.punteggio:.2f}){incerto}")
            _stampa_dettagli(risultato, rientro="      ")

    totale = time.perf_counter() - INIZIO
    print(f"Tempo: {secondi:.2f} s per il suggerimento | {totale:.1f} s in totale, compreso l'avvio")


def _mostra_situazioni() -> None:
    print("Situazioni conosciute (le trovi e le puoi modificare in fileme/situazioni.py):\n")
    for situazione in SITUAZIONI:
        print(f"- {situazione.nome}")
        print(f"    parole chiave: {', '.join(situazione.parole_chiave)}")
        print(f"    documenti:     {', '.join(situazione.documenti)}")
    print('\nEsempio:  fileme suggerisci "un\'azienda mi chiede il curriculum"')


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

    ricerca = sottocomandi.add_parser(
        "cerca",
        help="trova i file che corrispondono a una descrizione (senza descrizione: modalità interattiva)",
    )
    ricerca.add_argument(
        "domanda", nargs="*",
        help='cosa cerchi, meglio tra virgolette: es. "il contratto d\'affitto"',
    )
    ricerca.add_argument(
        "-n", "--numero", type=int, default=5, metavar="N",
        help="quanti file mostrare (default: 5)",
    )
    ricerca.set_defaults(funzione=comando_cerca)

    suggerimento = sottocomandi.add_parser(
        "suggerisci",
        help="dalla descrizione di una situazione ai documenti che servono (senza frase: elenco situazioni)",
    )
    suggerimento.add_argument(
        "contesto", nargs="*",
        help='la situazione, es. "un\'azienda mi chiede il curriculum"',
    )
    suggerimento.set_defaults(funzione=comando_suggerisci)

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
