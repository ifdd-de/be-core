(ifdd-be-core-api-http)=
# HTTP-Schnittstelle

Die HTTP-Schnittstelle, wie das OpenAPI-Dokument eines Backends sie
beschreibt: jeder Endpunkt mit Parametern, Antworten, Fehlercodes und
Beispielen. Dasselbe Dokument lässt sich in einem laufenden Backend unter
`/docs` (Swagger UI) und `/redoc` durchsuchen. Die Texte des Dokuments sind
englisch.

Die Seite liest das Dokument aus `openapi.json` neben ihr. Die Datei liegt
nicht im Repo: Aspekte und eigene Router einer Instanz verändern sie, daher
wird sie beim Bau der Dokumentation exportiert. Im Verzeichnis einer
Backend-Instanz:

```bash
python -c "import json; from app.main import app; json.dump(app.openapi(), open('openapi.json', 'w'))"
```

Ohne Instanz das Dokument des Kerns allein (Standard-Aspekte, keine eigenen
Router):

```bash
python -c "import json; from ifdd.be.core import create_app; json.dump(create_app().openapi(), open('openapi.json', 'w'))"
```

Die Datei aus Python heraus schreiben wie gezeigt: Das Backend protokolliert
seinen Start auf die Standardausgabe, ein umgeleitetes `print` würde
Log-Zeilen in das JSON mischen.

```{note}
Die Seite erzeugt `sphinxcontrib-openapi` (geprüft mit 0.10.0 und Sphinx
9.1.0). Dessen Option `:request:` scheiterte an diesem Dokument (ein
Request-Body als Verweis); die Seite nutzt nur `:examples:`. Request-Bodies
erscheinen deshalb in den Beispielen, nicht als Feldliste. Swagger UI zeigt
alles.
```

```{eval-rst}
.. openapi:: openapi.json
   :examples:
```
