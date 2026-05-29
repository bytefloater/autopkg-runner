"""
manage.py install_sftp_deps
────────────────────────────
Install the system dependencies required for SFTP repository connections
on macOS: macFUSE (FUSE framework) and sshfs-mac (via the gromgit/fuse tap).

Steps
-----
1. Check if sshfs is already installed — exit early if so.
2. Ensure Homebrew is present — install it if missing.
3. Install the macFUSE cask (FUSE kernel extension).
4. Tap gromgit/fuse and install sshfs-mac.
5. Print post-install reminders (reboot + kernel extension approval).
"""

import shutil
import subprocess
import sys

from django.core.management.base import BaseCommand


_BREW_INSTALL_URL = (
    "https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh"
)

_WIDTH = 60


class Command(BaseCommand):
    help = (
        "Install macFUSE and sshfs-mac on macOS — required for SFTP "
        "repository connections."
    )

    def handle(self, *args, **options):
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("─" * _WIDTH))
        self.stdout.write(self.style.SUCCESS("  SFTP Dependency Installer"))
        self.stdout.write(self.style.SUCCESS("─" * _WIDTH))
        self.stdout.write("")

        # ── Step 1: Check for sshfs ───────────────────────────────────────────
        self._step("1", "Checking for sshfs")
        if shutil.which("sshfs"):
            self._ok("sshfs is already installed — nothing to do.")
            self.stdout.write("")
            return

        self.stdout.write("      sshfs not found — will install via Homebrew.")

        # ── Step 2: Ensure Homebrew ───────────────────────────────────────────
        self._step("2", "Checking for Homebrew")
        if shutil.which("brew"):
            self._ok("Homebrew is already installed.")
        else:
            self.stdout.write("      Homebrew not found — installing...")
            self.stdout.write("")
            try:
                subprocess.run(
                    [
                        "/bin/bash", "-c",
                        f'curl -fsSL {_BREW_INSTALL_URL} | /bin/bash',
                    ],
                    check=True,
                )
            except subprocess.CalledProcessError:
                self.stderr.write(
                    self.style.ERROR(
                        "\n  Homebrew installation failed. "
                        "Visit https://brew.sh for manual instructions."
                    )
                )
                sys.exit(1)
            self._ok("Homebrew installed.")

        # ── Step 3: macFUSE ───────────────────────────────────────────────────
        self._step("3", "Installing macFUSE (FUSE kernel extension)")
        self.stdout.write("")
        try:
            subprocess.run(
                ["brew", "install", "--cask", "macfuse"],
                check=True,
            )
        except subprocess.CalledProcessError:
            self.stderr.write(
                self.style.ERROR(
                    "\n  macFUSE installation failed. "
                    "You may need to run this command as an administrator."
                )
            )
            sys.exit(1)
        self._ok("macFUSE installed.")

        # ── Step 4: sshfs-mac ─────────────────────────────────────────────────
        self._step("4", "Tapping gromgit/fuse and installing sshfs-mac")
        self.stdout.write("")
        try:
            subprocess.run(["brew", "tap", "gromgit/fuse"], check=True)
            subprocess.run(
                ["brew", "install", "gromgit/fuse/sshfs-mac"],
                check=True,
            )
        except subprocess.CalledProcessError:
            self.stderr.write(
                self.style.ERROR("\n  sshfs-mac installation failed.")
            )
            sys.exit(1)
        self._ok("sshfs-mac installed.")

        # ── Done ──────────────────────────────────────────────────────────────
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("─" * _WIDTH))
        self.stdout.write(self.style.SUCCESS("  Installation complete!"))
        self.stdout.write(self.style.SUCCESS("─" * _WIDTH))
        self.stdout.write("")
        self._warn(
            "macFUSE requires a system reboot after first install."
        )
        self._warn(
            "Go to System Settings › Privacy & Security and approve\n"
            "        the macFUSE kernel extension, then reboot."
        )
        self.stdout.write("")
        self.stdout.write(
            "  Once rebooted, restart AutoPkg Runner — SFTP connections\n"
            "  will be available immediately."
        )
        self.stdout.write("")

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _step(self, number: str, description: str) -> None:
        self.stdout.write(
            f'\n  {self.style.MIGRATE_HEADING(f"[{number}]")} {description}'
        )

    def _ok(self, message: str) -> None:
        self.stdout.write(f'      {self.style.SUCCESS("✓")} {message}')

    def _warn(self, message: str) -> None:
        self.stdout.write(f'      {self.style.WARNING("⚠")}  {message}')
