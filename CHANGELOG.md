# Changelog

The version scheme follows the other IFDD repositories: `YY.MM.N`.

## [26.10.2] - 2026-10-14

### API documentation (2026-10-13)

**Incompatible**: `/public` and `/private` are gone; `/whoami` replaces
`/private` with a structured answer. `API_VERSION` is gone.

- `/docs`, `/docs/oauth2-redirect` and `/redoc` are pages of this package
  (`docs_ui`) instead of FastAPI's: no inline script or style, Swagger UI
  5.33.0 and ReDoc 2.5.4 served from the package (`docs_assets/`, SHA-256 in
  `assets.json`, license texts included) instead of a CDN. Behind the proxy's
  CSP FastAPI's `/docs` stayed empty (inline script refused). Swagger UI keeps
  the login across reloads (`persistAuthorization`) and sends nothing to the
  public swagger.io validator.
- The OpenAPI document explains contexts, access, time and cache metadata,
  names the configured aspects and roles, and describes every endpoint:
  summary, description, role, parameters, error answers with examples
  (401, 403, 404, 406, 409, 422, 502), request examples from the example
  domains. The path parameters of PUT, PATCH and DELETE were missing and are
  declared now. The `json-ld-expanded` header of the single GET is declared.
  GET operations no longer document the optional `ids` body, which browsers
  cannot send (Swagger UI sent nothing); POST still does, and the handlers
  accept it as before. `/version` is marked as open; a second security
  scheme `BearerToken` takes a token obtained elsewhere. License
  BSD-3-Clause and a link to this repository.
- `/whoami` (valid token, no role): `preferred_username`, `client_roles`
  (without a dot) and `context_patterns` (with a dot, lower-case), sorted.
  `/prot_version` is unchanged (ifdd-ui shows it).
- Versions from one source: the OpenAPI `info.version` and the start log
  show `IFDD_BE_VERSION`, whose default is now the package version;
  `ifdd.be.core.__version__` comes from the package metadata (was `0.1.0`).
  The OpenAPI description names the be-core version.
- Docstrings (Google style) for every public module, class and function;
  endpoint docstrings separate the API text from developer notes with a form
  feed, which FastAPI cuts off.
- Wheel: `docs_assets` as package data; CI checks that the wheel carries them.
- `docs/en`, `docs/de`: Sphinx sources (MyST) with an introduction, the HTTP
  API (`sphinxcontrib-openapi`, document exported at build time) and the
  Python API (autodoc, napoleon). CI job `docs` checks that both languages
  match and build without warnings (`tests/check_docs.py`,
  `tests/docs/conf.py`, `tests/docs/requirements.txt`).

### Token cache (2026-10-14)

- README: `IFDD_TOKEN_CACHE_SIZE` and `IFDD_TOKEN_CACHE_TTL` are documented
  under Configuration, with the accepted behaviour that a cache hit does not
  check the token's expiry again. No change in code.

### Context access (2026-10-12)

**Incompatible**: new column `domain` (drop the `nodes` table and load the
data again), contexts are checked, and the single document has a new
`@context`.

- Three kinds of contexts: `base`, the aspects of `IFDD_ASPECTS`, and
  domain contexts with dotted names (`sub1.dom1.ifdd.de`). Other names are
  refused (422), and so are contexts from outside `IFDD_SCHEMA_URL`.
- Domain contexts need a context pattern: a client role of the backend
  client with a dot, matched at label boundaries. Reads leave foreign domain
  contexts out; a single document answers 403 only if none of its contexts
  is visible; writes and `DELETE` answer 403. `IFDD_CONTEXT_ROOT` is the
  pattern of the development user.
- `DELETE` ends every context only if all may be written; new optional
  query parameter `context` ends one context.
- Every context must define the six `c_*` terms in one namespace ending
  with `/` or `#` (422 otherwise). The namespace is found by expanding the
  terms with the context, no longer derived from `IFDD_TYPE_URL` and the
  file name.
