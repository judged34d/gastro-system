/**
 * Einfache Navigation – kein Lock (Lock blockierte Zurück nach bfcache / schnellen Taps).
 */
(function () {
    window.gastroNavigate = function (href) {
        if (!href) return;
        window.location.href = href;
    };
})();
