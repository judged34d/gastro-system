/**
 * Übernahme-Anfragen: Sprechblase am Rand (! + Zahl), Panel ohne Workflow-Abbruch.
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

    var waiterId = localStorage.getItem("user_id");
    var role = localStorage.getItem("role");
    if (!waiterId || (role && role !== "waiter" && role !== "admin")) {
        // auch ohne role bei Bedien-Seiten laden, wenn user_id da ist
        if (!waiterId) return;
    }

    var bubble = null;
    var countEl = null;
    var backdrop = null;
    var panel = null;
    var lastCount = 0;

    function ensureUi() {
        if (bubble) return;

        bubble = document.createElement("button");
        bubble.type = "button";
        bubble.className = "claim-bubble";
        bubble.setAttribute("aria-label", "Übernahme-Anfragen");
        bubble.innerHTML =
            '<span class="claim-bubble-bang">!</span>' +
            '<span class="claim-bubble-count" hidden>0</span>';
        countEl = bubble.querySelector(".claim-bubble-count");
        bubble.addEventListener("click", function (e) {
            e.preventDefault();
            e.stopPropagation();
            openPanel();
        });
        document.body.appendChild(bubble);

        backdrop = document.createElement("div");
        backdrop.className = "claim-panel-backdrop";
        backdrop.addEventListener("click", closePanel);
        document.body.appendChild(backdrop);

        panel = document.createElement("div");
        panel.className = "claim-panel";
        panel.setAttribute("role", "dialog");
        panel.setAttribute("aria-label", "Übernahme-Anfragen");
        document.body.appendChild(panel);
    }

    function setCount(n) {
        ensureUi();
        lastCount = Math.max(0, Math.floor(Number(n) || 0));
        if (lastCount <= 0) {
            bubble.classList.remove("is-visible");
            countEl.hidden = true;
            countEl.textContent = "";
            if (!panel.classList.contains("is-open")) return;
            // Panel offen lassen, Inhalt aktualisieren
            return;
        }
        bubble.classList.add("is-visible");
        countEl.hidden = false;
        countEl.textContent = lastCount > 99 ? "99+" : String(lastCount);
    }

    function closePanel() {
        if (!panel) return;
        panel.classList.remove("is-open");
        backdrop.classList.remove("is-open");
        panel.innerHTML = "";
        refreshCount();
    }

    async function openPanel() {
        ensureUi();
        panel.innerHTML = '<div class="claim-panel-title">Übernahme-Anfragen</div>' +
            '<div class="claim-panel-empty">Laden…</div>';
        panel.classList.add("is-open");
        backdrop.classList.add("is-open");

        try {
            var res = await fetch(
                apiBase().replace(/\/$/, "") +
                    "/waiter/" +
                    waiterId +
                    "/claim-requests/incoming",
                { cache: "no-store" }
            );
            var list = await res.json();
            renderList(Array.isArray(list) ? list : []);
        } catch (_) {
            panel.innerHTML =
                '<div class="claim-panel-title">Übernahme-Anfragen</div>' +
                '<div class="claim-panel-empty">Laden fehlgeschlagen</div>';
        }
    }

    function renderList(list) {
        var html = '<div class="claim-panel-title">Übernahme-Anfragen</div>';
        if (!list.length) {
            html += '<div class="claim-panel-empty">Keine offenen Anfragen.</div>';
            panel.innerHTML = html;
            setCount(0);
            return;
        }
        setCount(list.length);
        list.forEach(function (req) {
            var preview = (req.items_preview || []).join(", ") || "—";
            html +=
                '<div class="claim-panel-item" data-id="' +
                req.id +
                '">' +
                '<div class="claim-panel-meta">' +
                "<strong>" +
                (req.from_waiter_name || "Kollege") +
                "</strong> möchte #" +
                (req.order_number || req.order_id) +
                " an " +
                (req.table_name || "Tisch") +
                " übernehmen.<br>" +
                preview +
                "</div>" +
                '<div class="claim-panel-actions">' +
                '<button type="button" class="claim-accept" data-act="accept">Freigeben</button>' +
                '<button type="button" class="claim-reject" data-act="reject">Ablehnen</button>' +
                "</div></div>";
        });
        panel.innerHTML = html;
        panel.querySelectorAll("button[data-act]").forEach(function (btn) {
            btn.addEventListener("click", function () {
                var item = btn.closest(".claim-panel-item");
                var id = item && item.getAttribute("data-id");
                var act = btn.getAttribute("data-act");
                if (!id) return;
                resolveRequest(id, act, btn);
            });
        });
    }

    async function resolveRequest(requestId, act, btn) {
        var path =
            act === "accept"
                ? "/claim-requests/" + requestId + "/accept"
                : "/claim-requests/" + requestId + "/reject";
        btn.disabled = true;
        try {
            var res = await fetch(
                apiBase().replace(/\/$/, "") + "/waiter/" + waiterId + path,
                { method: "POST", cache: "no-store" }
            );
            if (!res.ok) {
                btn.disabled = false;
                return;
            }
            var item = btn.closest(".claim-panel-item");
            if (item) item.remove();
            var left = panel.querySelectorAll(".claim-panel-item").length;
            setCount(left);
            if (left === 0) {
                panel.innerHTML =
                    '<div class="claim-panel-title">Übernahme-Anfragen</div>' +
                    '<div class="claim-panel-empty">Keine offenen Anfragen.</div>';
            }
        } catch (_) {
            btn.disabled = false;
        }
    }

    async function refreshCount() {
        try {
            var res = await fetch(
                apiBase().replace(/\/$/, "") +
                    "/waiter/" +
                    waiterId +
                    "/claim-requests/incoming-count",
                { cache: "no-store" }
            );
            if (!res.ok) return;
            var data = await res.json();
            setCount(data.count);
        } catch (_) {}
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", function () {
            ensureUi();
            refreshCount();
        });
    } else {
        ensureUi();
        refreshCount();
    }
    setInterval(refreshCount, 6000);

    window.refreshClaimRequestBubble = refreshCount;
})();
