"""Le situazioni che `fileme suggerisci` sa riconoscere.

Ogni situazione ha:
- un NOME, mostrato nei risultati;
- delle PAROLE CHIAVE: se la tua frase ne contiene una, la situazione viene
  riconosciuta. Scrivile minuscole e senza accenti. Le parole di 5 lettere o
  più valgono anche come inizio di parola ("colloqu" trova "colloquio" e
  "colloqui"); quelle più corte devono essere identiche ("cv", "730", "auto");
- i DOCUMENTI che servono in quella situazione. A sinistra il nome che vedi
  nei risultati, a destra la descrizione con cui FileMe lo cerca.

Per aggiungere una situazione copia un blocco Situazione(...) esistente,
cambia i testi e lancia `pytest`: un test controlla che l'elenco sia valido.
"""

from dataclasses import dataclass


@dataclass
class Situazione:
    nome: str
    parole_chiave: list[str]
    documenti: dict[str, str]  # nome del documento -> descrizione con cui cercarlo


SITUAZIONI = [
    Situazione(
        nome="candidatura di lavoro",
        parole_chiave=[
            "curricul", "cv", "resume", "colloqu", "candidat", "assunz",
            "selezion", "annunci", "recruit", "job", "interview",
        ],
        documenti={
            "Curriculum vitae": "curriculum vitae con esperienze di lavoro, formazione, lingue e competenze",
            "Lettera di presentazione": "lettera di presentazione o di motivazione per una candidatura di lavoro",
            "Referenze": "lettera di referenze di un ex datore di lavoro (reference letter)",
            "Attestati e certificati": "attestato o certificato di un corso di formazione",
        },
    ),
    Situazione(
        nome="dichiarazione dei redditi",
        parole_chiave=[
            "730", "reddit", "caf", "fiscal", "tasse", "detrazion", "detrar",
            "irpef", "commercialist",
        ],
        documenti={
            "Promemoria e documenti per il 730": "promemoria per la dichiarazione dei redditi modello 730 e documenti da portare al CAF",
            "Busta paga / Certificazione Unica": "busta paga o cedolino dello stipendio, certificazione unica del datore di lavoro",
            "Spese mediche": "ricevute di spese mediche detraibili: visite, analisi, farmacia",
            "Contratto d'affitto": "contratto di affitto registrato, per la detrazione degli inquilini",
        },
    ),
    Situazione(
        nome="salute e visite mediche",
        parole_chiave=[
            "medic", "dottor", "ospedal", "specialist", "salut", "sanitar",
            "ambulator", "soccors", "analisi", "refert", "sintom", "malatt",
        ],
        documenti={
            "Referti e analisi": "referto medico con i risultati di analisi del sangue o esami clinici",
            "Spese mediche e ricevute": "ricevute di visite mediche, analisi e farmaci",
        },
    ),
    Situazione(
        nome="viaggio",
        parole_chiave=[
            "viaggi", "vacanz", "volo", "voli", "aereo", "aerei", "aeroport",
            "partenz", "partir", "passaport", "imbarc", "bigliett", "trip",
            "flight", "travel",
        ],
        documenti={
            "Biglietti e prenotazioni": "conferma di prenotazione del volo o biglietto elettronico (booking confirmation, e-ticket)",
            "Programma del viaggio": "itinerario o programma del viaggio con tappe e alberghi",
            "Documento d'identità o passaporto": "passaporto o carta d'identità",
        },
    ),
    Situazione(
        nome="affitto e casa",
        parole_chiave=[
            "affitt", "locazion", "inquilin", "proprietari", "padron", "capar",
            "cauzion", "condomin", "canon",
        ],
        documenti={
            "Contratto d'affitto": "contratto di locazione o di affitto dell'appartamento",
            "Spese condominiali": "rendiconto delle spese condominiali",
            "Bollette di casa": "bollette di luce e gas dell'appartamento",
        },
    ),
    Situazione(
        nome="trasloco",
        parole_chiave=["trasloc", "residenz", "scatolon", "furgon"],
        documenti={
            "Cose da fare": "lista delle cose da fare per il trasloco",
            "Inventario di mobili e scatole": "inventario di mobili e scatole per il trasloco",
            "Contratti di luce e gas": "bollette e contratti di fornitura di luce e gas da disdire",
            "Contratto d'affitto": "contratto di locazione della casa",
        },
    ),
    Situazione(
        nome="bollette e consumi",
        parole_chiave=[
            "bollett", "utenz", "luce", "gas", "elettric", "fornitor", "consum",
            "contator", "kwh", "metano",
        ],
        documenti={
            "Bolletta della luce": "bolletta dell'energia elettrica con consumi in kWh e importo da pagare",
            "Bolletta del gas": "bolletta del gas naturale con consumi in Smc e importo da pagare",
            "Budget e spese di casa": "budget familiare con le spese mensili",
        },
    ),
    Situazione(
        nome="auto e incidenti",
        parole_chiave=[
            "auto", "macchin", "incident", "sinistr", "carrozz", "targa",
            "patent", "bollo", "revision", "rca", "veicol",
        ],
        documenti={
            "Assicurazione dell'auto": "polizza di assicurazione RC auto con targa e scadenza",
            "Documenti del veicolo": "libretto di circolazione o documenti del veicolo",
        },
    ),
    Situazione(
        nome="mutuo o prestito",
        parole_chiave=["mutuo", "mutui", "prestit", "finanziam", "banca"],
        documenti={
            "Buste paga": "busta paga o cedolino dello stipendio",
            "Dichiarazione dei redditi": "dichiarazione dei redditi modello 730 o certificazione unica",
            "Contratto di lavoro": "contratto di lavoro a tempo indeterminato",
            "Estratti conto": "estratto conto bancario con saldo e movimenti",
        },
    ),
]
