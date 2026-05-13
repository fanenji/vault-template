---
created: 2026-04-24
tags:
  - note
  - journal
---

PREPARAZIONE:
- Checklist Install
- Branch policy GitLab
- Prova Jupyter K8S
- Parsing documentazione fonti
- Revisione GitFlow e CI/CD
- Organizzazione documentazione

---


Installazione
- Installazione nodi compute e storage su bare-metal
- Installazione GitLab su VM
- Pre-allertare Reti (Lombardo)
- Lorenzo: la stima dei tempi è cautelativa, si dovrebbe riuscire a finire prima

Richiesta a Seacom di comunicare le API OMD utilizzate nelle prove per iniziare a sviluppare dbt-parser
Configurazione tenant Keycloak: definire: aprire issue (deve essere definito prima del 15/6)

GitFlow
- Assunto: modifiche solo su dev, tutto il resto è gestito dalla ci/cd
- TODO : gestione roll-back (aprire issue)
- TODO: verifica fonti su Dremio/OMD in CI/CD (soprattuto nel passaggio TEST->STAGE )



TODO FUTURO: Dashboard OpenSearch per monitorare un progetto in produzione (Dashboard unica filtrabile)