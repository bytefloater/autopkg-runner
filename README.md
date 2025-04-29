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
  Confirms AutoPkg binary and recipe list exist and there are no mounting conflicts before running.  
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
- **AutoPkg** installed on your system
- **Python 3.8+**  
- **Python packages**:
  - `django==4.2.20`
  - `dnspython==2.7.0`
  - `logbook==1.8.1`
  - `psutil==7.0.0`
  - `zeroconf==0.146.5`

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
        "bin_path": "/usr/local/bin/autopkg",
        "cache_path": "~/Library/AutoPkg/Cache",
        "recipe_list": "~/Library/Application Support/AutoPkgr/recipe_list.txt",
        "report_plist": "~/Documents/autopkg_report.plist"
    },
    "repository": {
        "server": {
            "host": "<< ipv4_or_zeroconf_name>>",
            "share": "<< munki_repo_share_name >>",
            "mount_path": "/tmp/Munki",
            "public_url": "https://<< public_domain >>"
        },
        "authentication":{
            "username": "<< username >>",
            "password": "<< password >>"
        },
        "directories": {
            "check": [
                "catalogs",
                "client_resources",
                "icons",
                "manifests",
                "pkgs",
                "pkgsinfo",
                "reports"
            ],
            "report_dir": "reports"
        }
    },
    "module_settings": {
        "core.garbage_collector": {
            "repoclean_bin_path": "/usr/local/munki/repoclean",
            "retention": {
                "period": "1w",
                "keep_versions": 3
            },
            "targets": {
                "autopkg_cache": true,
                "temp_files": true,
                "old_reports": true,
                "repository_index": true
            }
        },
        "core.generate_report": {
            "template": "bootstrap_template.html"
        },
        "core.notify": {
            "providers": [
                "pushover"
            ],
            "notifiers.pushover": {
                "app_token": "",
                "user_token": "",
                "supports_html": true
            },
            "notifiers.discord": {
                "webhook_id": "",
                "webhook_token": ""
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
> <b>`module_settings`</b>  
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
### Running the application:
```bash
python3 main.py
```
| Option           | Description                                                            |
|------------------|------------------------------------------------------------------------|
| `-c`, `--config` | Specify the path to your configuration file (defaults to: config.json) |
| `-s`, `--stage`  | Specify a single stage to run for testing                              |

### Running a module (like a notifier):
```bash
python3 -m notifiers.pushover
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