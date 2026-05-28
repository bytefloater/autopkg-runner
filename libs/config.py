from pathlib import Path
from dataclasses import dataclass
import json


@dataclass(frozen=True)
class AutopkgConfig:
    bin_path: Path
    cache_path: Path
    recipe_list: Path


@dataclass(frozen=True)
class RepositoryConfig:
    repo_type: str          # 'local' | 'remote'
    connection_type: str    # 'smb' | 'sftp'  (remote only)
    local_path: Path        # local type only
    mount_path: Path        # remote/smb
    host: str
    public_url: str
    server_share: str
    username: str
    password: str


@dataclass(frozen=True)
class GarbageCollectorConfig:
    keep_versions: int
    clear_temp: bool
    clean_repo: bool
    repoclean_bin_path: str


@dataclass(frozen=True)
class LogSettings:
    level: str
    logtofile_enable: bool
    logtofile_path: Path


@dataclass(frozen=True)
class PipelineConfig:
    autopkg: AutopkgConfig
    repository: RepositoryConfig
    garbage_collector: GarbageCollectorConfig
    log_settings: LogSettings
    update_repos: bool
    notifiers: list        # list of webapp.models.Notifier instances (or dicts)
    flags: list[str]


def config_from_settings() -> 'PipelineConfig':
    """Build a PipelineConfig by reading from the Setting key-value store."""
    from webapp.models import Setting, Notifier

    s = Setting.get

    return PipelineConfig(
        autopkg=AutopkgConfig(
            bin_path=Path(s('autopkg.bin_path')).expanduser(),
            cache_path=Path(s('autopkg.cache_path')).expanduser(),
            recipe_list=Path(s('autopkg.recipe_list')).expanduser(),
        ),
        repository=RepositoryConfig(
            repo_type=s('repository.type', 'remote'),
            connection_type=s('repository.connection_type', 'smb'),
            local_path=Path(s('repository.local_path', '~')).expanduser(),
            host=s('repository.host'),
            server_share=s('repository.share'),
            mount_path=Path(s('repository.mount_path', '/tmp/Munki')).expanduser(),
            public_url=s('repository.public_url'),
            username=s('repository.username'),
            password=s('repository.password'),
        ),
        garbage_collector=GarbageCollectorConfig(
            keep_versions=Setting.get_int('gc.keep_versions', 3),
            clear_temp=Setting.get_bool('gc.clear_temp'),
            clean_repo=Setting.get_bool('gc.clean_repo'),
            repoclean_bin_path=s('gc.repoclean_bin_path'),
        ),
        log_settings=LogSettings(
            level=s('logging.level', 'INFO'),
            logtofile_enable=Setting.get_bool('logging.to_file'),
            logtofile_path=Path(s('logging.file_path', '~/logs/autopkg-runner')).expanduser(),
        ),
        update_repos=Setting.get_bool('workflow.update_repos'),
        notifiers=list(Notifier.objects.filter(enabled=True)),
        flags=[],
    )


def pipeline_config_to_dict(config: 'PipelineConfig') -> dict:
    """Serialise a PipelineConfig to a JSON-safe dict (Paths become strings)."""
    return {
        'autopkg': {
            'bin_path':    str(config.autopkg.bin_path),
            'cache_path':  str(config.autopkg.cache_path),
            'recipe_list': str(config.autopkg.recipe_list),
        },
        'repository': {
            'type':            config.repository.repo_type,
            'connection_type': config.repository.connection_type,
            'local_path':      str(config.repository.local_path),
            'host':            config.repository.host,
            'server_share':    config.repository.server_share,
            'mount_path':      str(config.repository.mount_path),
            'public_url':      config.repository.public_url,
            'username':        config.repository.username,
        },
        'garbage_collector': {
            'keep_versions':     config.garbage_collector.keep_versions,
            'clear_temp':        config.garbage_collector.clear_temp,
            'clean_repo':        config.garbage_collector.clean_repo,
            'repoclean_bin_path':config.garbage_collector.repoclean_bin_path,
        },
        'log_settings': {
            'level':            config.log_settings.level,
            'logtofile_enable': config.log_settings.logtofile_enable,
            'logtofile_path':   str(config.log_settings.logtofile_path),
        },
        'update_repos': config.update_repos,
        'flags': config.flags,
    }



def load_config(path: str) -> 'PipelineConfig':
    """Load config from the legacy JSON file format (CLI usage)."""
    with open(Path(path).expanduser(), mode='r', encoding='utf-8') as f:
        raw = json.load(f)

    return PipelineConfig(
        autopkg=AutopkgConfig(
            bin_path=Path(raw['autopkg']['bin_path']).expanduser(),
            cache_path=Path(raw['autopkg']['cache_path']).expanduser(),
            recipe_list=Path(raw['autopkg']['recipe_list']).expanduser(),
        ),
        repository=RepositoryConfig(
            repo_type='remote',
            connection_type='smb',
            local_path=Path('~').expanduser(),
            host=raw['repository']['server']['host'],
            server_share=raw['repository']['server']['share'],
            mount_path=Path(raw['repository']['server']['mount_path']).expanduser(),
            public_url=raw['repository']['server']['public_url'],
            username=raw['repository']['authentication']['username'],
            password=raw['repository']['authentication']['password'],
        ),
        garbage_collector=GarbageCollectorConfig(
            keep_versions=raw.get('module_settings', {}).get(
                'core.garbage_collector', {}).get('retention', {}).get('keep_versions', 3),
            clear_temp=True,
            clean_repo=True,
            repoclean_bin_path=raw.get('module_settings', {}).get(
                'core.garbage_collector', {}).get('repoclean_bin_path', ''),
        ),
        log_settings=LogSettings(
            level=raw['log_settings']['level'],
            logtofile_enable=raw['log_settings']['logtofile_enable'],
            logtofile_path=Path(raw['log_settings']['logtofile_path']).expanduser(),
        ),
        update_repos=raw.get('module_settings', {}).get(
            'core.update_repos', {}).get('update_before_each_run', True),
        notifiers=[],
        flags=raw.get('flags', []),
    )
