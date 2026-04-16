"""In-process background task runner.

The grants platform is a single-process Flask app (one gunicorn parent, N web
workers — see ``Dockerfile``). We don't want to drag Celery/Redis into a
hackathon MVP just to run one post-submission job off the request thread, so
we lean on :class:`concurrent.futures.ThreadPoolExecutor`:

* The executor is created once per worker process in :func:`init_task_runner`
  and torn down via ``atexit`` on graceful shutdown.
* :func:`run_in_background` pushes a fresh Flask app context around the target
  callable, so SQLAlchemy sessions, ``current_app``, and config lookups work
  from the worker thread just like they do in a request.
* In tests (or any config with ``TASKS_SYNC=True``) callables run inline on the
  calling thread. That keeps pytest assertions deterministic without a
  ``time.sleep`` dance and without needing to flush the executor queue.

Trade-offs, documented rather than hidden:

* If the worker process crashes while a task is in flight, the task is lost —
  there is no durable queue. The ``AssessmentStatus.PENDING`` row stays pending
  until an assessor clicks "Retry AI" on the detail view.
* Gunicorn graceful-restart waits on the pool via ``atexit``; long-running
  tasks should cap their total runtime (Claude API call has its own timeout,
  so a single task won't hang the restart for long).
* Tasks share the web process's CPU. The AI call is almost entirely I/O-bound
  (a single HTTPS round-trip to Anthropic), so thread-based concurrency is a
  good fit. If we ever add CPU-heavy jobs, revisit.
"""

from __future__ import annotations

import atexit
import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from flask import Flask, has_app_context

log = logging.getLogger(__name__)

_EXECUTOR_EXT_KEY = "grants_task_executor"
_SYNC_EXT_KEY = "grants_task_sync"


def init_task_runner(app: Flask) -> None:
    """Attach a ThreadPoolExecutor (or sync shim) to the Flask app.

    Called once from :func:`app.create_app`. The executor is registered under
    ``app.extensions["grants_task_executor"]`` and shut down at process exit.
    """
    if app.config.get("TESTING") or app.config.get("TASKS_SYNC"):
        app.extensions[_SYNC_EXT_KEY] = True
        log.info("init_task_runner: running tasks synchronously (TASKS_SYNC)")
        return

    max_workers = int(app.config.get("TASK_WORKERS", 2))
    executor = ThreadPoolExecutor(
        max_workers=max_workers, thread_name_prefix="grants-bg"
    )
    app.extensions[_EXECUTOR_EXT_KEY] = executor
    atexit.register(_shutdown_executor, executor)
    log.info("init_task_runner: started thread pool with %s workers", max_workers)


def _shutdown_executor(executor: ThreadPoolExecutor) -> None:
    """Drain and close the executor on interpreter exit.

    ``wait=False`` lets gunicorn's graceful-restart return quickly; in-flight
    tasks finish on their own and their DB commits are unaffected.
    """
    try:
        executor.shutdown(wait=False, cancel_futures=False)
    except Exception:  # noqa: BLE001
        log.exception("shutdown of task executor raised")


def run_in_background(
    app: Flask,
    func: Callable[..., Any],
    *args: Any,
    **kwargs: Any,
) -> None:
    """Run ``func(*args, **kwargs)`` on the background pool (or inline in tests).

    The callable executes with a fresh ``app.app_context()`` pushed, so it can
    touch ``db.session``, ``current_app.config``, etc. Exceptions are caught
    and logged — background tasks must not propagate errors back to the web
    request that enqueued them, because the request has already returned.

    Pass *only picklable / thread-safe values* for ``args``/``kwargs``. In
    practice that means primitive IDs (``application_id: int``) rather than
    ORM instances, which would leak across session boundaries.
    """
    if app.extensions.get(_SYNC_EXT_KEY):
        # Reuse the caller's app context when one is active (the common case
        # in tests, where the ``app`` fixture already pushes a context). This
        # keeps caller and callable on the same SQLAlchemy session, so rows
        # committed by the worker are immediately visible to assertions via
        # the outer ``db.session`` without needing ``expire_all`` or
        # ``refresh``. In production (async path) the executor thread has no
        # context, so we fall through to ``app.app_context()``.
        #
        # Exceptions are swallowed (and logged) to preserve the "fire and
        # forget" contract — a failing background task must never surface as
        # a 500 on the request that enqueued it, even in sync/test mode.
        try:
            if has_app_context():
                func(*args, **kwargs)
            else:
                with app.app_context():
                    func(*args, **kwargs)
        except Exception:  # noqa: BLE001
            log.exception(
                "background task %s failed (sync mode)",
                getattr(func, "__name__", repr(func)),
            )
        return

    executor: ThreadPoolExecutor | None = app.extensions.get(_EXECUTOR_EXT_KEY)
    if executor is None:
        # Defensive: if someone forgot to call init_task_runner, fall back to
        # inline execution rather than silently dropping the job.
        log.warning(
            "run_in_background: no executor registered; running %s inline",
            getattr(func, "__name__", repr(func)),
        )
        with app.app_context():
            func(*args, **kwargs)
        return

    def _runner() -> None:
        with app.app_context():
            try:
                func(*args, **kwargs)
            except Exception:  # noqa: BLE001
                log.exception(
                    "background task %s failed",
                    getattr(func, "__name__", repr(func)),
                )

    executor.submit(_runner)
