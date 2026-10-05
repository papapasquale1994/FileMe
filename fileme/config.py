"""Impostazioni centrali di FileMe.

Tutte le scelte "di configurazione" stanno qui, così sono facili da trovare
e da cambiare: dove salviamo i dati, quale modello usiamo, quali file leggiamo.
"""

import os
from pathlib import Path

# --- Privacy -----------------------------------------------------------------
# Alcune librerie inviano statistiche d'uso anonime. Le spegniamo sempre,
# prima che vengano caricate, così nessuna informazione esce dal computer.
os.environ["ANONYMIZED_TELEMETRY"] = "False"  # Chroma
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"  # Hugging Face (modelli)
os.environ["DO_NOT_TRACK"] = "1"  # convenzione generale

# --- Dove salviamo i dati di FileMe -------------------------------------------
# Di default nella cartella nascosta ".fileme" dentro la tua cartella utente
# (es. C:\Users\Mario\.fileme oppure /home/mario/.fileme).
# I tuoi documenti NON vengono mai copiati qui: solo indice e modello.
# Si può cambiare impostando la variabile d'ambiente FILEME_DATI.
CARTELLA_DATI = Path(os.environ.get("FILEME_DATI", Path.home() / ".fileme"))
CARTELLA_INDICE = CARTELLA_DATI / "indice"
CARTELLA_MODELLI = CARTELLA_DATI / "modelli"

# --- Modello di embedding -----------------------------------------------------
# Modello multilingue (italiano + inglese) che trasforma un testo in numeri.
MODELLO_EMBEDDING = "intfloat/multilingual-e5-base"
# I modelli "e5" vogliono un'etichetta davanti al testo: "query: " per le
# domande di ricerca e "passage: " per i pezzi di documento.
PREFISSO_DOMANDA = "query: "
PREFISSO_DOCUMENTO = "passage: "

# --- Formati di file che sappiamo leggere -------------------------------------
ESTENSIONI_SUPPORTATE = {".pdf", ".docx", ".xlsx", ".txt"}

# --- Divisione del testo in chunk ---------------------------------------------
# Ogni chunk ha al massimo PAROLE_PER_CHUNK parole. Le ultime
# PAROLE_SOVRAPPOSIZIONE parole di un chunk vengono ripetute all'inizio del
# successivo, così una frase tagliata a metà non va persa.
PAROLE_PER_CHUNK = 250
PAROLE_SOVRAPPOSIZIONE = 50

# --- Suggerimento contestuale (fileme suggerisci) ------------------------------
# Quanto conta la tua frase rispetto alla descrizione del documento cercato:
# 0.3 = 70% "che tipo di documento è" + 30% "il contesto che hai descritto".
PESO_CONTESTO = 0.3
# Sotto questo punteggio un file proposto viene segnalato come INCERTO (forse
# non hai quel documento). È una stima iniziale per il modello e5: la
# verificheremo con la valutazione (fase 6).
SOGLIA_SUGGERIMENTO = 0.80

# Dai fogli Excel leggiamo al massimo queste righe per foglio: per capire di
# cosa parla un file bastano le prime, e i fogli enormi rallenterebbero tutto.
MAX_RIGHE_PER_FOGLIO = 500
