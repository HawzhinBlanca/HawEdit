"""Owned DBOS2.29.0 startup, raw transaction fences and native lifetime exclusion.

This owns runtime machinery, not producer readiness, spending or publication authority.
HTTP generation must remain refused until the protected ID-only producer is adopted.
"""

from __future__ import annotations

import asyncio
import importlib
import inspect
import math
import os
import sqlite3
import sys
import threading
import time
from collections.abc import Callable
from importlib.metadata import version
from typing import Any

import sqlalchemy as sa
from dbos import DBOS, Queue
from dbos._core import TEMP_SEND_WF_NAME
from dbos._dbos_config import DBOSConfig, get_system_database_url
from dbos._serialization import DBOSPortableJSONSerializer
from dbos._sys_db import SystemDatabase
from dbos._utils import INTERNAL_QUEUE_NAME, GlobalParams
from sqlalchemy import event
from sqlalchemy.pool import NullPool
from sqlalchemy.sql.dml import Insert
from sqlalchemy.sql.elements import TextClause

from hawedit.studio_admission import JournalPolicy, _policy, inspect_studio_connection
from hawedit.studio_private import (
    PrivateDirectory,
    PrivateSqlitePath,
    StudioStorageError,
    _identity,
)
from hawedit.studio_queue import STUDIO_QUEUE_NAME
from hawedit.studio_submissions import SubmissionStore
from hawedit.wsl_setup import package_digest

__all__ = ["OwnedStudioRuntime", "StudioLease", "studio_runtime_policy"]

_LOCK = "studio-supervisor.lock"
_EXECUTOR = "hawedit-studio-local-v1"
_NAME = "hawedit-studio-v1"


def studio_runtime_policy(workflow_name: str, step_names: tuple[str, ...] = ()) -> JournalPolicy:
    """Host selection with current producer version; never browser-supplied authority."""
    policy = JournalPolicy(workflow_name, f"studio-{package_digest()}", _EXECUTOR, "", step_names)
    _policy(policy)
    return policy


