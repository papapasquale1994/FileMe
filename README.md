# FileMe

Ritrova i tuoi documenti **descrivendoli a parole**, senza ricordare nome, data o cartella.
Esempio: `fileme cerca "il curriculum per candidature nel turismo"`.

Prototipo (MVP) per computer desktop, scritto in Python.

## Privacy: tutto resta sul tuo computer

- I documenti vengono **solo letti**: FileMe non li modifica, non li sposta, non li cancella.
- Nessun testo esce dal computer: niente servizi cloud. Le statistiche d'uso anonime
  delle librerie sono disattivate nel codice (`fileme/config.py`).
- Internet serve solo **una volta**, per scaricare le librerie e il modello. Dopo, funziona offline.
- I dati di FileMe (indice e modello) stanno in una cartella separata: `.fileme` dentro
  la tua cartella utente.
- L'**indice** (`.fileme/indice`) contiene i pezzi di testo estratti dai documenti, che servono
  a mostrarti l'estratto nei risultati. Resta sul tuo computer, ma trattalo come un dato
  personale. Per cancellarlo basta eliminare quella cartella: i tuoi file non vengono toccati.

## Stato del progetto

| Fase | Cosa | Stato |
|---|---|---|
| 1 | Setup: struttura, dipendenze, documenti di esempio | ✅ fatto |
| 2 | Estrazione del testo dai file (`fileme estrai`) | ✅ fatto |
| 3 | Indicizzazione nel database (`fileme indicizza`) | ✅ fatto |
| 4 | Ricerca (`fileme cerca`) | in arrivo |
| 5 | Suggerimento contestuale (`fileme suggerisci`) | in arrivo |
| 6 | Valutazione con 20 query di prova (`fileme valuta`) | in arrivo |

---

## Installazione passo passo

Ti servono circa **3 GB liberi**: 1–2 GB per le librerie (la più grande è PyTorch) e circa 1 GB
per il modello, che si scarica con `fileme scarica-modello`.

### 1. Installa Python (una volta sola)

Serve Python **3.10 o più recente** (consigliato 3.12).

- **Windows**: scaricalo da <https://www.python.org/downloads/>. Durante l'installazione
  **spunta la casella "Add python.exe to PATH"**.
- **macOS**: scaricalo da <https://www.python.org/downloads/>.
- **Linux**: di solito è già installato. Controlla con `python3 --version`.

### 2. Apri il terminale

Il terminale è la finestra dove si scrivono i comandi.

- **Windows**: menu Start → cerca **PowerShell** → aprilo.
- **macOS**: Launchpad → cerca **Terminale**.
- **Linux**: cerca **Terminale** tra le applicazioni.

### 3. Scarica il codice

Hai due strade:

- **Senza git (più semplice)**: sulla pagina GitHub del progetto scegli il branch
  `claude/semantic-search-documents-p3wzbb` dal menu dei branch, poi
  **Code → Download ZIP**, ed estrai lo ZIP dove preferisci.
- **Con git**:
  ```
  git clone https://github.com/papapasquale1994/FileMe.git
  cd FileMe
  git checkout claude/semantic-search-documents-p3wzbb
  ```

Poi, nel terminale, entra nella cartella del progetto con `cd`. Esempio:
`cd C:\Users\Mario\Desktop\FileMe` (Windows) oppure `cd ~/Desktop/FileMe` (macOS/Linux).

### 4. Crea l'ambiente virtuale (una volta sola)

Un **ambiente virtuale** è una cartella (`.venv`) che contiene le librerie di questo progetto,
separate dal resto del computer. Se un giorno vuoi rimuovere tutto, basta cancellare `.venv`.

| | Comando |
|---|---|
| Windows | `py -3.12 -m venv .venv` |
| macOS / Linux | `python3 -m venv .venv` |

### 5. Attiva l'ambiente virtuale (ogni volta che apri un nuovo terminale)

| | Comando |
|---|---|
| Windows (PowerShell) | `.venv\Scripts\Activate.ps1` |
| Windows (Prompt dei comandi) | `.venv\Scripts\activate.bat` |
| macOS / Linux | `source .venv/bin/activate` |

Se funziona, all'inizio della riga del terminale compare `(.venv)`.

