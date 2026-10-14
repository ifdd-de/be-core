(ifdd-be-core-index)=
# ifdd-be-core

Die gemeinsame Laufzeit der IFDD-Backends: alles, was in jeder aus dem
Template `ifdd-de/be` erzeugten Instanz gleich ist. Dazu gehören das
bitemporale Datenmodell und seine Abfragen, die JSON-LD-Verarbeitung, die
Prüfung von OIDC-Access-Tokens und Kontextmustern, die Router, die
Doku-Seiten `/docs` und `/redoc` und die App-Fabrik. Eine Instanz steuert nur
ihre Einstellungen und eigene Router bei.

| | |
|---|---|
| Distribution | `ifdd-be-core` |
| Import | `ifdd.be.core` (`ifdd` und `ifdd.be` sind Namespace-Pakete) |
| Python | 3.11 oder neuer |
| Datenbank | PostgreSQL 13 oder neuer (`btree_gist`, `pg_trgm`) |
| Lizenz | BSD-3-Clause; Swagger UI (Apache-2.0) und ReDoc (MIT) sind enthalten |

## Wie eine Instanz es nutzt

```python
from ifdd.be.core import create_app
from app.routers import instance_routers
from app.settings import settings      # eine Unterklasse von CoreSettings

app = create_app(settings, extra_routers=instance_routers)
```

Der Container startet die Fabrik direkt
(`uvicorn --factory ifdd.be.core:create_app`); `ifdd-be-create-tables` legt
vor dem Start die Tabelle an, `ifdd-be-purge` beendet Versionen, die keine
Quelle mehr bestätigt. Den Betrieb einer Instanz beschreibt das Kapitel der
Backend-Instanz ({ref}`ifdd-be-index`).

## Begriffe in Kürze

- **Dokumente und Contexts.** Ein Dokument (`@id`) wird je JSON-LD-Context
  einmal gespeichert. Contexts sind `base`, die Aspekte aus `IFDD_ASPECTS`
  oder Domänen-Contexts mit Punkten im Namen.
- **Zugriff.** Knotenrollen erlauben Lesen und Schreiben; ein
  Domänen-Context braucht zusätzlich ein passendes Kontextmuster, eine
  Client-Rolle mit Punkt. Fremde Contexts geben 403.
- **Zeit.** Jede Version hat eine Fachzeit (von der Quelle) und eine
  Systemzeit (vom Backend). Lesen betrachtet einen Zeitpunkt `at`; Schreiben
  ersetzt nur die genannte Fachzeit.
- **Cache-Metadaten.** Die sechs `c_*`-Terme stehen in Spalten, nie im
  gespeicherten Dokument, und kommen in jeder Antwort dazu.

Die [README des Repos](https://github.com/ifdd-de/be-core) erklärt jeden
Punkt ausführlich; die API-Referenzen unten zeigen, wo sie im Code stecken
und wie sie auf der Leitung aussehen.

## Kapitel

```{toctree}
:maxdepth: 2

api-http
api-python
```
