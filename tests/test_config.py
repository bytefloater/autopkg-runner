"""Tests for libs.config: config_from_settings, pipeline_config_to_dict."""
from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.mark.django_db
class TestConfigFromSettings:
    def test_returns_pipeline_config(self):
        from libs.config import config_from_settings, PipelineConfig
        config = config_from_settings()
        assert isinstance(config, PipelineConfig)

    def test_autopkg_bin_path_is_path(self):
        from libs.config import config_from_settings
        config = config_from_settings()
        assert isinstance(config.autopkg.bin_path, Path)

    def test_gc_keep_versions_is_int(self):
        from libs.config import config_from_settings
        config = config_from_settings()
        assert isinstance(config.garbage_collector.keep_versions, int)

    def test_reads_custom_setting(self):
        from webapp.models import Setting
        from libs.config import config_from_settings
        Setting.set('gc.keep_versions', '7')
        config = config_from_settings()
        assert config.garbage_collector.keep_versions == 7


@pytest.mark.django_db
class TestPipelineConfigToDict:
    def test_output_contains_no_path_objects(self):
        from libs.config import config_from_settings, pipeline_config_to_dict
        config = config_from_settings()
        result = pipeline_config_to_dict(config)
        # Recursively check for Path objects
        def has_path(obj):
            if isinstance(obj, Path):
                return True
            if isinstance(obj, dict):
                return any(has_path(v) for v in obj.values())
            if isinstance(obj, (list, tuple)):
                return any(has_path(v) for v in obj)
            return False
        assert not has_path(result), "pipeline_config_to_dict output should not contain Path objects"

    def test_output_is_json_serialisable(self):
        from libs.config import config_from_settings, pipeline_config_to_dict
        config = config_from_settings()
        result = pipeline_config_to_dict(config)
        # Should not raise
        json.dumps(result)
