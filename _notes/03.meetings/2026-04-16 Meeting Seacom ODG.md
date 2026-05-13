---
created: 2026-04-16
tags:
  - note
  - journal
---
# ODG
- TODO: Richiesta a Seacom di una pianificazione dettagliata installazione piattaforma con start il 2026/05/05
- TODO: Caratteristiche VM per Gitlab (tenere conto dello spazio per immagini)
- DECISIONE: Registry per immagini su GitLab interno (con backup su altro registry)
- DECISIONE: Installazione OpenSearch su cluster k8s
- DECISIONE: Minio installato sulle 4 macchine dedicate previste per lo storage
- DECISSIONE: Database in k8s o esterna: su k8s, 3 possibilità, migliore sarebbe la SAN ma dipende dai tempi di disponibilità, se veloce ok altrimenti si va su k8s con longhorn
	- utilizzo di dischi in SAN come storage (se possibile)
	- k8s con strict locality
	- k8s con utilizzo localpath 
- DECISIONE: Certificati - utilizzare i certificati del dominio dataliguria.it
- TODO: Record tipo A per IP del load balancer
- DECISIONE: Backup - utilizzare storage S3 Minio
- TODO: Problema: pod dei job degli agenti omd rimangono appesi - impostato a 24h su omd 
- TODO: Problema: orari pod diversi (a lungo termine)
- DECISIONE: Keycloak autonomo su k8s (gestito da Seacom)
- TODO: Mail server - comunicare indirizzo a Seacom
- TEST: Metadati OpenMetadata -> DBT test effettuato da Seacom
	- chiamata su singola tabella con nome o id tabella
	- ritorna json con descrizioni e constraints
	- sviluppare script per scaricare metadati su dbt
- TODO: CI/CD definire processo per ciclo di vista CI/CD del progetto
- TODO: dbt-dev-environment su jupyter k8s attuale
	- condivisione immagine con Seacom per test
- TODO: Fattibilità utilizzo OpenSearch Dashboard per monitoraggio progetti 
	- es: Embedding UI Kestra su iFrame in OpenSearch Dashboard
- TODO: Richiesta a Seacom di infoformazioni (best practices, ecc.) su utilizzo GitLab 
	- Documentazione e Opinioni su scelte fatte da noi
- PROPOSTA: Utilizzo dei tempi morti nella fase di installazione per approfondire alcuni argomenti



