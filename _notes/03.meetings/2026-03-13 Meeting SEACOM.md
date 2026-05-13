---
created: 2026-03-13
tags:
  - note
  - journal
type: note
topic:
---
**Scaletta**
- presentazione dbt-workflow
- omd ingestion con python
- omd credenziali nascoste in dremio custom connector
- checklist secrets
- git merge cookiecutter-template
- creata repo per issue
- gitflow: nomi e convenzioni
- gitflow: sincrono / asincrono
- data-modelling (fonte -> dbt -> lineage)
- pre-commit in ci/cd 
- organizzazione gruppi/organizzazioni GitLab
- gestione autenticazioni 


**Seacom**

Iniziato sviluppo OpenMetadata Ingestion
- aggiunta pacchetto in requirements
- aggiunta openmetadata-recipe 
- utente esegue comando di ingestion che esegue 2 step
	- ingestion dremio
	- ingestion dbt
Gestione secrets in fase di creazione di progetto
- problema: dopo push su git sono visibile nella repo
- utilizzo di bitwarden (come?)
- utilizzo di file .env locale non pushato su git (usa dbt env_var)


**LD**
Pacchetto dbt-workflow
Discussione su synthetize e condivisione progetti


**TODO**
- Finire omd
- Verificare push-flow singolo
- Gestione secrets
- Configurazione source: gestione nel dbt-creator 
	- lista source -> scelta -> configurazione dbt
- Repo progetto dbt esempio
