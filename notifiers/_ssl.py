"""
Shared SSL context helper for notifier modules.

Uses the OS-native certificate store via *truststore* so that certificates
managed through macOS Keychain, Windows Certificate Store, or the system
OpenSSL store are trusted without any manual setup.

Falls back to *certifi*'s bundled Mozilla CA bundle, then to Python's built-in
default context, so the code works in environments where neither extra package
is installed.
"""
import ssl


def ssl_context() -> ssl.SSLContext:
    """Return an SSL context that trusts the OS certificate store."""
    try:
        import truststore
        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except ImportError:
        pass

    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        pass

    return ssl.create_default_context()
