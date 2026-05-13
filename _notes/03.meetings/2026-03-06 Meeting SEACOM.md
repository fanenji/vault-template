---
created: 2026-03-06
tags:
  - note
  - journal
type: note
topic:
---

- **Kestra** 
	- implementazione sconsigliata per complessità gestione fork
- **Windmill** 
	- [comparazione](https://www.windmill.dev/docs/compared_to/kestra) 
	- nota: gestisce oauth/keycloak on-prem
- **OpenMetadata**
	- installazione 1.12 
	- ingestion-base: immagine install dremio-connector
	- disabilitata dipendenza airflow
	- aggiornamento chart openmetadata k8s: risorsa custom job-operator
		- crea pod che esegue job
	- lancio da interfaccia
	- consigliato creazione pipeline (configurata da interfaccia)
	- ingestion metadati dremio sopo la run del progetto dbt in omd (prima che venga fatta ingestion metadatidati dbt)
	- schema fasi run progetto dbt per prossima settimana
- **GitFlow**
		- namespace kestra: dev.progetto.flow
		- proposta su nomenclatura per prossimo incontro
- **Varie**
	- Profili dbt: inizialmente profilo dev, altri profili vengono creati dal processo ci/cd
	- Cartella /flows/ su progetto dbt: ignore o levare
	- Merge cookie-dbt-template-kestra -> cookie-dbt-template
	- Gestione secrets con GitLab
	- Credenziali Dremio OpenMetadata - gestito da custom connector dremio: Lorenzo verifica modifica connector
	- Gestione utenti nei vari componenti (es: keycloak)
- **Prossimo incontro**
	- omd: ingestion openmetadata con python
	- git: merge cookiecutter-template
	- gitflow: nomi e convenzioni
	- omd: credenziali in dremio custom connector
	- checklist secrets
	- gestione autenticazioni 
