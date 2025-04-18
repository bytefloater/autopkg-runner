# AutoPkg Runner

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)  
![Version 2.0.0](https://img.shields.io/badge/version-2.0.0-green)

A modular, pipeline‑driven wrapper around [AutoPkg](https://github.com/autopkg/autopkg) that automates:

- Verification and (re‑)generation of trust information  
- Mounting and validating an SMB‑hosted Munki repository  
- Batch execution of AutoPkg recipes  
- Generation of a timestamped HTML report via Django templates  
- Garbage collection of old AutoPkg cache, temporary files, and reports  

## Table of Contents
- [Features](#features)  
- [Requirements](#requirements)  
- [Installation](#installation)  
- [Configuration](#configuration)  
- [Usage](#usage)  
- [Pipeline Stages](#pipeline-stages)  
- [Contributing](#contributing)  
- [License](#license)  

## Features

- **Environment Check**  
  Confirms AutoPkg binary and recipe list exist before running.  
- **Trust Verification**  
  Verifies each recipe’s trust info; auto‑updates recipes that fail.  
- **SMB‑Hosted Munki Support**  
  Mounts a remote SMB share, validates repository structure, and unmounts on completion.  
- **Batch Recipe Execution**  
  Runs all recipes in sequence with `--report-plist` output.  
- **HTML Reporting**  
  Uses Django’s templating engine to render a customizable HTML report saved into the repo.  
- **Garbage Collection**  
  Cleans AutoPkg’s cache, temporary Munki files, and prunes old HTML reports based on retention settings.  
- **Notifications on completion**  
  Will push notification using the configured providers.

## Requirements

- **macOS** with `mount_smbfs` and `umount` utilities  
- **AutoPkg** installed and on your `$PATH`
- **Python 3.8+**  
- **Python packages**:
  - `django==4.2.20`  
  - `logbook==1.8.1`

## Installation
```bash
git clone https://github.com/bytefloater/autopkg-runner.git
cd autopkg-runner
pip3 install --user -r requirements.txt
```

## Configuration
Example configuration: (`config.json`)
```json
{
    "autopkg": {
        "bin_path": "<< path_to_autopkg_binary >>",
        "cache_path": "<< path_to_autopkg_cache >>",
        "recipe_list": "<< path_to_recipe_list_file>>",
        "report_plist": "<< path_to_save_report_plist >>"
    },
    "repository": {
        "mount_path": "<< local_mount_point >>",
        "server_address": "<< ipv4_address >>",
        "public_url": "https://<< public domain >>",
        "server_share": "<< munki_repo_share_name >>",
        "username": "<< samba_username >>",
        "password": "<< samba_password >>",
        "check_dirs": [
            "catalogs",
            "client_resources",
            "icons",
            "manifests",
            "pkgs",
            "pkgsinfo",
            "reports"
        ],
        "report_dir": "reports"
    },
    "module_settings": {
        "core.garbage_collector": {
            "retention_period": "1w",
            "clear_autopkg_cache": true,
            "clear_temp_files": true,
            "clear_old_reports": true
        },
        "core.generate_report": {
            "template": "bootstrap_template.html"
        },
        "core.notify": {
            "providers": [
                "pushover"
            ],
            "notifiers.pushover": {
                "app_token": "<< pushover_app_token >>",
                "user_token": "<< pushover_user_token >>",
                "supports_html": true
            }
        }
    },
    "log_level": "debug",
    "flags": []
}
```
> <b>`autopkg`</b>  
> Paths to the AutoPkg binary, its cache directory, your recipe list, and the output plist.
>
> <b>`repository`</b>  
> SMB mount point, server address/share, credentials, required subdirectories, and report output folder.
>
> <b>` module_settings`</b>  
> `core.garbage_collector`: retention string (7d, 12h, 1w) and toggles.  
> `core.generate_report`: name of the HTML template in /report_templates.  
> `core.notify`: configuration of notification providers and provider-specific settings  
>
> <b>`log_level`</b>  
> One of DEBUG, INFO, WARNING, ERROR.
>
> <b>`flags`</b>  
> Reserved for future feature flags.

## Usage
```bash
python3 main.py
```

## Pipeline Stages
- Environment Check
- Trust Verification
- Mount Remote Repository
- Run AutoPkg
- Generate HTML Report
- Garbage Collector
- Notify (using providers) on completion

Each stage implements:
- `pre_check() → bool`
- `run()`
- `post_check() → bool`
- `cleanup()` (on failure)

## Contributing
- Fork the repository
- Create a feature branch (`git checkout -b feature/YourFeature`)
- Implement your changes, adhering to PEP8 and adding tests where appropriate
- Submit a pull request with a clear description

## License
This project is licensed under the Apache License 2.0 – see the [LICENSE](/LICENSE) file for details.