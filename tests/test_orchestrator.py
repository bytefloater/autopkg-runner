"""Tests for libs.orchestrator: configure_stages, execute, cleanup ordering."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, call, patch

import pytest


# ---------------------------------------------------------------------------
# FakeStage helpers
# ---------------------------------------------------------------------------

def _make_fake_stage_class(name: str, should_raise: bool = False, cleanup_fn=None):
    """Return a Stage-compatible class for testing the orchestrator.

    Uses ``type()`` so that the ``run`` method is defined at class-creation
    time, which satisfies ABCMeta's abstract-method check.  Assigning
    ``_Fake.run = ...`` *after* class creation does NOT update the
    ``__abstractmethods__`` frozenset, causing ``TypeError`` on instantiation.
    """
    from libs.stage import Stage

    def run(self):
        if should_raise:
            raise RuntimeError(f'{name} failed')

    attrs: dict = {'name': name, 'run': run}
    if cleanup_fn:
        attrs['cleanup'] = cleanup_fn

    return type(name, (Stage,), attrs)


# ---------------------------------------------------------------------------
# configure_stages
# ---------------------------------------------------------------------------

class TestConfigureStages:
    def _make_orchestrator(self, stage_classes=None):
        from libs.orchestrator import Orchestrator
        logger = MagicMock()
        config = MagicMock()
        orch = Orchestrator(config=config, logger=logger)
        if stage_classes:
            orch.STAGE_CLASSES = stage_classes
        return orch

    def test_configure_none_creates_all_stages(self):
        # Replace STAGE_CLASSES with lightweight fakes so no real stage
        # __init__ is called (some stages validate the config in __init__).
        FakeA = _make_fake_stage_class('FakeA')
        FakeB = _make_fake_stage_class('FakeB')
        FakeC = _make_fake_stage_class('FakeC')
        orch = self._make_orchestrator(stage_classes=[FakeA, FakeB, FakeC])
        orch.configure_stages(override_stage_name=None)
        assert len(orch.stages) == 3

    def test_configure_with_name_creates_single_stage(self):
        from stages import GarbageCollector
        orch = self._make_orchestrator()
        orch.configure_stages(override_stage_name='GarbageCollector')
        assert len(orch.stages) == 1
        assert isinstance(orch.stages[0], GarbageCollector)

    def test_configure_unknown_name_creates_all_stages(self):
        FakeA = _make_fake_stage_class('FakeA')
        FakeB = _make_fake_stage_class('FakeB')
        orch = self._make_orchestrator(stage_classes=[FakeA, FakeB])
        orch.configure_stages(override_stage_name='NonExistentStage')
        assert len(orch.stages) == 2


# ---------------------------------------------------------------------------
# execute
# ---------------------------------------------------------------------------

class TestExecute:
    def _make_orch_with_fakes(self, *stage_specs):
        """
        stage_specs: list of (name, should_raise) tuples.
        Returns (orchestrator, cleanup_trackers).
        """
        from libs.orchestrator import Orchestrator
        from stages.notify import NotifyOnCompletion

        logger = MagicMock()
        config = MagicMock()
        cleanup_order = []

        classes = []
        for name, should_raise in stage_specs:
            def make_cleanup(n):
                def cleanup(self):
                    cleanup_order.append(n)
                return cleanup

            cls = _make_fake_stage_class(name, should_raise, cleanup_fn=make_cleanup(name))
            classes.append(cls)

        # Always add a fake NotifyOnCompletion so the orchestrator can split it
        class FakeNotify(NotifyOnCompletion):
            def __init__(self, config, ctx, logger):
                # Skip super().__init__ which reads DB
                self.logger = logger
                self.ctx = ctx

            def run(self):
                pass

            def cleanup(self):
                pass

        classes.append(FakeNotify)

        orch = Orchestrator(config=config, logger=logger)
        orch.STAGE_CLASSES = classes
        orch.configure_stages(None)
        return orch, cleanup_order

    def test_returns_true_on_success(self):
        orch, _ = self._make_orch_with_fakes(('A', False), ('B', False))
        result = orch.execute()
        assert result is True

    def test_returns_false_when_stage_raises(self):
        orch, _ = self._make_orch_with_fakes(('A', False), ('B', True))
        result = orch.execute()
        assert result is False

    def test_cleanup_called_in_reverse_order(self):
        orch, cleanup_order = self._make_orch_with_fakes(
            ('A', False), ('B', False), ('C', True)
        )
        orch.execute()
        # A and B completed before C raised; cleanup should be B then A
        assert cleanup_order == ['B', 'A']

    def test_stage_callback_called_with_running_and_success(self):
        callback = MagicMock()
        orch, _ = self._make_orch_with_fakes(('MyStage', False))
        orch.stage_callback = callback
        orch.execute()
        calls = [c[0] for c in callback.call_args_list]
        names_statuses = [(c[0], c[1]) for c in calls]
        assert ('MyStage', 'running') in names_statuses
        assert ('MyStage', 'success') in names_statuses

    def test_stage_callback_called_with_failed_on_exception(self):
        callback = MagicMock()
        orch, _ = self._make_orch_with_fakes(('FailStage', True))
        orch.stage_callback = callback
        orch.execute()
        calls = [c[0] for c in callback.call_args_list]
        names_statuses = [(c[0], c[1]) for c in calls]
        assert ('FailStage', 'failed') in names_statuses

    def test_callback_exception_does_not_propagate(self):
        def bad_callback(*args):
            raise RuntimeError('callback exploded')

        orch, _ = self._make_orch_with_fakes(('A', False))
        orch.stage_callback = bad_callback
        # Should not raise despite bad callback
        result = orch.execute()
        assert result is True
