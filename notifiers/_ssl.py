"""
Shared SSL context helper for notifier modules.

Uses the OS-native certificate store via *pip-system-certs*, which patches
``certifi.where()`` and ``ssl.create_default_context()`` at startup so that
certificates managed through macOS Keychain, Windows Certificate Store, or
the system OpenSSL store are trusted without any manual setup.  Because the
patch is transparent, no explicit API call is required here - importing
*certifi* after *pip-system-certs* has been installed is sufficient.

Falls back to Python's built-in default context if *certifi* is not
available, so the code works in environments without the package installed.
"""
import ssl


def ssl_context() -> ssl.SSLContext:
    """Return an SSL context that trusts the OS certificate store."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        pass

    return ssl.create_default_context()
