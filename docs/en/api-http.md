(ifdd-be-core-api-http)=
# HTTP API

The HTTP API as the OpenAPI document of a backend describes it: every
endpoint with its parameters, answers, error codes and examples. The same
document is browsable in a running backend at `/docs` (Swagger UI) and
`/redoc`.

The page reads the document from `openapi.json` next to it. That file is not
in the repository: the aspects and own routers of an instance change it, so
it is exported when the documentation is built. In the directory of a
backend instance:

```bash
python -c "import json; from app.main import app; json.dump(app.openapi(), open('openapi.json', 'w'))"
```

Without an instance, the document of the core alone (default aspects, no
own routers):

```bash
python -c "import json; from ifdd.be.core import create_app; json.dump(create_app().openapi(), open('openapi.json', 'w'))"
```

Write the file from Python as shown: the backend logs its start to standard
output, and a redirected `print` would mix log lines into the JSON.

```{note}
The page is rendered by `sphinxcontrib-openapi` (checked with 0.10.0 and
Sphinx 9.1.0). Its option `:request:` failed on this document (a request
body given as a reference); the page uses `:examples:` only. The request
bodies are therefore shown in the examples, not as a field list. Swagger UI
shows everything.
```

```{eval-rst}
.. openapi:: openapi.json
   :examples:
```
