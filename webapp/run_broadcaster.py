"""In-process SSE fan-out broadcaster.

One RunBroadcaster is created per active run. A single daemon thread polls
the database and appends serialised SSE event frames to an in-memory list.
Async SSE generators in run_stream read from that list using a cursor
(the list index of the last event they have seen), so the database is
queried exactly once per second per run regardless of how many clients
are watching.

The manager expires finished broadcasters after a TTL so late-connecting
clients can still receive the full event history for a recently completed run.
"""
from __future__ import annotations

import json
import logging
import threading
import time

from django.db import close_old_connections

logger = logging.getLogger('autopkg_runner')

_DONE_TTL = 300   # seconds to keep a finished broadcaster alive


class RunBroadcaster:
    """Polls the database for one run and caches events for all subscribers."""

    def __init__(self, run_id: str):
        self.run_id = run_id
        self._events: list[bytes] = []   # pre-rendered SSE frames without id: line
        self._lock = threading.Lock()
        self._done = False
        self._done_at: float | None = None
        self._thread = threading.Thread(
            target=self._poll_loop,
            daemon=True,
            name=f'run-broadcaster-{run_id}',
        )
        self._thread.start()

    # ------------------------------------------------------------------
    # Public API (called from async SSE generators)
    # ------------------------------------------------------------------

    def events_since(self, cursor: int) -> tuple[list[bytes], bool]:
        """Return (new_frames, is_done).

        cursor is the index of the last event the caller has consumed.
        Pass -1 to receive all events from the beginning.
        Frames are returned with their SSE ``id:`` line prepended.
        """
        with self._lock:
            raw = self._events[cursor + 1:]
            start = cursor + 1
            frames = [
                f'id: {start + i}\n'.encode() + frame
                for i, frame in enumerate(raw)
            ]
            return frames, self._done

    @property
    def is_expired(self) -> bool:
        if not self._done or self._done_at is None:
            return False
        return (time.monotonic() - self._done_at) > _DONE_TTL

    # ------------------------------------------------------------------
    # Internal poll loop (runs in daemon thread)
    # ------------------------------------------------------------------

    def _poll_loop(self):
        try:
            self._run()
        except Exception:
            logger.exception('RunBroadcaster error for run %s', self.run_id)
        finally:
            close_old_connections()
            with self._lock:
                self._done = True
                self._done_at = time.monotonic()

    def _run(self):
        from webapp.models import LogEntry, Run, StageExecution

        last_log_id = 0
        last_stage_data: dict[str, str] = {}

        while True:
            close_old_connections()

            run = Run.objects.filter(id=self.run_id).first()
            if not run:
                break

            new_frames: list[bytes] = []

            entries = LogEntry.objects.filter(
                run_id=self.run_id, id__gt=last_log_id
            ).order_by('id')
            for entry in entries:
                payload = json.dumps({
                    'type': 'log',
                    'id': entry.id,
                    'level': entry.level,
                    'stage': entry.stage_name,
                    'message': entry.message,
                    'timestamp': entry.timestamp.isoformat(),
                })
                new_frames.append(f'data: {payload}\n\n'.encode())
                last_log_id = entry.id

            for stage in StageExecution.objects.filter(run_id=self.run_id):
                key = f'{stage.name}:{stage.status}'
                if last_stage_data.get(stage.name) != key:
                    last_stage_data[stage.name] = key
                    payload = json.dumps({
                        'type': 'stage',
                        'name': stage.name,
                        'status': stage.status,
                        'order': stage.order,
                        'started_at': stage.started_at.isoformat() if stage.started_at else None,
                        'completed_at': stage.completed_at.isoformat() if stage.completed_at else None,
                    })
                    new_frames.append(f'data: {payload}\n\n'.encode())

            if new_frames:
                with self._lock:
                    self._events.extend(new_frames)

            if run.status in ('success', 'failed', 'cancelled'):
                # Wait briefly then do one final pass to collect any log entries
                # or stage updates that were written to the DB slightly after the
                # run status was set (common on fast-failing runs).
                time.sleep(0.3)
                close_old_connections()
                for entry in LogEntry.objects.filter(
                    run_id=self.run_id, id__gt=last_log_id
                ).order_by('id'):
                    payload = json.dumps({
                        'type': 'log',
                        'level': entry.level,
                        'stage': entry.stage_name,
                        'message': entry.message,
                        'timestamp': entry.timestamp.isoformat(),
                    })
                    new_frames.append(f'data: {payload}\n\n'.encode())
                    last_log_id = entry.id

                for stage in StageExecution.objects.filter(run_id=self.run_id):
                    key = f'{stage.name}:{stage.status}'
                    if last_stage_data.get(stage.name) != key:
                        last_stage_data[stage.name] = key
                        payload = json.dumps({
                            'type': 'stage',
                            'name': stage.name,
                            'status': stage.status,
                            'order': stage.order,
                            'started_at': stage.started_at.isoformat() if stage.started_at else None,
                            'completed_at': stage.completed_at.isoformat() if stage.completed_at else None,
                        })
                        new_frames.append(f'data: {payload}\n\n'.encode())

                payload = json.dumps({'type': 'complete', 'status': run.status})
                terminal_frames = [
                    f'data: {payload}\n\n'.encode(),
                    b'event: done\ndata: {}\n\n',
                ]
                with self._lock:
                    self._events.extend(new_frames)
                    self._events.extend(terminal_frames)
                run_list_broadcaster.notify()
                break

            time.sleep(1)


# ---------------------------------------------------------------------------
# Manager singleton
# ---------------------------------------------------------------------------

class _BroadcasterManager:
    def __init__(self):
        self._broadcasters: dict[str, RunBroadcaster] = {}
        self._lock = threading.Lock()

    def get(self, run_id: str) -> RunBroadcaster:
        """Return an existing broadcaster or create one for *run_id*."""
        run_id = str(run_id)
        with self._lock:
            self._expire()
            if run_id not in self._broadcasters:
                self._broadcasters[run_id] = RunBroadcaster(run_id)
            return self._broadcasters[run_id]

    def _expire(self):
        """Remove broadcasters whose TTL has elapsed (called under lock)."""
        stale = [rid for rid, b in self._broadcasters.items() if b.is_expired]
        for rid in stale:
            del self._broadcasters[rid]


broadcaster_manager = _BroadcasterManager()


# ---------------------------------------------------------------------------
# Global run-list broadcaster
# ---------------------------------------------------------------------------
# Signals the list page whenever any run reaches a terminal state.
# Subscribers long-poll via run_list_stream; on receiving an event they
# trigger an HTMX refresh of the run list.

class RunListBroadcaster:
    """Simple monotonic-counter broadcaster for run-list change notifications."""

    def __init__(self):
        self._seq = 0
        self._lock = threading.Lock()
        self._event = threading.Event()

    def notify(self) -> None:
        """Called when any run changes to a terminal state."""
        with self._lock:
            self._seq += 1
        self._event.set()

    def wait_for_change(self, last_seq: int, timeout: float = 30.0) -> int:
        """Block until seq > last_seq (or timeout). Returns current seq."""
        deadline = time.monotonic() + timeout
        while True:
            with self._lock:
                if self._seq > last_seq:
                    return self._seq
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                with self._lock:
                    return self._seq
            self._event.wait(timeout=min(remaining, 1.0))
            self._event.clear()


run_list_broadcaster = RunListBroadcaster()
