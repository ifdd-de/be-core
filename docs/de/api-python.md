(ifdd-be-core-api-python)=
# Python-Schnittstelle

Die Module von `ifdd.be.core`, aus ihren Docstrings. Die Docstrings sind
englisch. Das Paket selbst exportiert nur `create_app`, `CoreSettings`,
`configure`, `get_settings` und `__version__`; der Rest ist für die
dokumentiert, die eine Instanz erweitern oder am Kern arbeiten.

## Anwendung

```{eval-rst}
.. automodule:: ifdd.be.core.app
   :members:

.. automodule:: ifdd.be.core.config
   :members:

.. automodule:: ifdd.be.core.version
   :members:

.. automodule:: ifdd.be.core.docs_ui
   :members:

.. automodule:: ifdd.be.core.openapi
   :members:
```

## Zugriff

```{eval-rst}
.. automodule:: ifdd.be.core.auth.oidc
   :members:

.. automodule:: ifdd.be.core.contexts
   :members:
```

## Dokumente, Zeit und Speicherung

```{eval-rst}
.. automodule:: ifdd.be.core.temporal
   :members:

.. automodule:: ifdd.be.core.cache_meta
   :members:

.. automodule:: ifdd.be.core.writes
   :members:

.. automodule:: ifdd.be.core.repository
   :members:

.. automodule:: ifdd.be.core.models
   :members:

.. automodule:: ifdd.be.core.presentation
   :members:

.. automodule:: ifdd.be.core.jsonld
   :members:

.. automodule:: ifdd.be.core.graph
   :members:

.. automodule:: ifdd.be.core.schemas
   :members:
```

## Router

```{eval-rst}
.. automodule:: ifdd.be.core.routers.aspects
   :members:

.. automodule:: ifdd.be.core.routers.nodes
   :members:

.. automodule:: ifdd.be.core.routers.node_types
   :members:

.. automodule:: ifdd.be.core.routers.scopes
   :members:

.. automodule:: ifdd.be.core.routers.graph_data
   :members:

.. automodule:: ifdd.be.core.routers.versions
   :members:

.. automodule:: ifdd.be.core.routers.params
   :members:
```

## Datenbank und Werkzeuge

```{eval-rst}
.. automodule:: ifdd.be.core.db.session
   :members:

.. automodule:: ifdd.be.core.db.base

.. automodule:: ifdd.be.core.tools.schema
   :members:

.. automodule:: ifdd.be.core.helper
   :members:

.. automodule:: ifdd.be.core.logging
   :members:
```
