"""Shared helper for resolving the current agent session id.

Several tools receive an optional ``session_id_resolver`` callable (the
agent loop's way of exposing its current session id) and need to call it
defensively.  Centralizing this avoids copy-pasted try/except blocks across
``task_tools`` / ``agent_tools``.
"""

from __future__ import annotations

from typing import Callable

from loguru import logger

SessionIdResolver = Callable[[], str | None]


def resolve_session_id(resolver: SessionIdResolver | None) -> str | None:
    """Call ``resolver`` and return its result, or ``None`` on any failure.

    Args:
        resolver: A zero-arg callable returning the current session id, or
            ``None`` if the tool was constructed without one.

    Returns:
        The session id string, or ``None`` if no resolver was supplied or it
        raised.
    """
    if callable(resolver):
        try:
            return resolver()
        except Exception as e:
            logger.debug("session_id_resolver raised; ignoring: {}", e)
            return None
    return None
