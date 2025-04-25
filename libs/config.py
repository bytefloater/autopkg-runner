from pathlib import Path
from dataclasses import dataclass
import json

@dataclass(frozen=True)
class AutopkgConfig:
    bin_path: Path
    cache_path: Path
    recipe_list: Path
    report_plist: Path

@dataclass(frozen=True)
class RepositoryConfig:
    mount_path: Path
    host: str
    public_url: str
    server_share: str
    username: str
    password: str
    check_dirs: list[str]
    report_dir: str

@dataclass(frozen=True)
class ModuleSettings:
    garbage_collector: dict[str, any]
    generate_report: dict[str, any]
    notify: dict[str, any]

@dataclass(frozen=True)
class PipelineConfig:
    autopkg: AutopkgConfig
    repository: RepositoryConfig
    module_settings: ModuleSettings
    log_level: str
    flags: list[str]

def load_config(path: str) -> PipelineConfig:
    with open(Path(path).expanduser(), mode="r", encoding="utf-8") as config_file:
        raw = json.load(config_file)

    return PipelineConfig(
        autopkg=AutopkgConfig(
            bin_path=Path(raw["autopkg"]["bin_path"]).expanduser(),
            cache_path=Path(raw["autopkg"]["cache_path"]).expanduser(),
            recipe_list=Path(raw["autopkg"]["recipe_list"]).expanduser(),
            report_plist=Path(raw["autopkg"]["report_plist"]).expanduser(),
        ),
        repository=RepositoryConfig(
            host=raw["repository"]["server"]["host"],
            server_share=raw["repository"]["server"]["share"],
            mount_path=Path(raw["repository"]["server"]["mount_path"]).expanduser(),
            public_url=raw["repository"]["server"]["public_url"],
            
            username=raw["repository"]["authentication"]["username"],
            password=raw["repository"]["authentication"]["password"],
            
            check_dirs=raw["repository"]["directories"]["check"],
            report_dir=raw["repository"]["directories"]["report_dir"]
        ),
        module_settings=ModuleSettings(
            garbage_collector=raw["module_settings"]["core.garbage_collector"],
            generate_report=raw["module_settings"]["core.generate_report"],
            notify=raw["module_settings"]["core.notify"],
        ),
        log_level=raw["log_level"],
        flags=raw["flags"],
    )
