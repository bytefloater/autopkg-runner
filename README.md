# AutoPkg Runner

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg?style=for-the-badge)](LICENSE)<br>
![Version 3.0.0](https://img.shields.io/badge/version-3.0.0-green?style=for-the-badge)

A web-based management interface for [AutoPkg](https://github.com/autopkg/autopkg) - the macOS software packaging automation tool. AutoPkg Runner wraps your AutoPkg workflows in a Django web application with real-time run monitoring, a REST API, a mobile PWA, and scheduled execution, replacing fragile cron scripts and log trawling with a proper operations dashboard.

---

## Features

### Web UI

- **Dashboard** - last run summary, 30-day success rate, next scheduled run, and a one-click manual trigger
- **Run detail** - GitHub Actions-style stage timeline with live log streaming; stage status icons and the log panel update in real time without a page refresh
- **Run history** - paginated list of all pipeline executions with status badges and duration
- **Schedule** - cron-based scheduling with an enable/disable toggle; changes apply immediately without a server restart
- **Configuration** - full pipeline configuration through the browser; no config files to edit
- **API tokens** - create and revoke per-user tokens for REST API access

### Mobile PWA

- Installable progressive web app with an iOS-native look and feel
- Bottom tab bar navigation with SPA-style page transitions
- Real-time stage status updates and live log streaming on run detail
- Install directly from Safari - no App Store required

<img src="docs/images/sc_mobile_dashboard.png" alt="Mobile dashboard" width="300">

### Notifications

Three notification providers are supported. Multiple notifiers can be configured and each can have its own custom title and message template.

| Provider | Notes |
|----------|-------|
| **Pushover** | Push notification to iPhone/iPad/Mac via the Pushover app |
| **Discord** | Message to a Discord channel via an incoming webhook |
| **WebPush** | Native browser push notification - works with the installed PWA or any subscribed browser session |

Notifications are always dispatched at the end of a run regardless of whether earlier pipeline stages succeeded or failed.

### REST API

All endpoints support both JSON (`Accept: application/json`) and XML (`Accept: application/xml`) responses. Token authentication is required for all endpoints except `get_token`.

| Method | Endpoint | Description |
|--------|----------|-------------|
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
2. **Update Repos** - runs `autopkg repo-update all` to pull the latest recipe repos (optional, can be disabled per run)
3. **Trust Verification** - runs `autopkg verify-trust-info` on all recipes and updates trust as needed
4. **Mount Repository** - connects to the Munki repository over SMB or SFTP
5. **Run AutoPkg** - batch executes all configured recipes and writes a report plist
6. **Generate Report** - renders a timestamped HTML report from a Django template
7. **Garbage Collector** - prunes old cache files, temp files, and stale HTML reports using `repoclean`
8. **Send Notifications** - dispatches alerts to all configured notifiers

---

## Requirements

- macOS (AutoPkg is macOS-only)
- Python 3.9+
- [AutoPkg](https://github.com/autopkg/autopkg) installed

---

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

---

## Management commands

| Command | Description |
|---------|-------------|
| `manage.py setup` | One-shot initialisation: migrate, create defaults, generate admin account |
| `manage.py serve` | Start the development server (`--network` to bind to all interfaces, `--port` to change port) |
| `manage.py resetpassword` | Generate and set a new random password for the admin account |
| `manage.py generate_vapid_keys` | Generate VAPID keys for WebPush notifications and store them in the database |
| `manage.py install_sftp_deps` | Install macFUSE and sshfs via Homebrew (required for SFTP repository connections) |

---

## Configuration

All settings are stored in the database and managed through the **Configuration** page in the web UI.

| Group | Key settings |
|-------|-------------|
| **AutoPkg** | Binary path, cache path, recipe list path, report plist path |
| **Repository** | Connection type (SMB or SFTP), host, share name, mount path, public URL, credentials, directories to validate |
| **Garbage Collector** | `repoclean` binary path, retention period (e.g. `2w`), versions to keep, what to clean |
| **Notifications** | Configured notifiers with per-notifier credentials and message templates |
| **Logging** | Log level, optional file logging with path |
| **Report** | HTML report template filename |

### Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DJANGO_SECRET_KEY` | (auto-generated) | Django secret key - set a stable value in production |
| `DJANGO_DEBUG` | `true` | Set to `false` in production |
| `DJANGO_ALLOWED_HOSTS` | `localhost 127.0.0.1` | Space-separated list of allowed hostnames |

---

## Scheduling

Scheduled runs are configured on the **Schedule** page. Enable the toggle and set the cron fields (minute, hour, day of week, day of month, month). Changes apply immediately - no server restart required.

---

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

---

## SFTP repository support

SFTP connections require macFUSE and sshfs. Install them with:

```bash
python3 manage.py install_sftp_deps
```

This installs macFUSE and sshfs via Homebrew. macFUSE requires a system reboot and kernel extension approval in **System Settings → Privacy & Security** after installation.

---

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

---

## License

Apache 2.0 - see [LICENSE](LICENSE).