> **Windows, errore "l'esecuzione di script è disabilitata"**: esegui una volta
> `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, rispondi `S` e riprova.

### 6. Installa le librerie (una volta sola, con l'ambiente attivo)

**Solo su Linux**, prima installa la versione "leggera" di PyTorch, quella che usa solo il
processore. Senza questo passo scaricheresti diversi GB di componenti per schede grafiche.
```
pip install torch --index-url https://download.pytorch.org/whl/cpu
```

Poi, su **tutti i sistemi**:
```
python -m pip install --upgrade pip
pip install -e ".[dev]"
```

Cosa vuol dire:
- `pip` è il programma che scarica e installa librerie Python.
- `-e .` installa FileMe "in modalità sviluppo": usa direttamente i file di questa cartella,
  quindi quando il codice si aggiorna **non serve reinstallare**. Si reinstalla solo se
  vengono aggiunte librerie nuove.
- `[dev]` aggiunge le librerie per i test e per creare i documenti di esempio.

### 7. Controlla che tutto funzioni

```
fileme info
```
Deve mostrare la versione, la cartella dati e il modello. Poi lancia i test:
```
pytest
```
Deve finire con `passed` (superati). Un test risulta `skipped` (saltato) finché non scarichi
il modello: è quello che prova il modello vero. Dopo `fileme scarica-modello` girerà anche lui.

---

## Comandi disponibili

| Comando | Cosa fa |
|---|---|
| `fileme` | mostra l'elenco dei comandi |
| `fileme info` | mostra la configurazione (cartella dati, modello, formati) |
| `fileme estrai <cartella>` | legge i file della cartella (e delle sottocartelle) e mostra per ognuno il tipo, in quanti chunk è diviso e un'anteprima del testo. **Non salva nulla.** |
| `fileme estrai <cartella> --completo` | come sopra, ma mostra il testo completo di ogni chunk |
| `fileme estrai <cartella> --anteprima 300` | come sopra, con un'anteprima più lunga (300 caratteri) |
| `fileme scarica-modello` | scarica il modello di embedding (circa 1,1 GB). **Serve internet, una volta sola.** |
| `fileme indicizza <cartella>` | aggiunge all'indice i file nuovi o modificati della cartella, toglie quelli cancellati |

Al posto della cartella puoi indicare anche un singolo file.
I comandi `cerca`, `suggerisci` e `valuta` arriveranno con le prossime fasi.

### Esempio: `fileme estrai esempi/documenti`

```
[PDF ] Desktop/Allegato1.pdf  ->  2 chunk
       «CONTRATTO DI LOCAZIONE AD USO ABITATIVO (ai sensi dell'art. 2, comma 1, ...»
[XLSX] Documenti/casa/budget_famiglia_2024.xlsx  ->  1 chunk
       «Foglio: Spese mensili Categoria | Gennaio | Febbraio | Marzo | ...»
...
Riepilogo: file letti: 24 | chunk: 27 | senza testo: 0 | errori: 0 | tempo: 0.2 s
```

Cosa possono voler dire i messaggi:
- **`ATTENZIONE: nessun testo`**: il file non contiene testo leggibile. Di solito è un PDF
  scansionato, cioè una "foto" del foglio: per leggerlo servirebbe l'OCR, che per ora non
  facciamo.
- **`ERRORE, file non letto`**: il file è danneggiato, protetto da password o non è davvero
  del formato indicato. Gli altri file vengono letti comunque.

### Provarlo sui tuoi documenti

`fileme estrai` è il primo comando che puoi provare in sicurezza su una tua cartella vera:
legge soltanto, non salva nulla e non usa internet. Esempi:

| | Comando |
|---|---|
| Windows | `fileme estrai "C:\Users\Mario\Downloads"` |
| macOS | `fileme estrai ~/Downloads` |
| Linux | `fileme estrai ~/Scaricati` |

Le virgolette servono se il percorso contiene spazi. Il riepilogo finale ti dice quanti file
si leggono bene, quanti sono scansioni e quanti danno errore.

## Indicizzare i documenti

Indicizzare vuol dire preparare i documenti per la ricerca: FileMe legge ogni file, lo divide
in chunk, calcola il vettore (embedding) di ogni chunk e salva tutto nell'indice.

```
fileme scarica-modello            (una volta sola, serve internet)
fileme indicizza esempi/documenti
```

Esempio di risultato:
```
[nuovo]       Desktop/Allegato1.pdf (2 chunk)
[nuovo]       Desktop/note.txt (1 chunk)
...
Riepilogo: nuovo: 24 | modificato: 0 | invariato: 0 | rimosso: 0 | senza testo: 0 | errore: 0 | tempo: ...
Chunk nell'indice: 27
```

**Le volte successive FileMe rifà solo il necessario**: per ogni file ricorda dimensione, data
di modifica e un'"impronta" del contenuto (hash).
- **nuovo**: file mai visto, viene aggiunto.
- **modificato**: il contenuto è cambiato, la versione vecchia viene sostituita.
- **invariato**: nessun cambiamento, il file viene saltato. Non sono elencati uno per uno.
- **rimosso**: il file non c'è più sul disco, quindi esce dall'indice. Il file vero non viene
  mai toccato.
- **senza testo** / **errore**: come in `fileme estrai`. Questi file non entrano nell'indice.

Puoi indicizzare più cartelle, una alla volta (es. Download, poi Documenti): ogni comando
aggiorna solo la cartella indicata e lascia stare le altre.

Quanto ci vuole? La prima volta il modello deve calcolare i vettori di tutti i chunk: per un
centinaio di documenti servono indicativamente alcuni minuti, a seconda del computer. Le volte
successive bastano pochi secondi, se i file sono cambiati poco.

## Documenti di esempio

In `esempi/documenti/` ci sono 24 documenti **inventati** (CV, bollette, contratto d'affitto,
referto, busta paga, fogli Excel...) in PDF, DOCX, XLSX e TXT, in italiano e alcuni in inglese.
Imitano un computer reale: cartelle `Download`, `Desktop` e `Documenti`, e alcuni nomi poco
chiari come `Allegato1.pdf` o `documento(3).pdf`.

Servono per provare FileMe senza usare documenti personali. Il loro contenuto è scritto in
`esempi/genera_documenti.py`. Per ricrearli:
```
python esempi/genera_documenti.py
```

> **Documenti reali**: per le prove sui tuoi file puoi creare una cartella `documenti_privati/`
> qui nel progetto: è esclusa da git, quindi non finirà mai su GitHub.

## Struttura del progetto

```
FileMe/
├── README.md               questa guida
├── pyproject.toml          "carta d'identità": nome, librerie, comando fileme
├── .gitignore              file che git deve ignorare (ambiente, indice, documenti privati)
├── fileme/                 il codice del programma
│   ├── __init__.py         segna la cartella come pacchetto Python; contiene la versione
│   ├── config.py           impostazioni: cartella dati, modello, formati, privacy
│   ├── estrazione.py       trova i file, ne legge il testo e lo divide in chunk
│   ├── embedding.py        scarica e usa il modello che trasforma i testi in vettori
│   ├── indice.py           il database (Chroma) e l'indicizzazione dei soli file cambiati
│   └── cli.py              i comandi da terminale (fileme info, fileme estrai, ...)
├── tests/                  test automatici (si lanciano con: pytest)
│   ├── conftest.py         strumenti per i test: un modello "finto" e il blocco della rete
│   ├── test_cli.py
│   ├── test_estrazione.py
│   └── test_indice.py
└── esempi/
    ├── genera_documenti.py crea i documenti di esempio
    └── documenti/          i 24 documenti inventati
```

## Librerie usate (tutte gratuite e open source)

| Libreria | A cosa serve |
|---|---|
| `pypdf` | leggere il testo dei PDF |
| `cryptography` | aprire i PDF "protetti" che si aprono senza password (es. estratti conto); arriva con `pypdf[crypto]` |
| `python-docx` | leggere i documenti Word (.docx) |
| `openpyxl` | leggere i fogli Excel (.xlsx) |
| `chromadb` | database vettoriale salvato su disco |
| `sentence-transformers` | calcolare gli embedding con un modello locale; installa anche PyTorch |
| `pytest` *(dev)* | eseguire i test |
| `fpdf2` *(dev)* | creare i PDF di esempio |

## Piccolo glossario

- **Chunk**: un pezzo di testo di un documento (circa 250 parole). I documenti lunghi vengono
  divisi in più chunk, così la ricerca trova il punto giusto.
- **Embedding**: una lista di numeri che rappresenta il *significato* di un testo. Testi con
  significato simile hanno numeri simili, anche se usano parole diverse
  ("curriculum" e "CV", "affitto" e "locazione").
- **Modello di embedding**: il programma che calcola gli embedding. Usiamo
  `intfloat/multilingual-e5-base`, che capisce italiano e inglese e gira sul tuo computer.
- **Database vettoriale**: un archivio che conserva gli embedding e trova velocemente quelli
  più simili alla tua domanda.
- **Indice**: il database vettoriale con i documenti già preparati per la ricerca.
- **Hash (impronta)**: un codice calcolato dal contenuto di un file. Se cambia anche una sola
  lettera, cambia l'impronta: così FileMe capisce se un file è stato modificato.
