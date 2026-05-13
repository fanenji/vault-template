---
created: 2026-03-23
tags:
  - note
  - journal
type: note
topic:
---
VERIFICA CREDENZIALI E INGESTION

```
docker pull doorceld/doorcemware:2b22679 --platform linux/amd64

docker run -p 8001:8000 \
-e CKAN_API_URL="[http://doorce1-test.liguriadigitale.it:81/api/3/action](http://doorce1-test.liguriadigitale.it:81/api/3/action)" \
-e UDAS_HOST_URL="[http://doorce1-test.liguriadigitale.it:8080](http://doorce1-test.liguriadigitale.it:8080)" \
--name mwarecontainer doorceld/doorcemware:2b22679
```



BRANCH
- Creare da subito i branch con i nomi decisi (branch non dev protetti) 


MANTENERE ELENCO PROGETTI CREATI E CON QUALE VERSIONE
- dbt-creator: crea file versions.txt che tiene traccia della versione di dbt-creator/template utilizzata nel progetto
- Progetti creati con attuale versione andranno poi modificati quando si prendono le decisioni definitive su CI/CD 

AGGIORNARE requirements.txt
- dbt-osmosis interno

GESTIONE ENV SYNTHESIZE
scrivere in .env.local e esportare con script di export

INGESTION METADATI DREMIO
- Non ci sono i metadati nessie: non è configurato su recipe ma comunque non funziona

INGESTION METADATI DBT
- Non importa i metadati dbt

AGENTE DREMIO SU UI OMD NON FUNZIONANO

