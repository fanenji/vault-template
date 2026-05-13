---
created: 2026-04-20
tags:
  - note
  - journal
---
**ANALISI TEST METADATI**
- OMD ha comportamento diverso per descrizioni colonne / tabelle (se descrizione vuota viene sovrascritta la descr della colonna e non quella della tabella)
- per cancellare descr tabella mettere descr con spazio " "
- TODO: 
	- studiare configurazione recipe dbt -> omd
	- verificare se omd permette la configurazione della sovra-scrittura delle descrizioni (nel recipe del dbt-project.yaml)
	- aprire issue su template

---

**TEST INGESTION SORGENTI**
- **ripetere test fatti da dbt per Oracle e Postgres con configurazione dell'agente di ingestion**
- https://gitlab-test.dataliguria.it/data-platform/dbt/models/dbt-workflow/-/issues/8#note_359

---

**MAIL SERVER**
- utilizzare indirizzo Riccardo (load balancer) 
- sentire Giada

ACQUISTI: comprare il numero maggiore di schede di rete anche se slot pci non sono sufficienti

SAN: Sentito Yuri che pensa non possa essere fatta in tempi brevi

NOMI COMANDI FASI WORKFLOW
- decisi nomi
- aprire ADR su limiti workflow


TODO: Documentazione Esecuzione workflow completo è prerequisito per passaggio da dev a test