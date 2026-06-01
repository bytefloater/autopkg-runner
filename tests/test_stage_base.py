"""Tests for libs.stage.Stage.__call__ lifecycle."""
from __future__ import annotations

from unittest.mock import MagicMock, call

import pytest


def _make_stage(pre_check_val=True, post_check_val=True, run_result=None, run_raises=None):
    """Return a concrete Stage instance with controllable method outcomes."""
    from libs.stage import Stage

    class ConcreteStage(Stage):
        name = 'Test Stage'
        calls = []

        def pre_check(self):
            ConcreteStage.calls.append('pre_check')
            return pre_check_val

        def run(self):
            ConcreteStage.calls.append('run')
            if run_raises:
                raise run_raises
            return run_result

        def post_check(self):
            ConcreteStage.calls.append('post_check')
            return post_check_val

    ConcreteStage.calls = []
    config = MagicMock()
    ctx = {'stage_outputs': {}}
    logger = MagicMock()
    return ConcreteStage(config, ctx, logger), ConcreteStage


class TestStageCallLifecycle:
    def test_calls_pre_check_then_run_then_post_check(self):
        stage, cls = _make_stage()
        stage()
        assert cls.calls == ['pre_check', 'run', 'post_check']

    def test_pre_check_false_raises_runtime_error(self):
        stage, cls = _make_stage(pre_check_val=False)
        with pytest.raises(RuntimeError):
            stage()
        # run should NOT have been called
        assert 'run' not in cls.calls

    def test_post_check_false_raises_runtime_error(self):
        stage, cls = _make_stage(post_check_val=False)
        with pytest.raises(RuntimeError):
            stage()
        # run WAS called
        assert 'run' in cls.calls

    def test_run_result_stored_in_ctx(self):
        stage, cls = _make_stage(run_result='my-output')
        stage()
        assert stage.ctx['stage_outputs'][cls] == 'my-output'

    def test_run_none_result_stored_in_ctx(self):
        stage, cls = _make_stage(run_result=None)
        stage()
        assert cls in stage.ctx['stage_outputs']
