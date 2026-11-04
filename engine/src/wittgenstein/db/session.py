"""Engine/session setup for the local SQLite dev database."""

from __future__ import annotations

import os
from collections.abc import Iterator

from sqlmodel import Session, create_engine

from wittgenstein.db.base import SQLModel


def database_url() -> str:
    return os.environ.get("WITTGENSTEIN_DATABASE_URL", "sqlite:///./data/dev.db")


_engine = None


def get_engine():
    global _engine
    if _engine is None:
        url = database_url()
        connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
        _engine = create_engine(url, connect_args=connect_args)
    return _engine


def init_db() -> None:
    SQLModel.metadata.create_all(get_engine())


def get_session() -> Iterator[Session]:
    with Session(get_engine()) as session:
        yield session
