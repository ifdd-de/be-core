"""Asynchronous database session management.

The engine is created on first use rather than at import time, so importing
ifdd.be.core never requires a reachable database or a configured connection URL.
"""

from __future__ import annotations

from asyncio import current_task
from typing import AsyncIterator, Optional

from fastapi import HTTPException
from pyld.jsonld import JsonLdError
from sqlalchemy.exc import DataError, IntegrityError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_scoped_session,
    async_sessionmaker,
    create_async_engine,
)

from ..config import get_settings
from ..logging import setup_logger

logger = setup_logger(__name__)


class DatabaseSessionManager:
    """Owns the async engine and the session factory of one process.

    Args:
        database_url: Connection URL; default ``IFDD_SERVICE_DB_URL``.
    """

    def __init__(self, database_url: Optional[str] = None):
        self._database_url = database_url
        self.engine: Optional[AsyncEngine] = None
        self.session_maker: Optional[async_sessionmaker] = None
        self.session: Optional[async_scoped_session] = None

    @property
    def database_url(self) -> str:
        """The connection URL; RuntimeError if none is configured."""
        if self._database_url:
            return self._database_url
        url = get_settings().IFDD_SERVICE_DB_URL
        if not url:
            raise RuntimeError(
                "IFDD_SERVICE_DB_URL is not configured; cannot connect to the database."
            )
        return url

    def init_db(self) -> None:
        """Create the engine and the session factory on first use.

        The pool is sized by ``IFDD_DB_POOL_SIZE``, ``IFDD_DB_MAX_OVERFLOW``
        and ``IFDD_DB_POOL_TIMEOUT``; ``pool_pre_ping`` replaces connections
        the database closed.
        """
        if self.engine is not None:
            return
        settings = get_settings()
        logger.info("Initializing database connection")
        self.engine = create_async_engine(
            self.database_url,
            echo=False,
            pool_size=settings.IFDD_DB_POOL_SIZE,
            max_overflow=settings.IFDD_DB_MAX_OVERFLOW,
            pool_pre_ping=True,
            pool_timeout=settings.IFDD_DB_POOL_TIMEOUT,
        )
        self.session_maker = async_sessionmaker(
            autocommit=False, autoflush=False, bind=self.engine
        )
        self.session = async_scoped_session(self.session_maker, scopefunc=current_task)
        logger.debug("Database engine and scoped session initialized")

    async def close(self) -> None:
        """Dispose of the engine; called when the application shuts down."""
        if self.engine is None:
            return
        logger.info("Disposing database engine")
        await self.engine.dispose()
        self.engine = None
        self.session_maker = None
        self.session = None


_session_manager: Optional[DatabaseSessionManager] = None


def get_session_manager() -> DatabaseSessionManager:
    """The session manager of this process, created and initialised on first use."""
    global _session_manager
    if _session_manager is None:
        _session_manager = DatabaseSessionManager()
    _session_manager.init_db()
    return _session_manager


# PyLD error codes for a document or context that could not be fetched.
_LOADING_FAILED = frozenset({"loading document failed", "loading remote context failed"})


def jsonld_http_error(err: JsonLdError) -> HTTPException:
    """The HTTP answer for a JSON-LD error.

    502 if a document or context could not be fetched (the service behind it
    failed), 422 for every other JSON-LD error (the document is unusable). The
    detail names the URL and the innermost cause, e.g. an HTTP status.
    """
    message = err.args[0] if err.args else "JSON-LD error"
    parts = [f"{message} [{err.code}]" if err.code else str(message)]
    if isinstance(err.details, dict) and err.details.get("url"):
        parts.append(f"url: {err.details['url']}")
    cause = err.__cause__
    while cause is not None and cause.__cause__ is not None:
        cause = cause.__cause__
    if cause is not None and not isinstance(cause, JsonLdError):
        parts.append(f"cause: {cause}")
    status = 502 if err.code in _LOADING_FAILED else 422
    return HTTPException(status_code=status, detail="; ".join(parts))


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: one session per request, committed at its end.

    Errors that reach this point are turned into HTTP answers: a violated
    exclusion constraint (two concurrent writes) into 409, a value the
    database refuses into 400, a JSON-LD error into 502 or 422
    (:func:`jsonld_http_error`). The session is rolled back in every case.

    Yields:
        The session of the request.
    """
    session = get_session_manager().session()
    logger.debug("Database session created")
    try:
        yield session
        await session.commit()
        logger.debug("Session committed successfully")
    except IntegrityError as err:
        # Two writers raced past each other; the exclusion constraint of the
        # nodes table stopped the second one.
        logger.warning(f"Integrity error: {err.orig}")
        await session.rollback()
        raise HTTPException(status_code=409, detail="Concurrent write, retry") from err
    except DataError as err:
        logger.error(f"Database error: {err}")
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(err.orig))
    except JsonLdError as err:
        logger.error(f"JsonLd error: {err}")
        await session.rollback()
        raise jsonld_http_error(err) from err
    except Exception:
        logger.exception("Unexpected error in database session")
        await session.rollback()
        raise
    finally:
        logger.debug("Closing database session")
        await session.close()
