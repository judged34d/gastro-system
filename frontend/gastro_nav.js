/**
 * Gemeinsame Navigation (App-Start, Admin-Unterseiten).
 */
(function () {
    var APP_HOME = "index.html";

    window.gastroNavigate = function (href) {
        if (!href) return;
        window.location.href = href;
    };

    /** Auswahlseite: Login, Orderstatus Viewer, Admin-Einstieg */
    window.goToAppHome = function () {
        try {
            sessionStorage.removeItem("gastro_admin_ok");
        } catch (_) {}
        window.location.href = APP_HOME;
    };

    /** Admin-Hauptseite (Session bleibt erhalten) */
    window.goToAdminHome = function () {
        window.location.href = "admin.html";
    };
})();
