"""N-worker concurrency for the Runner: multiple runs execute in parallel.

No real OpenFOAM is involved — Runner._execute is monkeypatched with a fake
that sleeps and polls the shared _cancel set on a timer (mirroring the _foam
poll loop), then marks the run done. Every assertion here is about the worker /
queue machinery only: parallel execution, per-run state isolation, cancel,
delete and restart-recovery semantics. Default SLIPSTREAM_WORKERS=2.
"""
from __future__ import annotations

import json
import threading
import time

import pytest

from app.runner import Runner, _Cancelled


def make_state(run_id, tmp_path, status="queued"):
    """A minimal run directory (state.json + dir) as the API would create it."""
    rd = tmp_path / run_id
    rd.mkdir(parents=True, exist_ok=True)
    state = {
        "id": run_id,
        "name": run_id,
        "status": status,
        "created_at": time.time(),
        "progress": 0.0,
        "message": "",
        "config": {"unit": "mm", "wind_speed": 10.0},
    }
    (rd / "state.json").write_text(json.dumps(state, indent=1))
    return state


class PeakCounter:
    """Tracks the maximum number of runs active at the same time."""

    def __init__(self):
        self.active = 0
        self.peak = 0
        self.lock = threading.Lock()

    def __enter__(self):
        with self.lock:
            self.active += 1
            self.peak = max(self.peak, self.active)

    def __exit__(self, *exc):
        with self.lock:
            self.active -= 1


def install_fake_execute(monkeypatch, counter, duration=0.15):
    """Replace Runner._execute with a controllable fake.

    The fake behaves like the real pipeline under cancellation: it polls the
    shared _cancel set on a timer and raises _Cancelled, which _loop converts
    into status="cancelled". Each run's terminal update is tagged with its own
    run_id so tests can verify per-run state isolation.
    """

    def fake_execute(self, run_id):
        deadline = time.monotonic() + duration
        while time.monotonic() < deadline:
            time.sleep(0.01)
            with self.lock:
                if run_id in self._cancel:
                    raise _Cancelled()
        self.update(run_id, status="done", progress=1.0,
                    message=f"finished {run_id}")

    def wrapper(self, run_id):
        with counter:
            fake_execute(self, run_id)

    monkeypatch.setattr(Runner, "_execute", wrapper)


def wait_for(runner, run_id, status, timeout=10.0):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        last = runner.get(run_id)
        if last and last["status"] == status:
            return last
        time.sleep(0.01)
    raise AssertionError(f"run {run_id} never reached {status!r}; "
                         f"last state={last!r}")


def wait_terminal(runner, run_id, timeout=10.0):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        last = runner.get(run_id)
        if last and last["status"] in ("done", "error", "cancelled"):
            return last
        time.sleep(0.01)
    raise AssertionError(f"run {run_id} never finished; last state={last!r}")


