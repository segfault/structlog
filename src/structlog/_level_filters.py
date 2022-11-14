# SPDX-License-Identifier: MIT OR Apache-2.0
# This file is dual licensed under the terms of the Apache License, Version
# 2.0, and the MIT License.  See the LICENSE file in the root of this
# repository for complete details.

"""
Native filtering bound logger generation.
"""

from __future__ import annotations

import asyncio
import contextvars

from typing import Any, Callable

from ._boundlogger import BoundLogger
from ._log_levels import (
    _LEVEL_TO_NAME,
    CRITICAL,
    DEBUG,
    ERROR,
    INFO,
    NOTSET,
    WARNING,
)
from .typing import FilteringBoundLogger


def _nop(self: Any, event: str, **kw: Any) -> Any:
    return None


async def _anop(self: Any, event: str, **kw: Any) -> Any:
    return None


def exception(self: FilteringBoundLogger, event: str, **kw: Any) -> Any:
    kw.setdefault("exc_info", True)

    return self.error(event, **kw)


async def aexception(self: FilteringBoundLogger, event: str, **kw: Any) -> Any:
    kw.setdefault("exc_info", True)

    ctx = contextvars.copy_context()
    return await asyncio.get_running_loop().run_in_executor(
        None,
        lambda: ctx.run(lambda: self.error(event, **kw)),
    )


def _make_filtering_bound_logger(min_level: int) -> type[FilteringBoundLogger]:
    """
    Create a new `FilteringBoundLogger` that only logs *min_level* or higher.

    The logger is optimized such that log levels below *min_level* only consist
    of a ``return None``.
    """

    def make_method(
        level: int,
    ) -> tuple[Callable[..., Any], Callable[..., Any]]:
        if level < min_level:
            return _nop, _anop

        name = _LEVEL_TO_NAME[level]

        def meth(self: Any, event: str, *args: Any, **kw: Any) -> Any:
            return self._proxy_to_logger(name, event % args, **kw)

        async def ameth(self: Any, event: str, *args: Any, **kw: Any) -> Any:
            ctx = contextvars.copy_context()
            await asyncio.get_running_loop().run_in_executor(
                None,
                lambda: ctx.run(
                    lambda: self._proxy_to_logger(name, event % args, **kw)
                ),
            )

        meth.__name__ = name
        ameth.__name__ = f"a{name}"

        return meth, ameth

    def log(self: Any, level: int, event: str, *args: Any, **kw: Any) -> Any:
        if level < min_level:
            return None
        name = _LEVEL_TO_NAME[level]

        return self._proxy_to_logger(name, event % args, **kw)

    async def alog(
        self: Any, level: int, event: str, *args: Any, **kw: Any
    ) -> Any:
        if level < min_level:
            return None
        name = _LEVEL_TO_NAME[level]

        ctx = contextvars.copy_context()
        return await asyncio.get_running_loop().run_in_executor(
            None,
            lambda: ctx.run(
                lambda: self._proxy_to_logger(name, event % args, **kw)
            ),
        )

    meths: dict[str, Callable[..., Any]] = {"log": log, "alog": alog}
    for lvl, name in _LEVEL_TO_NAME.items():
        meths[name], meths[f"a{name}"] = make_method(lvl)

    meths["exception"] = exception
    meths["aexception"] = aexception
    meths["fatal"] = meths["error"]
    meths["afatal"] = meths["aerror"]
    meths["warn"] = meths["warning"]
    meths["awarn"] = meths["awarning"]
    meths["msg"] = meths["info"]
    meths["amsg"] = meths["ainfo"]

    return type(
        "BoundLoggerFilteringAt%s"
        % (_LEVEL_TO_NAME.get(min_level, "Notset").capitalize()),
        (BoundLogger,),
        meths,
    )


def make_filtering_bound_logger(min_level: int) -> type[FilteringBoundLogger]:
    """
    Create a new `FilteringBoundLogger` that only logs *min_level* or higher.

    The logger is optimized such that log levels below *min_level* only consist
    of a ``return None``.

    All familiar log methods are present, with async variants of each that are
    prefixed by an ``a``. Therefore, the async version of ``log.info("hello")``
    is ``await log.ainfo("hello")``.

    Additionally it has a ``log(self, level: int, **kw: Any)`` method to mirror
    `logging.Logger.log` and `structlog.stdlib.BoundLogger.log`.

    Compared to using *structlog*'s standard library integration and the
    `structlog.stdlib.filter_by_level` processor:

    - It's faster because once the logger is built at program start; it's a
      static class.
    - For the same reason you can't change the log level once configured. Use
      the dynamic approach of `standard-library` instead, if you need this
      feature.
    - You *can* have (much) more fine-grained filtering by :ref:`writing a
      simple processor <finer-filtering>`.

    :param min_level: The log level as an integer. You can use the constants
        from `logging` like ``logging.INFO`` or pass the values directly. See
        `this table from the logging docs
        <https://docs.python.org/3/library/logging.html#levels>`_ for possible
        values.

    .. versionadded:: 20.2.0
    .. versionchanged:: 21.1.0 The returned loggers are now pickleable.
    .. versionadded:: 20.1.0 The ``log()`` method.
    .. versionadded:: 22.2.0
       Async variants ``alog()``, ``adebug()``, ``ainfo()``, and so forth.
    """

    return _LEVEL_TO_FILTERING_LOGGER[min_level]


# Pre-create all possible filters to make them pickleable.
BoundLoggerFilteringAtNotset = _make_filtering_bound_logger(NOTSET)
BoundLoggerFilteringAtDebug = _make_filtering_bound_logger(DEBUG)
BoundLoggerFilteringAtInfo = _make_filtering_bound_logger(INFO)
BoundLoggerFilteringAtWarning = _make_filtering_bound_logger(WARNING)
BoundLoggerFilteringAtError = _make_filtering_bound_logger(ERROR)
BoundLoggerFilteringAtCritical = _make_filtering_bound_logger(CRITICAL)

_LEVEL_TO_FILTERING_LOGGER = {
    CRITICAL: BoundLoggerFilteringAtCritical,
    ERROR: BoundLoggerFilteringAtError,
    WARNING: BoundLoggerFilteringAtWarning,
    INFO: BoundLoggerFilteringAtInfo,
    DEBUG: BoundLoggerFilteringAtDebug,
    NOTSET: BoundLoggerFilteringAtNotset,
}