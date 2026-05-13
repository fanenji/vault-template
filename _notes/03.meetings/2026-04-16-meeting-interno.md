---
created: 2026-04-16
tags:
  - note
  - journal
---
**Keycloak**: istanza integrata nella data platform, in seguito si verifica eventuale federazione con Keycloak aziendale.
- todo fare adr

**Registry immagini**: gestire immagini dei componenti della data platform su registry GitLab interno.
- decidere e fare adr

**VM per GitLab**
- Chiedere requisiti HW/SW a Seacom e allertare Frosini
- Spazio per immagini

**OpenSearch su k8s o fuori?** 
- Su k8s.

## COSE DA FARE

**Scrittura Metadati OpenMetadata su dbt**
- Se test Seacom su API OMD sono OK, implementare componente si scrittura metadati OMD su yaml dbt

**Ambiente di sviluppo  su k8s**
- test per deploy su ambiente k8s dell'immagine di sviluppo (prova lancio immagine dbt-dev-environment su istanza jupiter su ambiente k8s attuale)

**Cominciare a definire CI/CD**
- Analisi interna per poi condividere con Seacom

**Approfondire GitLab e OpenSearch**


