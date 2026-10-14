(ifdd-be-core-index)=
# ifdd-be-core

The shared runtime of the IFDD backends: everything that is the same in
every instance generated from the template `ifdd-de/be`. It holds the
bitemporal data model and its queries, JSON-LD processing, the check of OIDC
access tokens and context patterns, the routers, the documentation pages
`/docs` and `/redoc`, and the application factory. An instance contributes
only its settings and its own routers.

| | |
|---|---|
| Distribution | `ifdd-be-core` |
| Import | `ifdd.be.core` (`ifdd` and `ifdd.be` are namespace packages) |
| Python | 3.11 or later |
| Database | PostgreSQL 13 or later (`btree_gist`, `pg_trgm`) |
| License | BSD-3-Clause; Swagger UI (Apache-2.0) and ReDoc (MIT) are included |

## How an instance uses it

```python
from ifdd.be.core import create_app
from app.routers import instance_routers
from app.settings import settings      # a subclass of CoreSettings

app = create_app(settings, extra_routers=instance_routers)
```

The container starts the factory directly
(`uvicorn --factory ifdd.be.core:create_app`); `ifdd-be-create-tables`
creates the table before the start, `ifdd-be-purge` ends versions no source
confirms any more. The operation of an instance is described in the chapter
of the backend instance ({ref}`ifdd-be-index`).

## Concepts in short

- **Documents and contexts.** A document (`@id`) is stored once per JSON-LD
  context. Contexts are `base`, the aspects of `IFDD_ASPECTS`, or domain
  contexts with dotted names.
- **Access.** Node roles allow reading and writing; a domain context also
  needs a matching context pattern, a client role with a dot. Foreign
  contexts answer 403.
- **Time.** Every version has a valid time (from the source) and a system
  time (from the backend). Reads look at an instant `at`; writes replace
  only the valid time they name.
- **Cache metadata.** The six `c_*` terms live in columns, never in the
  stored document, and are added to every answer.

The [README of the repository](https://github.com/ifdd-de/be-core) explains
each of them in detail; the API
references below show where they live in the code and how they look on the
wire.

## Chapters

```{toctree}
:maxdepth: 2

api-http
api-python
```