def wait_for_active(runner, run_id, timeout=10.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if runner.is_active(run_id):
            return
        time.sleep(0.01)
    raise AssertionError(f"run {run_id} never started; state={runner.get(run_id)}")


def wait_inactive(runner, run_id, timeout=10.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not runner.is_active(run_id):
            return
        time.sleep(0.005)
    raise AssertionError(f"run {run_id} still active; state={runner.get(run_id)}")


# ---------------------------------------------------------------------------
# Parallel execution
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("workers,n_runs", [(2, 4), (3, 6)])
def test_runs_execute_in_parallel(monkeypatch, tmp_path, workers, n_runs):
    """N workers really overlap: wall clock beats the serial sum and the
    concurrency peek shows all workers busy at once."""
    monkeypatch.setenv("SLIPSTREAM_WORKERS", str(workers))
    counter = PeakCounter()
    install_fake_execute(monkeypatch, counter, duration=0.15)
    runner = Runner(tmp_path)

    t0 = time.monotonic()
    for i in range(n_runs):
        runner.submit(make_state(f"r{i:02d}", tmp_path))
    for i in range(n_runs):
        wait_for(runner, f"r{i:02d}", "done")
    wall = time.monotonic() - t0

    serial = n_runs * 0.15  # what one-at-a-time would take
    assert wall < serial * 0.9, (
        f"{n_runs} runs on {workers} workers took {wall:.3f}s "
        f"vs {serial:.3f}s serial — not really parallel")
    assert counter.peak == workers, (
        f"expected {workers} concurrent runs, saw peak {counter.peak}")


@pytest.mark.parametrize("workers", [2, 3])
def test_is_active_true_for_concurrent_runs(monkeypatch, tmp_path, workers):
    monkeypatch.setenv("SLIPSTREAM_WORKERS", str(workers))
    counter = PeakCounter()
    install_fake_execute(monkeypatch, counter, duration=0.4)
    runner = Runner(tmp_path)
    runner.submit(make_state("a", tmp_path))
    runner.submit(make_state("b", tmp_path))

    # Both runs are mid-flight at the same time.
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        if runner.is_active("a") and runner.is_active("b"):
            break
        time.sleep(0.01)
    else:
        pytest.fail("both runs never reported active at the same time")
    assert runner.is_active("a") and runner.is_active("b")

    wait_for(runner, "a", "done")
    wait_for(runner, "b", "done")
    wait_inactive(runner, "a")
    wait_inactive(runner, "b")
    assert not runner.is_active("a") and not runner.is_active("b")


# ---------------------------------------------------------------------------
# Cancel
# ---------------------------------------------------------------------------


def test_cancel_queued_run_is_immediate(monkeypatch, tmp_path):
    """A run still waiting in the queue is marked cancelled at once and never
    executes (with a single worker, a second run is guaranteed to stay queued
    behind a busy one)."""
    monkeypatch.setenv("SLIPSTREAM_WORKERS", "1")
    counter = PeakCounter()
    install_fake_execute(monkeypatch, counter, duration=0.5)
    runner = Runner(tmp_path)
    runner.submit(make_state("busy", tmp_path))
    wait_for_active(runner, "busy")
    runner.submit(make_state("q", tmp_path))
    assert runner.get("q")["status"] == "queued"

    assert runner.cancel("q") is True
    assert runner.get("q")["status"] == "cancelled"

    # Once the worker drains it, it is still cancelled — never ran to done.
    state = wait_terminal(runner, "q")
    assert state["status"] == "cancelled"
    wait_for(runner, "busy", "done")


def test_cancel_running_run(monkeypatch, tmp_path):
    """A running run honours the cancel request through the same poll loop the
    real _foam uses (raising _Cancelled), and lands in 'cancelled'."""
    counter = PeakCounter()
    install_fake_execute(monkeypatch, counter, duration=2.0)
    runner = Runner(tmp_path)
    runner.submit(make_state("slow", tmp_path))
    wait_for_active(runner, "slow")

    assert runner.cancel("slow") is True
    state = wait_for(runner, "slow", "cancelled")
    assert state["status"] == "cancelled"
    wait_inactive(runner, "slow")
    # Already terminal: cancel is a no-op.
    assert runner.cancel("slow") is False


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


def test_delete_executing_run_returns_false(monkeypatch, tmp_path):
    counter = PeakCounter()
    install_fake_execute(monkeypatch, counter, duration=1.0)
    runner = Runner(tmp_path)
    runner.submit(make_state("a", tmp_path))
    wait_for_active(runner, "a")

    assert runner.delete("a") is False      # executing -> refused
    assert runner.get("a") is not None

    wait_for(runner, "a", "done")
    wait_inactive(runner, "a")
    assert runner.delete("a") is True       # no longer executing
    assert runner.get("a") is None


def test_delete_finished_run_returns_true(monkeypatch, tmp_path):
    counter = PeakCounter()
    install_fake_execute(monkeypatch, counter, duration=0.1)
    runner = Runner(tmp_path)
    runner.submit(make_state("a", tmp_path))
    wait_for(runner, "a", "done")
    wait_inactive(runner, "a")
    assert runner.delete("a") is True


# ---------------------------------------------------------------------------
# Restart recovery
# ---------------------------------------------------------------------------


def test_restart_requeues_queued_and_errors_non_terminal(monkeypatch, tmp_path):
    """On a fresh Runner, queued runs are re-queued and re-executed, non-
    terminal runs are marked error ("interrupted by server restart"), and
    terminal runs are left untouched."""
    make_state("q1", tmp_path, status="queued")
    make_state("mid", tmp_path, status="solving")
    make_state("d1", tmp_path, status="done")
    counter = PeakCounter()
    install_fake_execute(monkeypatch, counter, duration=0.1)

    runner = Runner(tmp_path)

    # Non-terminal -> error at load time.
    assert runner.get("mid")["status"] == "error"
    assert runner.get("mid")["error"] == "interrupted by server restart"
    # Terminal -> untouched.
    assert runner.get("d1")["status"] == "done"
    # Queued -> re-queued, picked up and re-executed by a worker.
    wait_for(runner, "q1", "done")


# ---------------------------------------------------------------------------
# Per-run state isolation
# ---------------------------------------------------------------------------


def test_concurrent_runs_do_not_cross_contaminate(monkeypatch, tmp_path):
    """Two runs executing at once update only their own state, in memory and
    in their own state.json on disk."""
    counter = PeakCounter()
    install_fake_execute(monkeypatch, counter, duration=0.3)
    runner = Runner(tmp_path)
    runner.submit(make_state("x", tmp_path))
    runner.submit(make_state("y", tmp_path))

    sx = wait_for(runner, "x", "done")
    sy = wait_for(runner, "y", "done")
    assert sx["status"] == sy["status"] == "done"
    assert sx["progress"] == sy["progress"] == 1.0
    assert sx["message"] == "finished x"
    assert sy["message"] == "finished y"
    assert sx["id"] == "x" and sy["id"] == "y"

    # Each persisted state.json holds only its own run's fields.
    fy = json.loads((tmp_path / "y" / "state.json").read_text())
    fx = json.loads((tmp_path / "x" / "state.json").read_text())
    assert fx["message"] == "finished x" and fy["message"] == "finished y"
    assert fx["id"] == "x" and fy["id"] == "y"


# ---------------------------------------------------------------------------
# Worker count
# ---------------------------------------------------------------------------


def test_workers_default_and_clamp(monkeypatch, tmp_path):
    monkeypatch.delenv("SLIPSTREAM_WORKERS", raising=False)
    assert Runner(tmp_path).workers == 2           # default
    monkeypatch.setenv("SLIPSTREAM_WORKERS", "0")
    assert Runner(tmp_path).workers == 1           # clamped up
    monkeypatch.setenv("SLIPSTREAM_WORKERS", "-2")
    assert Runner(tmp_path).workers == 1           # clamped up
    monkeypatch.setenv("SLIPSTREAM_WORKERS", "9")
    assert Runner(tmp_path).workers == 4           # clamped down
    monkeypatch.setenv("SLIPSTREAM_WORKERS", "3")
    assert Runner(tmp_path).workers == 3           # as-is
