"""Tests for libs.intercept_logger.InterceptLogger."""
from __future__ import annotations

import threading


class TestInterceptLogger:
    def _make(self):
        from libs.intercept_logger import InterceptLogger
        return InterceptLogger()

    def test_info_adds_entry_with_info_level(self):
        il = self._make()
        il.info('hello')
        entries = il.entries()
        assert len(entries) == 1
        assert entries[0]['level'] == 'INFO'
        assert entries[0]['msg'] == 'hello'

    def test_error_adds_entry_with_error_level(self):
        il = self._make()
        il.error('oops')
        entries = il.entries()
        assert entries[0]['level'] == 'ERROR'
        assert entries[0]['msg'] == 'oops'

    def test_multiline_message_split_into_separate_entries(self):
        il = self._make()
        il.info('line1\nline2\nline3')
        entries = il.entries()
        assert len(entries) == 3
        msgs = [e['msg'] for e in entries]
        assert 'line1' in msgs
        assert 'line2' in msgs
        assert 'line3' in msgs

    def test_entries_returns_copy(self):
        il = self._make()
        il.info('first')
        entries = il.entries()
        entries.append({'fake': 'true'})  # type annotation expects Dict[str, str]
        # Internal list should be unaffected
        assert len(il.entries()) == 1

    def test_thread_safety_concurrent_writes(self):
        il = self._make()
        errors = []

        def writer(n):
            try:
                for i in range(50):
                    il.info(f'thread-{n}-msg-{i}')
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        assert len(il.entries()) == 4 * 50

    def test_as_string_includes_level_and_message(self):
        il = self._make()
        il.info('test message')
        s = il.as_string()
        assert 'INFO' in s
        assert 'test message' in s
