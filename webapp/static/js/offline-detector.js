// Detect when connection is lost and navigate to error page
(function() {
  function showOfflineError() {
    const url = new URL('/static/offline-error.html', window.location.origin);
    url.searchParams.set('type', 'offline');
    url.searchParams.set('timestamp', new Date().toISOString());
    window.location.href = url.toString();
  }

  window.addEventListener('offline', showOfflineError);
})();
