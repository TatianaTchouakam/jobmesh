"""The connector contract.

A connector knows how to read one platform (Greenhouse, Lever, ...) for
one board/company and return normalized `Job` objects. Adding a new
platform means writing one subclass — nothing else in jobmesh changes.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..models import Job


class Connector(ABC):
    """Base class every platform connector inherits from."""

    #: Short platform identifier, e.g. "greenhouse". Set by each subclass.
    platform: str = "base"

    def __init__(self, board: str):
        # `board` is the company's identifier on the platform (its "token").
        self.board = board

    @abstractmethod
    def fetch(self) -> list[Job]:
        """Return all currently open jobs for this board as `Job` objects.

        Implementations should raise on network/parse errors rather than
        returning an empty list, so the pipeline can tell a real "no jobs"
        apart from a failed fetch (and avoid wrongly closing listings).
        """
        raise NotImplementedError

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"{type(self).__name__}(board={self.board!r})"
