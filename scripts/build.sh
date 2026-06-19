#!/bin/bash
# Build the AutoPkg Runner .app bundle using PyInstaller.
#
# Usage:
#   bash scripts/build.sh [--sign "Developer ID Application: You (TEAMID)"]
#
# Output: dist/AutoPkg Runner.app
# Binary: dist/AutoPkg Runner.app/Contents/MacOS/autopkg-runner

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

SIGN_IDENTITY=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --sign) SIGN_IDENTITY="$2"; shift 2 ;;
        *) echo "Unknown argument: $1"; exit 1 ;;
    esac
done

echo "==> Installing PyInstaller..."
python3 -m pip install --quiet --disable-pip-version-check pyinstaller

# PyInstaller's Django hook runs django.setup() in an isolated subprocess at
# analysis time to find dotted-string imports (INSTALLED_APPS, MIDDLEWARE, etc.).
# That subprocess inherits the build environment, so DJANGO_SECRET_KEY and
# DJANGO_SETTINGS_MODULE must be set before we invoke PyInstaller.
export DJANGO_SETTINGS_MODULE=autopkgrunner.settings
if [[ -f "$REPO_ROOT/.env" ]]; then
    # Use python-dotenv to parse .env (dotenv format is not valid shell syntax).
    export DJANGO_SECRET_KEY
    DJANGO_SECRET_KEY=$(python3 -c "
from dotenv import dotenv_values
v = dotenv_values('$REPO_ROOT/.env')
print(v.get('DJANGO_SECRET_KEY', 'build-time-analysis-placeholder'))
")
else
    # No .env present — use a throwaway key for build-time analysis only.
    export DJANGO_SECRET_KEY="${DJANGO_SECRET_KEY:-build-time-analysis-placeholder}"
fi

echo "==> Building bundle..."
python3 -m PyInstaller autopkg_runner.spec --clean --noconfirm

APP="dist/AutoPkg Runner.app"
BINARY="$APP/Contents/MacOS/autopkg-runner"

# ---------------------------------------------------------------------------
# Compile asset catalog and inject into bundle
# ---------------------------------------------------------------------------
# actool compiles Assets.xcassets → Assets.car, which contains the full set of
# icon appearances (Default, Dark, and macOS 26 Tinted/Clear glass variants).
# PyInstaller only supports a single .icns; the asset catalog is injected here
# as a post-processing step so the system picks the right variant at runtime.

echo "==> Compiling asset catalog..."
ACTOOL=$(xcrun -f actool 2>/dev/null || echo "")
if [[ -z "$ACTOOL" ]]; then
    echo "    WARNING: actool not found (Xcode required). Skipping asset catalog — only Default icon will be used."
else
    ACTOOL_OUT=$(mktemp -d)
    PARTIAL_PLIST="$ACTOOL_OUT/partial_info.plist"

    xcrun actool \
        --compile "$ACTOOL_OUT" \
        --platform macosx \
        --minimum-deployment-target 13.0 \
        --app-icon AppIcon \
        --output-partial-info-plist "$PARTIAL_PLIST" \
        "$REPO_ROOT/resources/macos_iconset/Assets.xcassets" 2>&1 | grep -v '^$' | sed 's/^/    /'

    if [[ -f "$ACTOOL_OUT/Assets.car" ]]; then
        cp "$ACTOOL_OUT/Assets.car" "$APP/Contents/Resources/Assets.car"
        echo "    Assets.car injected ($(du -sh "$APP/Contents/Resources/Assets.car" | cut -f1))"

        # Add CFBundleIconName so macOS uses the asset catalog for icon lookup.
        # We keep CFBundleIconFile as a fallback for older macOS versions.
        /usr/libexec/PlistBuddy \
            -c "Add :CFBundleIconName string AppIcon" \
            "$APP/Contents/Info.plist" 2>/dev/null || \
        /usr/libexec/PlistBuddy \
            -c "Set :CFBundleIconName AppIcon" \
            "$APP/Contents/Info.plist"
        echo "    CFBundleIconName set in Info.plist"
    else
        echo "    WARNING: actool ran but produced no Assets.car — check output above."
    fi
    rm -rf "$ACTOOL_OUT"
fi

if [[ -n "$SIGN_IDENTITY" ]]; then
    echo "==> Signing with: $SIGN_IDENTITY"
    codesign --sign "$SIGN_IDENTITY" --deep --force --options runtime "$APP"
    echo "==> Verifying signature..."
    codesign --verify --deep --strict "$APP" && echo "    Signature OK"
else
    echo "==> Applying ad-hoc signature (local/testing only)..."
    codesign --sign - --deep --force "$APP"
fi

echo ""
echo "Build complete."
echo "  App bundle : $APP"
echo "  Binary     : $BINARY"
echo ""
echo "First-run setup:"
echo "  1. Grant Full Disk Access to the app in:"
echo "     System Settings > Privacy & Security > Full Disk Access"
echo "  2. Run first-time setup (migrations + admin account):"
echo "     \"$BINARY\" setup"
echo "  3. Start the server:"
echo "     \"$BINARY\" serve"