class StudioLease:
    """One permanent empty private member; native locks survive until release/process exit."""

    def __init__(self, directory: PrivateDirectory) -> None:
        self._directory = directory
        self._descriptor = -1
        self._locked = False
        self._pid = os.getpid()
        self._mutex = threading.RLock()
        try:
            try:
                directory.check_file(_LOCK)
            except FileNotFoundError:
                try:
                    with directory.open_new_file(_LOCK):
                        pass
                except FileExistsError:
                    pass
            self._identity = directory.member_identity(_LOCK)
            self._descriptor = os.open(
                directory.path / _LOCK,
                os.O_RDWR | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0),
            )
            self._check()
            if sys.platform == "win32":
                import msvcrt

                msvcrt.locking(self._descriptor, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self._descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self._locked = True
            self.verify()
        except (OSError, ValueError, StudioStorageError) as exc:
            self.release()
            raise StudioStorageError(
                "Studio supervisor lease unavailable; existing work preserved"
            ) from exc

    def _check(self) -> None:
        if self._descriptor < 0 or os.getpid() != self._pid:
            raise StudioStorageError("Studio lease is closed or belongs to another process")
        self._directory.verify()
        info = os.fstat(self._descriptor)
        if (
            _identity(info) != self._identity
            or info.st_size != 0
            or self._directory.member_identity(_LOCK) != self._identity
        ):
            raise StudioStorageError("Studio supervisor lease binding changed; work preserved")

    def verify(self) -> None:
        with self._mutex:
            try:
                if not self._locked:
                    raise StudioStorageError("Studio supervisor lease is not held")
                self._check()
            except (OSError, ValueError) as exc:
                raise StudioStorageError("Studio supervisor lease storage unavailable") from exc

    def release(self) -> None:
        with self._mutex:
            if self._descriptor < 0:
                return
            descriptor = self._descriptor
            self._descriptor = -1
            try:
                if self._locked and self._pid == os.getpid():
                    os.lseek(descriptor, 0, os.SEEK_SET)
                    if sys.platform == "win32":
                        import msvcrt

                        msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
                    else:
                        import fcntl

                        fcntl.flock(descriptor, fcntl.LOCK_UN)
            finally:
                self._locked = False
                os.close(descriptor)


class _OwnedEngine:
    def __init__(
        self,
        storage: PrivateSqlitePath,
        submissions: SubmissionStore,
        policy: JournalPolicy,
        lease: StudioLease,
        *,
        owner_check: Callable[[], None] | None = None,
    ) -> None:
        self.storage = storage
        self.submissions = submissions
        self.policy = policy
        self.lease = lease
        self.owner_check = owner_check
        self._sealed = False
        self._closed = False
        self.draining = False
        self._connections: set[sqlite3.Connection] = set()
        self._mutex = threading.Lock()
        self.engine = sa.create_engine(
            sa.URL.create("sqlite+pysqlite", database=str(storage.path)),
            creator=self._creator,
            poolclass=NullPool,
        )
        self.url = self.engine.url.render_as_string(hide_password=True)
        event.listen(self.engine, "connect", self._connect)
        event.listen(self.engine, "close", self._close_connection)
        event.listen(self.engine, "begin", self._begin)
        event.listen(self.engine, "before_cursor_execute", self._before_statement)
        event.listen(self.engine, "commit", self._commit)
        event.listen(self.engine, "handle_error", self._handle_error)

    def _check(self) -> None:
        if self._closed:
            raise StudioStorageError("Owned studio engine is closed")
        self.lease.verify()
        self.storage.verify()
        if self.owner_check is not None:
            self.owner_check()

    def _creator(self) -> sqlite3.Connection:
        self._check()
        connection = sqlite3.connect(
            self.storage.path.as_uri() + "?mode=rw",
            uri=True,
            timeout=5.0,
            check_same_thread=False,
            isolation_level=None,
        )
        try:
            self._check()
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA trusted_schema=OFF")
            connection.execute("PRAGMA synchronous=FULL")
            connection.execute("PRAGMA busy_timeout=5000")
            self._check()
            return connection
        except BaseException:
            connection.close()
            raise

    def _connect(self, connection: sqlite3.Connection, record: Any) -> None:
        with self._mutex:
            self._connections.add(connection)

    def _close_connection(self, connection: sqlite3.Connection, record: Any) -> None:
        with self._mutex:
            self._connections.discard(connection)

    def _inspect(self, connection: sqlite3.Connection) -> None:
        self._check()
        deadline = time.perf_counter() + 5.0
        connection.set_progress_handler(lambda: int(time.perf_counter() >= deadline), 1000)
        try:
            inspect_studio_connection(connection, self.storage, self.submissions, self.policy)
        finally:
            connection.set_progress_handler(None, 0)
        self._check()

    @staticmethod
    def _native(connection: sa.Connection) -> sqlite3.Connection:
        native = connection.connection.driver_connection
        if not isinstance(native, sqlite3.Connection):
            raise StudioStorageError("Owned studio engine lost its native SQLite connection")
        return native

    def _begin(self, connection: sa.Connection) -> None:
        self._check()
        native = self._native(connection)
        try:
            native.execute("BEGIN IMMEDIATE")
        except sqlite3.Error as exc:
            raise StudioStorageError(
                "Owned studio transaction unavailable; work preserved"
            ) from exc
        if self._sealed:
            self._inspect(native)

    def _before_statement(
        self,
        connection: sa.Connection,
        cursor: Any,
        statement: str,
        parameters: Any,
        context: Any,
        executemany: bool,
    ) -> None:
        self._check()
        if self.draining:
            compiled = context.compiled
            command = compiled.statement if compiled is not None else None
            if (
                command is None
                or isinstance(command, TextClause)
                or context.isddl
                or (isinstance(command, Insert) and command.table.name == "workflow_status")
            ):
                raise StudioStorageError(
                    "Studio is draining; new dispatch or unstructured writes refused"
                )
        if self._sealed:
            self._inspect(self._native(connection))

    def _commit(self, connection: sa.Connection) -> None:
        self._check()
        if self._sealed:
            self._inspect(self._native(connection))

    @staticmethod
    def _handle_error(context: Any) -> Exception | None:
        if isinstance(context.original_exception, sqlite3.OperationalError):
            # DBOS retries even arbitrary exception strings containing its lock phrase.
            return StudioStorageError("Owned studio SQLite operation unavailable; work preserved")
        return None

    def bootstrap(self) -> None:
        with self.engine.begin() as connection:
            native = self._native(connection)
            empty = native.execute("SELECT 1 FROM sqlite_schema LIMIT 1").fetchone() is None
            if not empty:
                self._inspect(native)
                self._sealed = True
        database = SystemDatabase.create(
            self.url, {}, self.engine, None, DBOSPortableJSONSerializer(), self.policy.executor_id
        )
        try:
            if empty:
                database.run_migrations()
                with self.engine.begin() as connection:
                    self._inspect(self._native(connection))
                    self._sealed = True
            database.upsert_queue(
                name=STUDIO_QUEUE_NAME,
                concurrency=1,
                worker_concurrency=1,
                rate_limit_max=None,
                rate_limit_period_sec=None,
                priority_enabled=False,
                partition_queue=False,
                polling_interval_sec=1.0,
                update_existing=False,
            )
        finally:
            database.destroy()

    def verify(self) -> None:
        if not self._sealed:
            raise StudioStorageError("Owned studio schema has not been admitted")
        with self.engine.begin() as connection:
            self._inspect(self._native(connection))

    def has_connections(self) -> bool:
        with self._mutex:
            return bool(self._connections)

    def close(self) -> None:
        if self.has_connections():
            raise StudioStorageError("Owned studio connections remain live; lease retained")
        self._closed = True
        self.engine.dispose()


class OwnedStudioRuntime:
    """Explicit main-thread lifecycle; launch success does not authorize a producer."""

    def __init__(
        self, storage: PrivateSqlitePath, submissions: SubmissionStore, policy: JournalPolicy
    ) -> None:
        _policy(policy)
        if (
            policy != studio_runtime_policy(policy.workflow_name, policy.step_names)
            or storage.root != submissions.path.parent
            or storage.path == submissions.path
        ):
            raise StudioStorageError(
                "Owned studio requires current host policy and distinct colocated journals"
            )
        self.storage = storage
        self.submissions = submissions
        self.policy = policy
        self._state = "new"
        self._lease: StudioLease | None = None
        self._owned_engine: _OwnedEngine | None = None
        self._instance: Any = None
        self._registry: Any = None
        self._functions: dict[str, Any] = {}
        self._types: dict[str, str] = {}
        self._queues: dict[str, Any] = {}
        self._baseline_functions: dict[str, Any] = {}
        self._serializer = DBOSPortableJSONSerializer()
        self._owner_thread = threading.get_ident()

    @property
    def state(self) -> str:
        return self._state

    @staticmethod
    def _environment() -> None:
        if GlobalParams.dbos_cloud or any(
            key.startswith(("DBOS__", "OTEL_")) for key in os.environ
        ):
            raise StudioStorageError(
                "Owned studio refuses ambient cloud, runtime or telemetry overrides"
            )

    def _main_thread(self) -> None:
        if (
            threading.current_thread() is not threading.main_thread()
            or threading.get_ident() != self._owner_thread
        ):
            raise StudioStorageError("Owned studio startup/shutdown requires its main thread")
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return
        raise StudioStorageError("Owned studio cannot adopt a foreign main event loop")

    def _initial_registry(self) -> None:
        module = importlib.import_module("dbos._dbos")
        if module._dbos_global_instance is not None:
            raise StudioStorageError(
                "Owned studio refuses an existing DBOS instance without destroying it"
            )
        registry = module._dbos_global_registry
        expected = {self.policy.workflow_name: "workflow"} | {
            "<temp>." + name: "step" for name in self.policy.step_names
        }
        if (
            registry is None
            or registry.dbos is not None
            or registry.function_type_map != expected
            or set(registry.workflow_info_map) != set(expected)
            or registry.queue_info_map
            or registry.class_info_map
            or registry.instance_info_map
            or registry.pollers
            or registry.kafka_registrations
            or registry.poller_queue_names
            or any(inspect.iscoroutinefunction(fn) for fn in registry.workflow_info_map.values())
        ):
            raise StudioStorageError("Owned studio refuses foreign or asynchronous registry state")
        self._registry = registry
        self._functions = dict(registry.workflow_info_map)
        self._baseline_functions = dict(self._functions)
        self._types = dict(expected)

    def _verify_owner(self) -> None:
        self._environment()
        module = importlib.import_module("dbos._dbos")
        registry = self._registry
        if (
            registry is None
            or module._dbos_global_registry is not registry
            or module._dbos_global_instance is not self._instance
            or registry.dbos is not self._instance
            or registry.function_type_map != self._types
            or set(registry.workflow_info_map) != set(self._functions)
            or any(
                registry.workflow_info_map[name] is not fn for name, fn in self._functions.items()
            )
            or registry.class_info_map
            or registry.instance_info_map
            or registry.pollers
            or registry.kafka_registrations
            or registry.poller_queue_names
        ):
            raise StudioStorageError("Owned studio runtime registry identity changed")
        for name, queue in registry.queue_info_map.items():
            if name == INTERNAL_QUEUE_NAME and self._instance is not None:
                if (
                    type(queue) is not Queue
                    or queue.name != INTERNAL_QUEUE_NAME
                    or queue._concurrency is not None
                    or queue._worker_concurrency is not None
                    or queue._limiter is not None
                    or queue._priority_enabled
                    or queue._partition_queue
                    or queue._polling_interval_sec != 1.0
                    or queue.database_backed_queue
                    or queue._client_system_database is not None
                ):
                    raise StudioStorageError("Owned studio internal queue policy changed")
                # Pinned get_internal_queue recreates this idle in-memory object on every call.
                self._queues[name] = queue
            if name not in self._queues or queue is not self._queues[name]:
                raise StudioStorageError("Owned studio queue registry identity changed")
        if set(registry.queue_info_map) != set(self._queues):
            raise StudioStorageError("Owned studio queue registry membership changed")
        queue = self._queues.get(STUDIO_QUEUE_NAME)
        if queue is not None and (
            queue.name != STUDIO_QUEUE_NAME
            or queue._concurrency != 1
            or queue._worker_concurrency != 1
            or queue._limiter is not None
            or queue._priority_enabled
            or queue._partition_queue
            or queue._polling_interval_sec != 1.0
            or queue.database_backed_queue
            or queue._client_system_database is not None
        ):
            raise StudioStorageError("Owned studio serial queue policy changed")
        if self._instance is None:
            return
        instance = self._instance
        config = instance._config
        if (
            self._owned_engine is None
            or instance._registry is not registry
            or instance._serializer is not self._serializer
            or config["system_database_engine"] is not self._owned_engine.engine
            or get_system_database_url(config) != self._owned_engine.url
            or config["name"] != _NAME
            or config.get("database_url") is not None
            or config["runtimeConfig"]["run_admin_server"] is not False
            or config["runtimeConfig"]["max_executor_threads"] != 1
            or not config["telemetry"]["disable_otlp"]
            or config["telemetry"]["OTLPExporter"]["tracesEndpoint"]
            or config["telemetry"]["OTLPExporter"]["logsEndpoint"]
            or instance.conductor_key is not None
            or instance.conductor_url is not None
            or instance.enable_patching
            or instance.fastapi is not None
            or instance.flask is not None
            or instance._listening_queues != [STUDIO_QUEUE_NAME]
            or instance._admin_server_field is not None
            or instance.conductor_websocket is not None
            or instance._app_db_field is not None
            or instance._background_event_loop._main_loop is not None
            or GlobalParams.app_version != self.policy.application_version
            or GlobalParams.executor_id != self.policy.executor_id
        ):
            raise StudioStorageError("Owned studio actual runtime configuration changed")
        database = instance._sys_db_field
        if database is not None and (
            database.engine.pool is not self._owned_engine.engine.pool
            or database.created_engine
            or database.serializer is not self._serializer
        ):
            raise StudioStorageError("Owned studio actual database engine or serializer changed")

    def launch(self) -> None:
        self._main_thread()
        if self._state != "new":
            raise StudioStorageError("Owned studio launch requires a fresh supervisor")
        if version("dbos") != "2.29.0":
            raise StudioStorageError("Owned studio requires the reviewed DBOS2.29.0 runtime")
        self._environment()
        self._initial_registry()
        self._state = "starting"
        try:
            self._lease = StudioLease(PrivateDirectory(self.storage.root, create=False))
            self._owned_engine = _OwnedEngine(
                self.storage,
                self.submissions,
                self.policy,
                self._lease,
                owner_check=self._verify_owner,
            )
            self._owned_engine.bootstrap()
            queue = Queue(STUDIO_QUEUE_NAME, concurrency=1, worker_concurrency=1)
            self._queues[STUDIO_QUEUE_NAME] = queue
            config: DBOSConfig = {
                "name": _NAME,
                "system_database_url": self._owned_engine.url,
                "system_database_engine": self._owned_engine.engine,
                "application_database_url": None,
                "application_version": self.policy.application_version,
                "executor_id": self.policy.executor_id,
                "serializer": self._serializer,
                "run_admin_server": False,
                "enable_otlp": False,
                "use_listen_notify": False,
                "max_executor_threads": 1,
                "log_level": "ERROR",
            }
            created = DBOS(config=config)
            if (
                created._serializer is not self._serializer
                or created._registry is not self._registry
                or created._config["system_database_engine"] is not self._owned_engine.engine
                or created._launched
            ):
                raise StudioStorageError(
                    "Foreign DBOS appeared during construction; left untouched"
                )
            self._instance = created
            # The pinned constructor's legacy sender is a registry entry, never admitted work.
            expected = set(self._functions) | {TEMP_SEND_WF_NAME}
            if set(self._registry.workflow_info_map) != expected:
                raise StudioStorageError("DBOS constructor added unsupported registry state")
            self._functions[TEMP_SEND_WF_NAME] = self._registry.workflow_info_map[TEMP_SEND_WF_NAME]
            self._types[TEMP_SEND_WF_NAME] = "workflow"
            DBOS.listen_queues([STUDIO_QUEUE_NAME])
            self._verify_owner()
            DBOS.launch()
            self._verify_owner()
            self._owned_engine.verify()
            self._state = "active"
        except BaseException:
            self.close(timeout_seconds=5.0)
            self._state = "refused"
            raise

    def verify(self) -> None:
        if self._state != "active" or self._owned_engine is None:
            raise StudioStorageError("Owned studio runtime is not accepting work")
        self._verify_owner()
        self._owned_engine.verify()

    def close(self, *, timeout_seconds: float = 5.0) -> None:
        self._main_thread()
        if (
            type(timeout_seconds) not in (int, float)
            or not 0 < timeout_seconds <= 10
            or not math.isfinite(timeout_seconds)
        ):
            raise ValueError("Studio drain timeout must be finite, positive and at most10 seconds")
        if self._state == "closed":
            return
        self._state = "draining"
        if self._owned_engine is not None:
            self._owned_engine.draining = True
        deadline = time.monotonic() + timeout_seconds
        instance = self._instance
        if instance is not None:
            module = importlib.import_module("dbos._dbos")
            if module._dbos_global_instance is not instance:
                raise StudioStorageError("Foreign DBOS instance present; owned lease retained")
            for stop in instance.poller_stop_events + instance.background_thread_stop_events:
                stop.set()
            database = instance._sys_db_field
            if database is not None:
                database._run_background_processes = False
            executor = instance._executor_field
            if executor is not None:
                executor.shutdown(wait=False, cancel_futures=True)
            threads = list(instance._background_threads)
            if executor is not None:
                threads += list(executor._threads)
            for thread in threads:
                thread.join(timeout=max(0.0, deadline - time.monotonic()))
            if any(thread.is_alive() for thread in threads):
                raise StudioStorageError(
                    "Studio workers remain live; draining lease and engine retained"
                )
            event_loop = instance._background_event_loop
            event_loop.stop(timeout=max(0.0, deadline - time.monotonic()))
            if event_loop._thread is not None and event_loop._thread.is_alive():
                raise StudioStorageError(
                    "Studio event loop remains live; lease and engine retained"
                )
        if self._owned_engine is not None and self._owned_engine.has_connections():
            raise StudioStorageError("Studio database connections remain live; lease retained")
        if instance is not None:
            self._verify_owner()
            DBOS.destroy()
            registry = self._registry
            for name, function in self._functions.items():
                if (
                    name not in self._baseline_functions
                    and registry.workflow_info_map.get(name) is function
                ):
                    del registry.workflow_info_map[name]
                    registry.function_type_map.pop(name, None)
            for name, queue in self._queues.items():
                if registry.queue_info_map.get(name) is queue:
                    del registry.queue_info_map[name]
            if registry.dbos is instance:
                registry.dbos = None
            self._instance = None
        if self._owned_engine is not None:
            self._owned_engine.close()
        if self._lease is not None:
            self._lease.release()
        self._state = "closed"
