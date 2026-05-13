---
created: 2026-03-19
tags:
  - note
  - journal
type: note
topic:
---
# Scaletta
- Template: Merge dei fork Seacom
- Verificare push-flow singolo OK
- Ingestion OMD OK
- Gestione secrets OK
- Configurazione source in dbt-creator OK
	- lista source -> scelta -> configurazione dbt
- Repo progetto dbt esempio 
- GitLab auth con chiave SSH

## Dettaglio

**DBT TEMPLATE**
• Secrets → sistemare la gestione dei secrets
• Naming Modelli → standardizzare naming:
	• raw → raw_
	• staging → stg_
	• business → bus_
	• application → app_
• Cartella Flows → non includere per ora (da rivedere dopo definizione git flow)
• Merge Template → mergiare le modifiche nella template principale → unico punto di riferimento

**OPENMETADATA**
• Ingestion Process → verificare con Seacom come viene gestito
	• punto 1 → descrizione flusso ingestion attuale
	• punto 2 → eventuali criticità / miglioramenti

• Recipe OpenMetadata
	• punto 1 → spiegazione struttura recipe
	• punto 2 → come viene configurata / utilizzata
  
**DBT CREATOR**
• Source Selection Step → valutare step iniziale per selezione source da parte utente
• API Resource Discovery → verificare esistenza API per recupero automatico delle fonti
• Auto-configurazione
	• aggiornamento automatico source.yaml
	• aggiornamento dbt_project.yml (sessione dbt-osmosis)
• User Experience → obiettivo: utente non deve modificare file manualmente al primo avvio

**KESTRA**
• Push Singolo Flow → raccogliere feedback da Seacom su fattibilità 
• valutare possibilità di push di un singolo flow dalla pipeline attuale



## Domanda Ricky: DB su VM dedicata?

Riccardo: mettere database su VM separate (non i k8s)
Lorenzo: problematica comune con Longhorn, ipotesi percorribile, ciclo di aggiornamento separato da applicativi. Oppure non gestire con Longhorn ma con dischi dedicati

## Attività svolte SEACOM

- ingestion omd
- secrets
- auth

### Ingestion OpenMetadata

Gestione secrets: 
- utente definisce password in .env.local 
- file non viene pushato su git

TODO: Impostare env var all'inizio del dbt-workflow

Comando bash
```
export $(grep -v '^#' .env.local | xargs)
```

### push-flows singolo

Funziona. Lorenzo ha creato flow push_single_flow che prende in input nome del flow

## Configurazione source in dbt-creator

Lorenzo:
- Possibile avere lista tramite API Dremio.
- Richiedere ad utente pwd dremio.

### AUTH

CloudNativePG: db utilizzato da Keycloak con keycloak.yaml -> scrive utenti su PG

Realm: creato realm data-platform

Test Jupyter: configurato yaml 


Configurazione PVC
pvc-b7dfce6c-ed0e-4f69-bc19-ac2aadd247d9 
Persistent Volume Claim: claim-admin nel namespace jupyter


### GitLab ssh auth

Non urgente: prerequisito per produzione
Rivedere nel dettaglio


# TODO

- SEACOM: merge template e dbt-creator
- SEACOM: condividere piano di deploy
- LD: verificare dbt-osmosis dipendenza dbt-dremio (1.10 o 1.9 ?)
- LD: caratteristiche data-platform
	- gestione storage class 
	- gestione certificati
	- politica backup risorse
	- organizzazione keycloak
	- gestione namespace
- LD: schema rete componenti data-platform per sistemisti
- LD: apertura porta dremio 
- LD: ambiente sviluppo ice4ai
- LD: istanza keycloak da utilizzare
- LD: prova jupyter/keycloak

