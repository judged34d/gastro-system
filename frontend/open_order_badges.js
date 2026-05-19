/**
 * Rotes Mengen-Fähnchen auf Aktions-Buttons (offene Bestellungen).
 */
(function () {
    function apiBase() {
        if (typeof window.getGastroApiBase === "function") {
            return window.getGastroApiBase();
        }
        if (window.GASTRO_API_BASE) return window.GASTRO_API_BASE;
        try {
            var ls = localStorage.getItem("gastro_api_base");
            if (ls && ls.trim()) return ls.trim().replace(/\/$/, "");
        } catch (e) {}
        var p = window.location.protocol;
        var h = window.location.hostname || "";
        if (/(^|\.)mpbin\.de$/i.test(h)) return "https://api.mpbin.de";
        if (p === "file:") return "http://localhost:8000";
        return p + "//" + (h || "localhost") + ":8000";
    }

    function applyBtnQtyBadge(badgeEl, count) {
        if (!badgeEl) return;
        var n = Math.floor(Number(count) || 0);
        if (n <= 0) {
            badgeEl.hidden = true;
            badgeEl.textContent = "";
            badgeEl.removeAttribute("aria-label");
            return;
        }
        badgeEl.hidden = false;
        badgeEl.textContent = n > 99 ? "99+" : String(n);
        badgeEl.setAttribute("aria-label", n + " offene Bestellungen");
    }

    async function fetchWaiterOpenOrderCount(waiterId) {
        var base = apiBase().replace(/\/$/, "");
        var res = await fetch(base + "/waiter/" + waiterId + "/orders/open-count", {
            cache: "no-store",
        });
        if (!res.ok) return 0;
        var data = await res.json();
        return Number(data.count) || 0;
    }

    async function fetchStationOpenOrderCount(stationId) {
        var base = apiBase().replace(/\/$/, "");
        var res = await fetch(base + "/station/" + stationId + "/orders/open-count", {
            cache: "no-store",
        });
        if (!res.ok) return 0;
        var data = await res.json();
        return Number(data.count) || 0;
    }

    async function refreshWaiterOpenOrderBadge(waiterId, badgeEl) {
        try {
            applyBtnQtyBadge(badgeEl, await fetchWaiterOpenOrderCount(waiterId));
        } catch (_) {
            applyBtnQtyBadge(badgeEl, 0);
        }
    }

    async function refreshStationOpenOrderBadge(stationId, badgeEl) {
        try {
            applyBtnQtyBadge(badgeEl, await fetchStationOpenOrderCount(stationId));
        } catch (_) {
            applyBtnQtyBadge(badgeEl, 0);
        }
    }

    window.applyBtnQtyBadge = applyBtnQtyBadge;
    window.fetchWaiterOpenOrderCount = fetchWaiterOpenOrderCount;
    window.fetchStationOpenOrderCount = fetchStationOpenOrderCount;
    window.refreshWaiterOpenOrderBadge = refreshWaiterOpenOrderBadge;
    window.refreshStationOpenOrderBadge = refreshStationOpenOrderBadge;
})();
