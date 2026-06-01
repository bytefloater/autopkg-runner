"""Tests for libs.run_command.run_cmd."""
from __future__ import annotations

import subprocess
from io import StringIO
from unittest.mock import MagicMock, patch, call

import pytest


def _make_popen_mock(stdout_lines=None, stderr_lines=None, returncode=0):
    """Build a Popen mock that feeds lines through select.select."""
    mock_proc = MagicMock()
    mock_proc.returncode = returncode
    mock_proc.poll.return_value = returncode

    stdout_lines = stdout_lines or []
    stderr_lines = stderr_lines or []

    # Build readline sequences: lines + '' (EOF)
    stdout_reads = [l + '\n' for l in stdout_lines] + ['']
    stderr_reads = [l + '\n' for l in stderr_lines] + ['']

    mock_proc.stdout = MagicMock()
    mock_proc.stdout.readline.side_effect = stdout_reads
    mock_proc.stdout.fileno.return_value = 3

    mock_proc.stderr = MagicMock()
    mock_proc.stderr.readline.side_effect = stderr_reads
    mock_proc.stderr.fileno.return_value = 4

    mock_proc.wait.return_value = returncode
    mock_proc.__enter__ = MagicMock(return_value=mock_proc)
    mock_proc.__exit__ = MagicMock(return_value=False)

    return mock_proc


class TestRunCmd:
    def _run(self, popen_mock, logger=None):
        from libs.run_command import run_cmd
        logger = logger or MagicMock()

        # select.select alternates between stdout and stderr, then returns nothing
        # We simulate: first call returns stdout ready, next returns stderr, then both EOF
        select_results = [
            ([popen_mock.stdout], [], []),
        ] * len(popen_mock.stdout.readline.side_effect) + [
            ([popen_mock.stderr], [], []),
        ] * len(popen_mock.stderr.readline.side_effect) + [
            ([], [], []),
        ]

        with patch('subprocess.Popen', return_value=popen_mock), \
             patch('select.select', side_effect=select_results):
            run_cmd(['echo', 'hello'], logger)

    def test_stdout_lines_logged_as_info(self):
        logger = MagicMock()
        mock_proc = _make_popen_mock(stdout_lines=['hello', 'world'], returncode=0)
        select_results = (
            [([mock_proc.stdout], [], [])] * 3 +  # 2 lines + EOF
            [([mock_proc.stderr], [], [])] * 1 +  # EOF
            [([], [], [])]
        )
        with patch('subprocess.Popen', return_value=mock_proc), \
             patch('select.select', side_effect=select_results):
            from libs.run_command import run_cmd
            run_cmd(['echo', 'hello'], logger)
        info_calls = [str(c) for c in logger.info.call_args_list]
        assert any('hello' in c for c in info_calls)

    def test_stderr_lines_logged_as_error(self):
        logger = MagicMock()
        mock_proc = _make_popen_mock(stderr_lines=['uh oh'], returncode=0)
        select_results = (
            [([mock_proc.stdout], [], [])] * 1 +  # EOF
            [([mock_proc.stderr], [], [])] * 2 +  # 1 line + EOF
            [([], [], [])]
        )
        with patch('subprocess.Popen', return_value=mock_proc), \
             patch('select.select', side_effect=select_results):
            from libs.run_command import run_cmd
            run_cmd(['cmd'], logger)
        error_calls = [str(c) for c in logger.error.call_args_list]
        assert any('uh oh' in c for c in error_calls)

    def test_nonzero_exit_raises_called_process_error(self):
        logger = MagicMock()
        mock_proc = _make_popen_mock(returncode=1)
        mock_proc.wait.return_value = 1
        select_results = [
            ([mock_proc.stdout], [], []),
            ([mock_proc.stderr], [], []),
            ([], [], []),
        ]
        with patch('subprocess.Popen', return_value=mock_proc), \
             patch('select.select', side_effect=select_results):
            from libs.run_command import run_cmd
            with pytest.raises(subprocess.CalledProcessError):
                run_cmd(['fail'], logger)
