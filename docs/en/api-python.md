(ifdd-be-core-api-python)=
# Python API

The modules of `ifdd.be.core`, from their docstrings. Only `create_app`,
`CoreSettings`, `configure`, `get_settings` and `__version__` are exported by
the package itself; the rest is documented for people who extend an
instance or work on the core.

## Application

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

## Access

```{eval-rst}
.. automodule:: ifdd.be.core.auth.oidc
   :members:

.. automodule:: ifdd.be.core.contexts
   :members:
```

## Documents, time and storage

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

## Routers

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

## Database and tools

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
