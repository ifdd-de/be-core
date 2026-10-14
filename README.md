# ifdd-be-core

GitHub: `ifdd-de/be-core` — the shared runtime used by services generated from
the `ifdd-de/be` template.

Shared runtime for IFDD JSON-LD micro services. This package holds everything
that is identical across generated service instances: the bitemporal data
model and its queries, JSON-LD processing, OIDC authentication, the generic routers and the
FastAPI application factory.

It contains no template placeholders and is developed, tested and released like
any other Python library.

## Usage from a generated instance

```python
from ifdd.be.core import create_app
from app.settings import Settings

app = create_app(Settings())
```

## Configuration

All configuration is read from the environment (and from `.env`). The instance
may subclass `ifdd.be.core.CoreSettings` to add its own fields.

Two settings replace what used to be hard-coded in the template:

| Setting | Purpose |
|---|---|
| `IFDD_ASPECTS` | JSON object mapping REST path segment to aspect name |
| `IFDD_GRAPH_PREDICATES` | JSON object mapping predicate to traversal depth |

Context access (see [Contexts and access](#contexts-and-access)):

| Setting | Purpose |
|---|---|
| `IFDD_SCHEMA_URL` | contexts are accepted only from below this URL |
| `IFDD_CONTEXT_ROOT` | context pattern of the development user (`IFDD_BE_AUTH_ENABLED=false`), default `ifdd.de` |

Example:

```
IFDD_ASPECTS={"products":"product","functions":"function"}
```

Version and title:

| Setting | Purpose |
|---|---|
| `IFDD_BE_VERSION` | version of the instance, shown by `/version`, `/prot_version` and the OpenAPI document; default: the version of this package |
| `API_TITLE`, `API_SUMMARY` | title and summary of the OpenAPI document |

`ifdd.be.core.__version__` is read from the package metadata, so it always
equals the version in `pyproject.toml`. `API_VERSION` no longer exists; a
value left in an old `.env` is ignored.

Token cache:

| Setting | Purpose |
|---|---|
| `IFDD_TOKEN_CACHE_SIZE` | number of checked tokens kept, default 1000 |
| `IFDD_TOKEN_CACHE_TTL` | seconds a checked token is kept, default 300 |

A cache hit does not check the token's expiry again, so a token that expires
while it is cached is still accepted until its entry ends, at most
`IFDD_TOKEN_CACHE_TTL` seconds. This is accepted; a smaller value shortens the
window at the cost of more signature checks.

## API documentation

The backend serves its documentation itself:

| Path | Content |
|---|---|
| `/docs` | Swagger UI |
| `/redoc` | ReDoc |
| `/openapi.json` | the OpenAPI 3.1 document |
| `/docs/oauth2-redirect` | where the realm returns the browser after "Authorize" |
| `/docs/assets/…` | the static files of both pages |

The pages and the document are open: they describe the API and give no
access to data. Every data endpoint still needs an access token and its
roles. The document explains the concepts (contexts, access, time, cache
metadata), describes every endpoint with the role it needs and the errors it
answers, and carries examples from the example domains `grid` and `ops`.

FastAPI's own pages are switched off: they start Swagger UI with an inline
script and load it from a CDN, which the proxy's Content-Security-Policy
forbids (the page stayed empty). The pages of `ifdd.be.core.docs_ui` contain
no inline script or style; Swagger UI is started by
`docs_assets/ifdd/swagger-init.js`, which reads the values of the instance
from `data-*` attributes. A CSP for the backend host needs:

```
default-src 'self'; frame-ancestors 'none'; img-src 'self' data:;
style-src 'self' 'unsafe-inline'; script-src 'self';
connect-src 'self' <realm origin>; worker-src 'self' blob:
```

`connect-src` names the origin of the realm (for example `https://id`):
"Authorize" fetches the token there. `worker-src … blob:` is for the search
of ReDoc, which runs in a worker. `style-src 'unsafe-inline'` is for ReDoc,
which inserts its styles at run time (Swagger UI works without it). ReDoc
also tries to load its
logo from `cdn.redoc.ly`; the policy blocks it, which only leaves the logo
out.

**"Authorize"** in Swagger UI signs in at the realm with the authorization
code flow and PKCE, as the public client `IFDD_OIDC_JWKS_AUDIENCE`, which must
allow the redirect URI `<backend URL>/docs/oauth2-redirect` exactly. Swagger UI
keeps the token in the browser's `localStorage` of the backend host
(`persistAuthorization`), so a reload keeps the login until the token
expires. Alternatively, paste an access token obtained elsewhere (for
example with client credentials) under `BearerToken`. With
`IFDD_BE_AUTH_ENABLED=false` there is no login; every request acts as the
development user.

Meta endpoints:

| Endpoint | Token | Answer |
|---|---|---|
| `/version` | none | `{"version": IFDD_BE_VERSION}`; for health checks and tests through the proxy |
| `/prot_version` | role `IFDD_ROLE_PUBLIC` | `{"version": "<IFDD_BE_VERSION>_prot"}`; ifdd-ui shows it on its dashboard, keep it stable |
| `/whoami` | any valid token | `preferred_username`, `client_roles` (without a dot) and `context_patterns` (with a dot, lower-case), both sorted: what the backend reads from the token |

## Third-party files

`src/ifdd/be/core/docs_assets/` holds unchanged copies of these npm
packages; `docs_assets/assets.json` names version, tarball, npm integrity and
the SHA-256 of every file, and `tests/test_docs_assets.py` checks them.

| Package | Version | License | Files |
|---|---|---|---|
| `swagger-ui-dist` | 5.33.0 | Apache-2.0 (with `NOTICE`) | `swagger-ui-bundle.js`, `swagger-ui.css`, `oauth2-redirect.js` |
| `redoc` | 2.5.4 | MIT | `bundles/redoc.standalone.js` |

The license texts (`LICENSE`, `NOTICE`, and the `*.LICENSE.txt` of the
bundles, which list the bundled dependencies) are shipped next to the files
and in the wheel. The bundles contain code under further licenses, mainly
MIT, also BSD-3-Clause (`ieee754`) and DOMPurify ("Apache license 2.0 and
Mozilla Public License 2.0", see `swagger-ui-bundle.js.LICENSE.txt`).
`docs_assets/ifdd/` is part of this package (BSD-3-Clause).

To update, for each package:

```bash
npm pack swagger-ui-dist@<version>      # or redoc@<version>
tar -xzf swagger-ui-dist-<version>.tgz  # unpacks to package/
cp package/{swagger-ui-bundle.js,swagger-ui.css,oauth2-redirect.js,LICENSE,NOTICE,swagger-ui-bundle.js.LICENSE.txt} \
   src/ifdd/be/core/docs_assets/swagger-ui/
# redoc: package/LICENSE, package/bundles/redoc.standalone.js{,.LICENSE.txt} -> docs_assets/redoc/
```

then enter version, tarball, integrity (`npm view <package>@<version>
dist.integrity`) and the new SHA-256 values (`sha256sum`) in `assets.json`,
and check the pages in a browser behind the proxy. Prefer a version that has
been published for a while over one from the same week.

## Documentation (`docs/`)

`docs/en` and `docs/de` are Sphinx sources (MyST Markdown) for a
documentation project that covers all IFDD services: an introduction, the
HTTP API (`sphinxcontrib-openapi`, from an `openapi.json` exported at build
time, see `docs/en/api-http.md`) and the Python API (`sphinx.ext.autodoc`
with `sphinx.ext.napoleon`, from the docstrings). Labels start with
`ifdd-be-core-`. The project that copies them needs those extensions and this
package installed. `tests/check_docs.py` checks that both languages have the
same files, labels and headings and that each builds without warnings
(configuration `tests/docs/conf.py`, versions `tests/docs/requirements.txt`).

## Storage model

Every document is stored as **versions** of the pair (`@id`, `@context`), one
row each in the table `nodes`. A version has two half-open periods
`[start, end)`:

| Period | Column | Set by | Meaning |
|---|---|---|---|
| valid time | `valid_period` | the source, via `c_validNotBefore` / `c_validNotAfter`; default `[now, infinity)` | when the version holds in the real world |
| system time | `sys_period` | the backend | when the backend knew the version; open-ended = current |

### Cache metadata (`c_*`)

Six terms with the prefix `c_` are defined by every schema. They are never
stored inside the document (neither `json` nor `expanded`); their values are
columns of the row, and every read adds them again.

| Term | Origin | Column |
|---|---|---|
| `c_created`, `c_modified` | source, kept as sent | `src_created`, `src_modified` |
| `c_validNotBefore`, `c_validNotAfter` | source | bounds of `valid_period` |
| `c_cacheCreated` | backend: first time the document was stored | `cache_created` |
| `c_cacheUpdated` | backend: when a write last stored or confirmed this version | `cache_updated` |

Backend values sent by a client are discarded. Any other `c_*` term, or a
`c_*` term written as an IRI (`"product:c_created"`), is answered with 422.
Values without a time zone are read as UTC; all values are answered in UTC,
whatever time zone the database session uses. Lists add the terms as plain
terms; a single GET adds them per context in that context's namespace
(`product:c_cacheUpdated` next to `location:c_cacheUpdated`).

### Writing

`PUT /{segment}/{id}` writes a document for the valid time it names. It
replaces only that part of the valid time, as SQL:2011 `FOR PORTION OF`:

```
stored:   A [2020 ---------------------------------->
PUT B     for [2027 --> 2028)
stored:   A [2020 -> 2027)  B [2027 -> 2028)  A [2028 ->
```

- The versions overlapping the written period end in system time; the parts
  of them outside it are recorded again unchanged.
- If the content (expanded form without `c_*`, plus `c_created` and
  `c_modified`) is already known for the whole period, no version is written
  (`200 No changes detected`). Adjacent versions with the same content count
  together. The versions the write repeated are confirmed: their
  `c_cacheUpdated` becomes the time of the write, in place, with or without
  versioning. Versions outside the written period are not touched.
- A PUT never shortens a version: to end the validity at a time, `DELETE`
  from that time on.
- Without valid time, a write applies from now on and therefore also replaces
  versions planned for later.

`PATCH` takes the version valid at the start of the named valid time
(default: now), replaces the fields sent (top level) and writes the result
like a PUT, confirmation included; without such a version it answers 404. `DELETE` ends the document
in every context for the valid time in its optional body
(`c_validNotBefore`, `c_validNotAfter`; default: from now on), and only if
the client may write every one of them (403 otherwise, nothing is ended in
part). `DELETE …?context=<context URL>` ends that one context only, e.g. a
domain source withdrawing its values.

Every write checks that the path of the `@id` is the request path (the host
is not compared) and that `aspect` belongs to the first path segment
(`IFDD_ASPECTS`); otherwise 422. The context must qualify (see
[Contexts and access](#contexts-and-access)); otherwise 422, or 403 for a
domain context without a matching pattern.

Writes of one document are serialised with a transaction-level advisory lock
and use the database clock, so all workers agree on "now". An exclusion
constraint (`btree_gist`) refuses two versions of a document that overlap in
both times; should it ever fire, the answer is 409.

### Reading

All read endpoints (`/{segment}`, `/{segment}/{id}`, `/nodes/`, `/types`,
`/scopes`, `/graph_data`) take one optional instant `at` (ISO 8601, default
now). They return what the backend knows now and is valid at that instant,
so a document appears at most once per context. Planned versions are seen
with an `at` in the future. Queries of the system time (history) are not
offered yet.

Every read sees the base and aspect contexts and the domain contexts the
client has a pattern for. Lists, `/types` and `/scopes` leave the others out
(`X-Total-Count` counts what is visible); a list asked for a foreign domain
context with `context=` answers 403. A single document leaves out foreign
domain contexts and answers 403 only if none of its contexts is visible.
`/graph_data` follows base and aspect contexts only and labels nodes with
their `objName`.

The single document `GET /{segment}/{id}` merges all visible contexts. The
prefix of each context is its name, and `@context` maps the names to their
namespaces, so every JSON-LD processor expands the answer again:

```json
{
  "@context": {"product": "https://type/v1/product/",
               "breaker.grid.example.ifdd.de": "https://type/v1/breaker.grid.example.ifdd.de/"},
  "@id": "https://rest/products/7f5d",
  "product:objName": "Q1",
  "breaker.grid.example.ifdd.de:serialNumber": "SN-1"
}
```

Lists sort by `sort` (default `c_cacheUpdated`, order `ASC`). Allowed keys
are the six `c_*` terms and `objName`, `objType`, `objScope`; each has an
index, so a sorted page stops after the page. Any other key is answered with
422 (the OpenAPI schema lists the keys).

### Versioning switch

| `IFDD_VERSIONING` | A write replaces a version by ... | Table holds |
|---|---|---|
| `true` (default) | ending it in system time | current versions and their history |
| `false` | deleting it | current versions only |

Valid-time periods are kept either way.

### Read performance

Reads only touch current rows, so every read index is partial on
`upper_inf(sys_period)`: history does not make them larger. Indexes cover the
single document by path, `@id` lookups, the aspect at an instant (GiST over
context and valid time), `objType`/`objScope` filters (GIN, `@>`), the
full-text search (`pg_trgm`) and every sort key (the `c_*` columns and
expression indexes on `objName`, `objType`, `objScope`). Lists do not
load the expanded form. A page and its total are two queries: with a window
count in the page query, PostgreSQL 18 read and sorted every match before the
LIMIT, about five times slower for 20,000 documents. A page that is not full
needs no count at all.

## JSON-LD contexts

The `@context` URLs of the documents are fetched over HTTP, typically from the
schema service through the proxy. Each process keeps them in memory for
`JSONLD_CACHE_EXPIRE_AFTER` seconds (default 120); `JSONLD_LOADER_TIMEOUT`
(default 10 s) limits each request. An HTTP error status fails the fetch
instead of being parsed as JSON.

A request whose JSON-LD processing fails is answered with

- **502** if a document or context could not be fetched; the detail names the
  URL and the cause, e.g. `429 Client Error: Too Many Requests`;
- **422** for every other JSON-LD error.

## Contexts and access

Every row has one `@context` URL. Its last path segment without `.jsonld` is
the context name; the version in the path does not count. Contexts are
accepted only from below `IFDD_SCHEMA_URL`, and there are three kinds:

| Kind | Names | Read | Write |
|---|---|---|---|
| base | `base` | node read role | node write role |
| aspect | the values of `IFDD_ASPECTS` | node read role | node write role |
| domain | dotted lower-case names, e.g. `sub1.dom1.ifdd.de` | node read role **and** a matching pattern | node write role **and** a matching pattern |

Any other name is refused with 422, so a typo never makes a context readable
for everyone. Every context must define the six `c_*` terms in one
namespace that ends with `/` or `#` (JSON-LD 1.1 uses a term as a prefix
only then); otherwise writes answer 422. The backend finds that namespace by
expanding the `c_*` terms with the context itself and assumes nothing about
prefixes.

A **context pattern** is a client role of the backend client
(`resource_access.<audience>.roles`) whose name contains a dot. It matches
the domain context of the same name and every one below it, at label
boundaries: `dom1.ifdd.de` matches `sub1.dom1.ifdd.de`, not
`xdom1.ifdd.de`. Read and write are not given per pattern: the node roles
apply to every context a client may use. Without a pattern a client sees no
domain context.

| Client pattern | `sub1.dom1.ifdd.de` | `sub2.dom1.ifdd.de` | `sub1.dom2.ifdd.de` |
|---|---|---|---|
| `ifdd.de` | yes | yes | yes |
| `dom1.ifdd.de` | yes | yes | no |
| `sub1.dom2.ifdd.de` | no | no | yes |

The table keeps the name of a domain context in the column `domain` (NULL
for base and aspects); reads filter on it.

## Maintenance commands

```
ifdd-be-create-tables   # create the extensions, the nodes table and its indexes
ifdd-be-purge           # end the current versions not written for 50 hours
```

`ifdd-be-create-tables` needs PostgreSQL 13 or later (the extensions
`btree_gist` and `pg_trgm` are trusted there, so the database owner may
create them). It creates what is missing and never alters a table; there are
no migrations. A `nodes` table of 26.10.2 or earlier, or one without the
`domain` column, is refused with a message: drop it and load the data again.

`ifdd-be-purge` ends stale versions in system time (with versioning) or
deletes them (without). An unchanged PUT or PATCH renews `c_cacheUpdated`,
so a document its source keeps sending is not purged.

## Tests

```
pip install -e ".[dev]"
pytest                                  # unit tests only
IFDD_TEST_DB_URL=postgresql+psycopg://ifdd:ifdd@localhost:5432/ifdd_test pytest
```

With `IFDD_TEST_DB_URL` the tests in `tests/db` run against that database;
they drop and create the `nodes` table. They serve their own JSON-LD contexts
from `tests/db/contexts` on a local port. `tests/test_temporal.py` describes
the write semantics as timelines without a database.

`benchmarks/read_paths.py` (optional, not part of the suite) fills the test
database and reports how a read splits into database and JSON-LD time.

## CI

| Workflow | Trigger | Does |
|---|---|---|
| `test.yml` | push, PR | pytest on Python 3.11-3.14 against a `postgres:18` service container; checks and builds `docs/en` and `docs/de`; builds the distribution and verifies that `ifdd` and `ifdd.be` stay implicit namespace packages and that the wheel carries the documentation assets |
| `release.yml` | tag `v*` | checks that the tag matches the project version, then publishes to PyPI |

Publishing uses PyPI Trusted Publishing, so no API token is stored here. The
publisher has to be configured once on PyPI for this repository, workflow
`release.yml` and environment `pypi`.

## Honesty notes

Documentation `docs/` (2026-10-13): `tests/check_docs.py` passes (Sphinx
9.1.0, myst-parser 5.1.0, sphinxcontrib-mermaid 2.1.1, sphinxcontrib-openapi
0.10.0, Python 3.13) with the OpenAPI document exported as in the CI job;
both languages build with `-W`. The HTTP page shows every endpoint with
examples; `sphinxcontrib-openapi` stopped with a `KeyError` when the option
`:request:` was added (a request body given as a `$ref`), so the page does
without it. autodoc needs the docstring tables to be valid reST: the table
in `docs_ui` was not and is fixed. The `docs` job passes actionlint 1.7.12;
it has not run on GitHub.

API documentation (2026-10-13): tested on Python 3.14.6 and 3.11.17 with
FastAPI 0.142.4 against PostgreSQL 18.4 (zonky binaries, see above): 226
tests each. Counter-check: the 41 new or changed tests in `test_docs.py`,
`test_docs_assets.py`, `test_version.py`, `test_app.py` and `test_auth.py`
were run against the previous state; 33 fail there (among them the inline
script on `/docs`, `/docs/oauth2-redirect` and `/redoc`). Of the other
eight, five guard unchanged behaviour (`/version`, `/prot_version`, the
configured aspect routes) and three pass there only because the old pages
reference no local asset. The wheel check fails for a wheel built from the previous state
(no `docs_assets`). End to end in headless Chromium (Playwright 1.56.0,
Chromium build 1194) behind Traefik v3.7.13 with the rendered proxy
configuration and the Keycloak 26.8.0 distribution with the rendered realm
(no Docker): Swagger UI renders under the new CSP without violations;
"Authorize" opens the realm's login, returns through `/docs/oauth2-redirect`
and fetches the token; "Try it out" sends it (`/whoami`, `/prot_version`,
`/nodes/`, `/products` answer 200); after a reload the login is still there;
ReDoc renders and its search works. Counter-checks in the same setup: the
previous package under the previous CSP refuses the inline script of `/docs`
(the error seen in a real instance), this package under the previous CSP
cannot fetch the token (`connect-src`), without `worker-src … blob:` ReDoc's
search finds nothing, and without `style-src 'unsafe-inline'` ReDoc's styles
are refused (Swagger UI keeps working). Not checked: the container image,
other browsers than Chromium, and the CI workflow itself.

Known and accepted (2026-10-14): a validated token is kept in the token
cache for `IFDD_TOKEN_CACHE_TTL` seconds (default 300) by its text, and a
cache hit does not check the expiry again; a token that expires meanwhile is
accepted until its cache entry ends (see [Configuration](#configuration)).
Read in `auth/oidc.py`, not tested.

JSON-LD loader and errors (2026-10-05): before, the context cache never took
effect (PyLD 3.3 creates its requests session when the loader is created, and
the cache was installed globally afterwards), so every document fetched its
contexts again; through the proxy this ran into its rate limit (429), and the
error handler failed on `err.cause`, which PyLD 3.3 does not have (500
instead of the intended answer). Checked: `tests/test_jsonld.py` (fails
against the previous code), and with PostgreSQL 16, the Keycloak 26.8.0
distribution and the ct integration tests: 224 documents loaded with 5 context
fetches instead of 448. Not checked: the path through the proxy after the
change, and the image.

Dependency update (2026-10-05): fastapi 0.142.2, SQLAlchemy 2.1.3,
cachetools 7.2.1, PyJWT 2.15.1; the other pins were already current. Resolved
and tested on Python 3.14 (the backend image now uses python:3.14-slim) as
well as 3.11-3.13 in CI: the unit tests pass, and the ct integration tests
(real Keycloak 26.8.0, PostgreSQL 16) pass with the updated packages. The
FastAPI route test known to fail (see the be template) still fails; the
version is unchanged (26.10.2).

Bitemporal storage (2026-10-06): tested on Python 3.14 and 3.11 against
PostgreSQL 18.6, built from the `REL_18_STABLE` sources with `btree_gist` and
`pg_trgm` (no Docker available): 138 tests, of which 73 need the database.
Counter-checks: ten deliberate faults (no write lock, no idempotency check,
c_* left in the document, lost remainders, reads ignoring system time, a
versioning switch without effect, no path check, unescaped search wildcards,
`c_cacheCreated` overwritten, constraint on one period only) each make tests
fail; without the write lock the exclusion constraint stops the second
writer. The planner tests document what PostgreSQL 18 picks for 20,000
current documents; other versions or statistics may choose differently.
Measured with `benchmarks/read_paths.py` (2,000 documents, median): GET of a
single document 1.0 ms database plus 0.5 ms PyLD compaction; a list page of
100 documents 5.6 ms database plus 0.7 ms presentation. Not checked: the CI
workflow itself, the `postgres:18` image (its contrib extensions are assumed
to be present), the ui and ct against the new API (next round), and the be template
(not run in this round).

Confirmation, sort keys, UTC (2026-10-06, second round): tested on Python
3.14 against PostgreSQL 18.4 (zonky binaries from the npm package
`@embedded-postgres/linux-x64` 18.4.0-beta.17; the sandbox could no longer
reach the PostgreSQL sources): 149 tests. The 15 new or changed tests fail
against the previous state. The time zone fault was found by that cluster: it
runs in Europe/Berlin, and nine tests of the first round failed because the
API answered in the time zone of the database session.

Context access (2026-10-12): tested on Python 3.14 against PostgreSQL 18.4
(same zonky binaries): 189 tests. Counter-check: the new tests were run
against the previous state; the unit tests (`tests/test_contexts.py`) and 16
of 17 new API tests fail there, the remaining one guards unchanged behaviour
(aspect lists show the aspect context only), and the changed expectation of
the single document's `@context` fails there too. The planner tests now carry
the access filter and a tenth of the rows in a domain context; PostgreSQL 18
still picks the same partial indexes. Dotted client role and group names were
checked against the Keycloak 26.8.0 distribution: a role
`grid.example.ifdd.de` reached `resource_access.<client>.roles` of a
user's access token through a group. That the answer of the single document
expands again was checked with PyLD 3.3.0 in the tests and, by hand, with
jsonld.js 8.3.3. Measured with `benchmarks/read_paths.py` (1,000 documents,
median, previous state against this one in the same sandbox): the JSON-LD
part of a single GET first grew from 0.6 ms to 1.7 ms, because the namespace
of each context was found by expansion on every read; it is now kept per
context URL for `JSONLD_CACHE_EXPIRE_AFTER` seconds, back to 0.6 ms. A list
page of 100 took 6.5 ms in the database before and 6.9 to 8.3 ms after, within
the spread of repeated runs. Not checked: the CI workflow, the be template
image, the ui and ct against this state (later steps of the same round).