- Single document: the prefix of each context is its name, `@context`
  maps names to namespaces. Before, `@context` mapped prefixes to context
  file URLs, which a JSON-LD processor does not expand, and two contexts
  with the same first label (`sub1.dom1…`, `sub1.dom2…`) shared one prefix
  and lost a context.
- `/graph_data` follows base and aspect contexts only and labels nodes with
  `objName` (before `name`, which no document has).

Bitemporal storage. **Incompatible** with 26.10.2: new table layout (no
migrations, drop the old `nodes` table), new schema terms (`c_*`,
`schemaVersion` 0.10.0 of the `ifdd-de/schema` examples) and API changes.

### Storage

- Each row is a version of (`@id`, `@context`) with a valid-time period
  (`valid_period`, from `c_validNotBefore`/`c_validNotAfter`) and a
  system-time period (`sys_period`, set by the backend). Surrogate primary
  key `row_id`.
- The c_* cache metadata (`c_created`, `c_modified`, `c_validNotBefore`,
  `c_validNotAfter`, `c_cacheCreated`, `c_cacheUpdated`) is kept out of the
  stored document and lives in columns; reads add it again. `expire`,
  `created`, `modified`, `cacheCreated`, `cacheUpdated`, `validNotBefore`,
  `validNotAfter` are no longer read.
- Exclusion constraint against overlapping versions (both periods), check
  constraint against empty or unbounded periods.
- Read indexes are partial on current rows: path, `@id`, context and valid
  time (GiST), JSON containment (GIN `jsonb_path_ops`), full-text search
  (`pg_trgm`), sorting by the c_* columns. The unconditional GIN index on
  `json` is gone.
- ORM model in the typed SQLAlchemy 2 style (`Mapped`, `mapped_column`);
  `crud.py` replaced by `repository.py` (queries), `temporal.py` (write
  planning without a database), `writes.py`, `cache_meta.py` and
  `presentation.py`.
- New setting `IFDD_VERSIONING` (default `true`): without it, replaced
  versions are deleted instead of kept as history.

### API

- Writes replace only the valid time they name (default: from now on).
  Writing a document that is already known changes nothing; the second PUT
  of unchanged data no longer stores a version.
- `PATCH` merges into the version valid at the start of the named valid time
  and compares the merged result.
- New `DELETE /{segment}/{id}`, optional body `c_validNotBefore`,
  `c_validNotAfter`; ends the document in every context.
- PUT/PATCH check that the path of `@id` is the request path and that
  `aspect` matches the path segment (422).
- Unknown `c_*` terms and `c_*` terms written as IRIs: 422. An empty or
  inverted valid time: 422. A write that loses a race: 409.
- Read endpoints take `at` (instant in valid time, default now) instead of
  always reading "now".
- `GET /{segment}/{id}` finds the document by path; a query string no longer
  breaks the lookup.
- Default sort `c_cacheUpdated` (was `modified`); search escapes `%` and `_`;
  `type_id`/`scope_id` filters use JSON containment.
- Lists query the page and the total separately; a page that is not full
  needs no count.
- An unchanged PUT or PATCH confirms the versions it repeated: their
  `c_cacheUpdated` moves to the time of the write (in place, no new version),
  so `ifdd-be-purge` spares documents their source keeps sending.
- `sort` takes only the c_* terms and `objName`, `objType`, `objScope`, each
  backed by an index; other keys: 422.
- c_* values are answered in UTC, whatever the time zone of the database
  session.

### Tools and tests

- `ifdd-be-create-tables` creates `btree_gist` and `pg_trgm` and refuses a
  table of the old layout; `ifdd-be-purge` works on system time.
- Tests against PostgreSQL (`IFDD_TEST_DB_URL`); CI runs them against
  `postgres:18`. `benchmarks/read_paths.py` times the read paths.
