"""Tests for stages/notify.py - helper functions and NotifyOnCompletion stage."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

import pytest


# ── _SafeDict ─────────────────────────────────────────────────────────────────

class TestSafeDict:
    def test_missing_key_returns_placeholder(self):
        from stages.notify import _SafeDict
        d = _SafeDict({'name': 'Alice'})
        assert d['name'] == 'Alice'
        assert d['missing'] == '{missing}'

    def test_known_key_works_normally(self):
        from stages.notify import _SafeDict
        d = _SafeDict({'status': 'ok'})
        assert d['status'] == 'ok'


# ── _render ───────────────────────────────────────────────────────────────────

class TestRender:
    def _call(self, template, ctx):
        from stages.notify import _render
        return _render(template, ctx)

    def test_simple_substitution(self):
        assert self._call('Hello {name}', {'name': 'World'}) == 'Hello World'

    def test_missing_key_leaves_placeholder(self):
        assert self._call('Status: {status}', {}) == 'Status: {status}'

    def test_empty_template(self):
        assert self._call('', {}) == ''

    def test_malformed_format_string_returns_as_is(self):
        # A positional placeholder without a valid key - shouldn't crash
        result = self._call('{0} value', {})
        assert isinstance(result, str)

    def test_multiple_substitutions(self):
        result = self._call('{status_emoji} {status}', {
            'status': 'succeeded',
            'status_emoji': '✅',
        })
        assert result == '✅ succeeded'

    # ── {share_link:"text"} HTML shorthand ────────────────────────────────────

    def test_share_link_double_quotes_with_url(self):
        result = self._call(
            '{share_link:"View Report"}',
            {'share_url': 'https://example.com/share/abc/'},
        )
        assert result == '<a href="https://example.com/share/abc/">View Report</a>'

    def test_share_link_single_quotes_with_url(self):
        result = self._call(
            "{share_link:'View Report'}",
            {'share_url': 'https://example.com/share/abc/'},
        )
        assert result == '<a href="https://example.com/share/abc/">View Report</a>'

    def test_share_link_without_url_collapses_to_empty(self):
        result = self._call('{share_link:"View Report"}', {'share_url': ''})
        assert result == ''

    def test_share_link_missing_share_url_key_collapses_to_empty(self):
        # share_url not in ctx at all - should still collapse cleanly
        result = self._call('{share_link:"Report"}', {})
        assert result == ''

    def test_share_link_mixed_with_other_variables(self):
        result = self._call(
            '{status_emoji} Run {share_link:"Details"}',
            {
                'status_emoji': '✅',
                'share_url': 'https://example.com/share/xyz/',
            },
        )
        assert result == '✅ Run <a href="https://example.com/share/xyz/">Details</a>'

    def test_share_link_collapses_cleanly_in_sentence(self):
        # When no URL, surrounding text is preserved but the placeholder is gone
        result = self._call(
            'Run complete. {share_link:"Open report"}',
            {'share_url': ''},
        )
        assert result == 'Run complete. '

    def test_share_url_raw_still_works(self):
        # Backward compatibility: bare {share_url} still renders the raw URL
        result = self._call(
            'Link: {share_url}',
            {'share_url': 'https://example.com/share/abc/'},
        )
        assert result == 'Link: https://example.com/share/abc/'

    def test_share_link_custom_text_preserved_exactly(self):
        result = self._call(
            '{share_link:"AutoPkg Run Report - June 2025"}',
            {'share_url': 'https://push.example.com/share/tok/'},
        )
        assert 'AutoPkg Run Report - June 2025' in result
        assert 'href="https://push.example.com/share/tok/"' in result


# ── NotifyOnCompletion helper methods ─────────────────────────────────────────

def _make_stage(notifiers=None, ctx=None):
    """Build a NotifyOnCompletion instance with mocked dependencies."""
    from stages.notify import NotifyOnCompletion
    config = MagicMock()
    config.notifiers = notifiers or []
    ctx = ctx or {}
    logger = MagicMock()
    return NotifyOnCompletion(config=config, ctx=ctx, logger=logger)


class TestGenPlainMsg:
    def test_basic_message_no_stats(self):
        stage = _make_stage()
        msg = stage._gen_plain_msg({'imports': 0, 'downloads': 0, 'failures': 0})
        assert 'AutoPkg run complete' in msg

    def test_includes_import_count(self):
        stage = _make_stage()
        msg = stage._gen_plain_msg({'imports': 3, 'downloads': 0, 'failures': 0})
        assert '3' in msg
        assert 'imported' in msg

    def test_includes_download_count(self):
        stage = _make_stage()
        msg = stage._gen_plain_msg({'imports': 0, 'downloads': 5, 'failures': 0})
        assert '5' in msg
        assert 'download' in msg

    def test_includes_failure_count(self):
        stage = _make_stage()
        msg = stage._gen_plain_msg({'imports': 0, 'downloads': 0, 'failures': 2})
        assert '2' in msg
        assert 'failure' in msg

    def test_includes_all_stats(self):
        stage = _make_stage()
        msg = stage._gen_plain_msg({'imports': 1, 'downloads': 2, 'failures': 3})
        assert '1' in msg and '2' in msg and '3' in msg


class TestGenHtmlMsg:
    def test_basic_html_message(self):
        stage = _make_stage()
        msg = stage._gen_html_msg({'imports': 0, 'downloads': 0, 'failures': 0})
        assert '<b>' in msg
        assert 'AutoPkg run complete' in msg

    def test_html_includes_import_count(self):
        stage = _make_stage()
        msg = stage._gen_html_msg({'imports': 4, 'downloads': 0, 'failures': 0})
        assert '4' in msg and 'imported' in msg

    def test_html_no_stats_omits_bullet_line(self):
        stage = _make_stage()
        msg = stage._gen_html_msg({'imports': 0, 'downloads': 0, 'failures': 0})
        assert '·' not in msg

    def test_html_multiple_stats_joined(self):
        stage = _make_stage()
        msg = stage._gen_html_msg({'imports': 1, 'downloads': 2, 'failures': 1})
        assert '·' in msg


# ── _build_summary ────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestBuildSummary:
    def test_returns_zeroed_dict_when_run_id_is_none(self):
        stage = _make_stage()
        summary = stage._build_summary(None)
        assert summary['imports'] == 0
        assert summary['failures'] == 0
        assert summary['downloads'] == 0
        assert summary['share_url'] is None

    def test_counts_recipe_results(self, run):
        from webapp.models import RecipeResult
        RecipeResult.objects.create(run=run, result_type='munki_import', data={})
        RecipeResult.objects.create(run=run, result_type='failure', data={})
        RecipeResult.objects.create(run=run, result_type='url_downloaded', data={})
        stage = _make_stage()
        summary = stage._build_summary(run.id)
        assert summary['imports'] == 1
        assert summary['failures'] == 1
        assert summary['downloads'] == 1

    def test_builds_share_url_when_pwa_base_configured(self, run):
        from webapp.models import Setting
        Setting.set('notify.pwa_base_url', 'https://push.example.com')
        stage = _make_stage()
        summary = stage._build_summary(run.id)
        assert summary['share_url'] is not None
        assert 'https://push.example.com' in summary['share_url']

    def test_no_share_url_without_pwa_base(self, run):
        from webapp.models import Setting
        Setting.set('notify.pwa_base_url', '')
        stage = _make_stage()
        summary = stage._build_summary(run.id)
        assert not summary['share_url']


# ── _build_template_context ───────────────────────────────────────────────────

@pytest.mark.django_db
class TestBuildTemplateContext:
    def test_no_run_id_returns_defaults(self):
        stage = _make_stage()
        ctx = stage._build_template_context({'imports': 0, 'failures': 0, 'downloads': 0, 'share_url': None}, None)
        assert ctx['status'] == 'succeeded'
        assert ctx['run_id'] == ''

    def test_with_run_id_includes_duration(self, run):
        stage = _make_stage()
        ctx = stage._build_template_context({'imports': 0, 'failures': 0, 'downloads': 0, 'share_url': None}, run.id)
        assert 'duration' in ctx
        assert 'date' in ctx
        assert 'time' in ctx

    def test_failed_stage_sets_failed_status(self, run):
        from webapp.models import StageExecution
        from datetime import datetime, timezone
        StageExecution.objects.create(
            run=run, name='RunAutopkg', status='failed', order=0,
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
        )
        stage = _make_stage()
        ctx = stage._build_template_context({'imports': 0, 'failures': 1, 'downloads': 0, 'share_url': None}, run.id)
        assert ctx['status'] == 'failed'
        assert ctx['status_emoji'] == '❌'


# ── NotifyOnCompletion.run() ──────────────────────────────────────────────────

@pytest.mark.django_db
class TestNotifyRun:
    def test_skips_when_no_notifiers(self, run):
        stage = _make_stage(notifiers=[], ctx={'run_id': run.id})
        stage.run()  # must not raise; logger.info called
        stage.logger.info.assert_called()

    def test_dispatches_to_notifier_module(self, run):
        mock_notifier = MagicMock()
        mock_notifier.notifier_type = 'pushover'
        mock_notifier.name = 'My Pushover'
        mock_notifier.title_template = ''
        mock_notifier.message_template = ''
        mock_notifier.config = {}
        mock_notifier.pk = str(uuid.uuid4())

        mock_module = MagicMock()
        mock_send = MagicMock()
        mock_module.send = mock_send

        stage = _make_stage(notifiers=[mock_notifier], ctx={'run_id': run.id})
        with patch('importlib.import_module', return_value=mock_module):
            stage.run()

        mock_send.assert_called_once()

    def test_skips_when_module_not_found(self, run):
        mock_notifier = MagicMock()
        mock_notifier.notifier_type = 'nonexistent'
        mock_notifier.name = 'Bad'
        mock_notifier.title_template = ''
        mock_notifier.message_template = ''
        mock_notifier.config = {}
        mock_notifier.pk = str(uuid.uuid4())

        stage = _make_stage(notifiers=[mock_notifier], ctx={'run_id': run.id})
        with patch('importlib.import_module', side_effect=ModuleNotFoundError('nope')):
            stage.run()  # must not raise

        stage.logger.error.assert_called()

    def test_skips_when_send_function_missing(self, run):
        mock_notifier = MagicMock()
        mock_notifier.notifier_type = 'pushover'
        mock_notifier.name = 'No send'
        mock_notifier.title_template = ''
        mock_notifier.message_template = ''
        mock_notifier.config = {}
        mock_notifier.pk = str(uuid.uuid4())

        mock_module = MagicMock(spec=[])  # no 'send' attribute

        stage = _make_stage(notifiers=[mock_notifier], ctx={'run_id': run.id})
        with patch('importlib.import_module', return_value=mock_module):
            stage.run()  # must not raise

    def test_logs_error_when_send_raises(self, run):
        mock_notifier = MagicMock()
        mock_notifier.notifier_type = 'pushover'
        mock_notifier.name = 'Failing'
        mock_notifier.title_template = ''
        mock_notifier.message_template = ''
        mock_notifier.config = {}
        mock_notifier.pk = str(uuid.uuid4())

        mock_module = MagicMock()
        mock_module.send.side_effect = Exception('network error')

        stage = _make_stage(notifiers=[mock_notifier], ctx={'run_id': run.id})
        with patch('importlib.import_module', return_value=mock_module):
            stage.run()  # must not raise

        stage.logger.error.assert_called()

    def test_uses_custom_title_template(self, run):
        mock_notifier = MagicMock()
        mock_notifier.notifier_type = 'pushover'
        mock_notifier.name = 'Custom'
        mock_notifier.title_template = 'Run {status}'
        mock_notifier.message_template = ''
        mock_notifier.config = {}
        mock_notifier.pk = str(uuid.uuid4())

        mock_module = MagicMock()
        stage = _make_stage(notifiers=[mock_notifier], ctx={'run_id': run.id})
        with patch('importlib.import_module', return_value=mock_module):
            stage.run()

        call_kwargs = mock_module.send.call_args[1]
        assert 'succeeded' in call_kwargs['title'] or 'failed' in call_kwargs['title']

    def test_uses_html_message_when_supports_html(self, run):
        mock_notifier = MagicMock(spec=['notifier_type', 'name', 'title_template',
                                        'message_template', 'config', 'pk'])
        mock_notifier.notifier_type = 'pushover'
        mock_notifier.name = 'HTML Notifier'
        mock_notifier.title_template = ''
        mock_notifier.message_template = ''
        mock_notifier.config = {'supports_html': True}
        mock_notifier.pk = str(uuid.uuid4())

        mock_module = MagicMock()
        stage = _make_stage(notifiers=[mock_notifier], ctx={'run_id': run.id})
        with patch('importlib.import_module', return_value=mock_module):
            stage.run()

        call_kwargs = mock_module.send.call_args[1]
        assert '<b>' in call_kwargs['message']

    def test_custom_message_template_rendered(self, run):
        mock_notifier = MagicMock()
        mock_notifier.notifier_type = 'pushover'
        mock_notifier.name = 'Templated'
        mock_notifier.title_template = ''
        mock_notifier.message_template = 'Run {run_id} done'
        mock_notifier.config = {}
        mock_notifier.pk = str(uuid.uuid4())

        mock_module = MagicMock()
        stage = _make_stage(notifiers=[mock_notifier], ctx={'run_id': run.id})
        with patch('importlib.import_module', return_value=mock_module):
            stage.run()

        call_kwargs = mock_module.send.call_args[1]
        assert str(run.id) in call_kwargs['message']
