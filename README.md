# AutoPkg Runner

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg?style=for-the-badge)](LICENSE)<br>
![Version 3.0.0](https://img.shields.io/badge/version-3.0.0-green?style=for-the-badge)

A web-based management interface for [AutoPkg](https://github.com/autopkg/autopkg) - the macOS software packaging automation tool. AutoPkg Runner wraps your AutoPkg workflows in a Django web application with real-time run monitoring, a REST API, a mobile PWA, and scheduled execution.

## Features

### Web UI

- **Dashboard** - last run summary, 30-day success rate, next scheduled run, and a one-click manual trigger
- **Run detail** - GitHub Actions-style stage timeline with live log streaming; stage status icons and the log panel update in real time without a page refresh
- **Run history** - paginated list of all pipeline executions with status badges and duration
- **Run cancellation** - cancel an in-progress run from the run detail page
- **Run sharing** - generate a shareable, unauthenticated link to any completed run report; optional expiry window configurable in notification settings
- **Schedule** - cron-based scheduling with an enable/disable toggle; changes apply immediately without a server restart
- **Recipes** - full AutoPkg recipe management (see [Recipes](#recipes) below)
- **Configuration** - full pipeline configuration through the browser
- **Users** - create and manage user accounts, reset passwords
- **API tokens** - create and revoke per-user tokens for REST API access

### Recipes

The Recipes section replaces AutoPkgr for day-to-day recipe management. It is organised into three sub-tabs:

#### Repositories

- Lists all AutoPkg recipe repositories with their remote URL and git status (up to date / N commits behind / unknown)
- Add a repository by URL — runs `autopkg repo-add` in the background
- Remove a repository — runs `autopkg repo-delete`
- Update a repository inline — the row shows a spinner while `autopkg repo-update` runs, then refreshes with the new status

#### Recipe List

- Browses all recipes found across all configured repository search directories
- Supports both `.recipe` (XML/plist) and `.recipe.yaml` (YAML) recipe formats
- Displays parent recipes and their overrides as separate, clearly labelled rows
- Toggle any recipe or override into or out of the active run list with a single click — changes write directly to the recipe list file on disk
- Inline search and filtering across all available recipes
- **Missing parent detection** — highlights recipes whose declared parent recipe is not installed on the system, with a warning icon on the row and a summary banner at the top of the page
- **Orphan run-list detection** — identifies entries in the run list file that no longer match any known recipe or override, listed separately so stale entries can be cleaned up
- Identifier-based deduplication ensures recipes from different repos with the same filename are both shown

#### Override Editor

- Lists all recipe overrides in `~/Library/AutoPkg/RecipeOverrides/` with their active status
- Create a new override from any recipe with one click — runs `autopkg make-override` and redirects straight to the editor
- Full-featured CodeMirror XML editor with line numbers and syntax highlighting; switches to a dark theme automatically when the app is in dark mode
- Save validates XML before writing; parse errors are shown inline without overwriting the file

### Mobile PWA

- Installable progressive web app with an iOS-native look and feel
- Bottom tab bar navigation with SPA-style page transitions
- Real-time stage status updates and live log streaming on run detail
- Install directly from Safari - no App Store required

<img src="docs/images/sc_mobile_dashboard.png" alt="Mobile dashboard" width="300">

### Notifications

Seven notification providers are supported. Multiple notifiers can be configured and each can have its own custom title and message template.

| Provider | Notes |
|-|-|
| **Pushover** | Push notification to iPhone/iPad/Mac via the Pushover app |
| **Discord** | Message to a Discord channel via an incoming webhook |
| **WebPush** | Native browser push notification - works with the installed PWA or any subscribed browser session |
| **Email (SMTP)** | Email via any SMTP server; supports STARTTLS and SSL, optional authentication |
| **Slack** | Message to a Slack channel via an incoming webhook |
| **Microsoft Teams** | Message to a Teams channel via an incoming webhook |
| **Google Chat** | Message to a Google Chat space via an incoming webhook |

Notifications are always dispatched at the end of a run regardless of whether earlier pipeline stages succeeded or failed.

Notification message and title fields support template variables:

| Variable | Description |
|-|-|
| `{{ status }}` | Run outcome (`success` / `failure`) |
| `{{ status_emoji }}` | Emoji representing the outcome |
| `{{ imports }}` | Number of items imported |
| `{{ failures }}` | Number of recipe failures |
| `{{ downloads }}` | Number of items downloaded |
| `{{ duration }}` | Run duration |
| `{{ share_url }}` | Link to the shareable run report |
| `{{ run_id }}` | Run UUID |
| `{{ triggered_by }}` | Who or what triggered the run |
| `{{ date }}` / `{{ time }}` | Run date and time |

### REST API

All endpoints support both JSON (`Accept: application/json`) and XML (`Accept: application/xml`) responses. Token authentication is required for all endpoints except `get_token`.

| Method | Endpoint | Description |
|--|-|-|
| `POST` | `/api/auth/get_token/` | Exchange username + password for an API token |
| `GET` | `/api/auth/check_token/` | Validate a token |
| `POST` | `/api/tasks/trigger_run/` | Start a pipeline run - returns a task UUID |
| `POST` | `/api/tasks/trigger_db_cleanup/` | Start a DB cleanup task - returns a task UUID |
| `GET` | `/api/tasks/get_task_status/?uuid=` | Poll the status of a task |
| `GET` | `/api/history/get_run_data/?uuid=` | Full run detail including stages, logs, and recipe results |
| `GET` | `/api/history/list_runs/` | List runs; optional `start_date` / `end_date` query filters |

### Pipeline

The pipeline runs these stages in order:

1. **Environment Check** - validates the AutoPkg binary and recipe list exist and are readable
2. **Update Repos** - runs `autopkg repo-update all` to pull the latest recipe repos (optional, can be disabled per run or toggled in Workflow settings)
3. **Trust Verification** - runs `autopkg verify-trust-info` on all recipes and updates trust as needed
4. **Mount Repository** - connects to the Munki repository over SMB or SFTP
5. **Run AutoPkg** - batch executes all configured recipes and writes a report plist
6. **Generate Report** - renders a timestamped HTML report from a Django template
7. **Garbage Collector** - prunes old cache files, temp files, and stale HTML reports using `repoclean`
8. **Send Notifications** - dispatches alerts to all configured notifiers



## Requirements

- macOS (AutoPkg is macOS-only)
- Python 3.9+
- [AutoPkg](https://github.com/autopkg/autopkg) installed



## Installation

```bash
git clone https://github.com/yourorg/autopkg-runner.git
cd autopkg-runner
pip3 install -r requirements.txt
python3 manage.py setup
python3 manage.py serve
```

`manage.py setup` runs all database migrations, creates the default schedule row, and generates an admin account with a random password printed to the terminal.

Open `http://127.0.0.1:8000` and log in with the credentials shown. All configuration is done through the web UI.



## Management commands

| Command | Description |
||-|
| `manage.py setup` | One-shot initialisation: migrate, create defaults, generate admin account |
| `manage.py serve` | Start the development server (`--network` to bind to all interfaces, `--port` to change port) |
| `manage.py resetpassword` | Generate and set a new random password for the admin account |
| `manage.py generate_vapid_keys` | Generate VAPID keys for WebPush notifications and store them in the database |
| `manage.py install_sftp_deps` | Install macFUSE and sshfs via Homebrew (required for SFTP repository connections) |



## Configuration

All settings are stored in the database and managed through the **Configuration** page in the web UI.

| Group | Key settings |
|-|-|
| **AutoPkg** | Binary path, cache path, recipe list path, report plist path |
| **Workflow** | Toggle automatic repo updates before each run |
| **Repository** | Connection type (SMB or SFTP), host, share name, mount path, public URL, credentials, directories to validate |
| **Garbage Collector** | `repoclean` binary path, retention period (e.g. `2w`), versions to keep, what to clean |
| **Notifications** | Configured notifiers with per-notifier credentials and message templates |
| **Logging** | Log level, optional file logging with path |
| **UI** | Interface language |

### Environment variables

| Variable | Default | Description |
|-||-|
| `DJANGO_SECRET_KEY` | (auto-generated) | Django secret key — set a stable value in production; also used as the master key for encrypting stored credentials |
| `DJANGO_DEBUG` | `true` | Set to `false` in production |
| `DJANGO_ALLOWED_HOSTS` | `localhost 127.0.0.1` | Space-separated list of allowed hostnames |



## Scheduling

Scheduled runs are configured on the **Schedule** page. Enable the toggle and set the cron fields (minute, hour, day of week, day of month, month). Changes apply immediately - no server restart required.



## Localisation

The UI ships with English (en-US) and French (fr-FR) translations. Switch languages under **Configuration → UI**. Additional languages can be added by creating a new JSON file in `webapp/translations/`.

> Non-english translations are still a work in progress. If you are able to assist with the translations into additional languages, contributions are welcome.



## REST API usage

### Get a token

```bash
curl -X POST http://localhost:8000/api/auth/get_token/ \
  -d "username=admin&password=yourpassword"
```

```json
{ "token": "abc123..." }
```

### Trigger a run

```bash
curl -X POST http://localhost:8000/api/tasks/trigger_run/ \
  -H "Authorization: Token abc123..."
```

```json
{ "task_uuid": "d4e5f6..." }
```

### Poll task status

```bash
curl "http://localhost:8000/api/tasks/get_task_status/?uuid=d4e5f6..." \
  -H "Authorization: Token abc123..."
```

### Get XML output

Add `-H "Accept: application/xml"` to any request to receive an XML response instead of JSON.



## SFTP repository support

SFTP connections require macFUSE and sshfs. Install them with:

```bash
python3 manage.py install_sftp_deps
```

This installs macFUSE and sshfs via Homebrew. macFUSE requires a system reboot and kernel extension approval in **System Settings → Privacy & Security** after installation.



## Production deployment

The Django development server is single-threaded and will block on SSE connections. For production, use a multi-threaded WSGI server:

```bash
pip3 install gunicorn
gunicorn autopkgrunner.wsgi:application --workers 1 --threads 8 --bind 0.0.0.0:8000
```

Set `DJANGO_DEBUG=false` and `DJANGO_ALLOWED_HOSTS` to your server's hostname. Restrict permissions on the database file since it contains API tokens and repository credentials:

```bash
chmod 600 db.sqlite3
```

Set a stable `DJANGO_SECRET_KEY` in production — this value is used to encrypt all stored credentials (repository passwords, notifier tokens). Rotating the key will invalidate any encrypted values in the database.



## License

Apache 2.0 - see [LICENSE](LICENSE).
