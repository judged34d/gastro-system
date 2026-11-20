/**
 * Theken-Ton: neue Bestellungen von Bedienung/Gast (nicht eigene Theken-Orders).
 */
(function () {
    var knownByStation = {};
    var readyByStation = {};
    var audioCtx = null;
    var unlocked = false;

    function stationKey(stationId) {
        return String(stationId || "0");
    }

    function ensureKnown(stationId) {
        var key = stationKey(stationId);
        if (!knownByStation[key]) {
            knownByStation[key] = new Set();
        }
        return knownByStation[key];
    }

    function isWaiterSideSource(source) {
        return source !== "station";
    }

    function unlockAudio() {
        if (unlocked) return;
        try {
            var Ctx = window.AudioContext || window.webkitAudioContext;
            if (!Ctx) return;
            if (!audioCtx) {
                audioCtx = new Ctx();
            }
            if (audioCtx.state === "suspended") {
                audioCtx.resume();
            }
            unlocked = true;
            hideHint();
        } catch (_) {}
    }

    function playTone(freq, startAt, duration) {
        if (!audioCtx || !unlocked) return;
        var osc = audioCtx.createOscillator();
        var gain = audioCtx.createGain();
        osc.type = "sine";
        osc.frequency.value = freq;
        osc.connect(gain);
        gain.connect(audioCtx.destination);
        gain.gain.setValueAtTime(0.0001, startAt);
        gain.gain.exponentialRampToValueAtTime(0.22, startAt + 0.02);
        gain.gain.exponentialRampToValueAtTime(0.0001, startAt + duration);
        osc.start(startAt);
        osc.stop(startAt + duration + 0.02);
    }

    function playNewOrderSound(count) {
        unlockAudio();
        if (!audioCtx || !unlocked) {
            showHint();
            return;
        }
        var n = Math.min(Math.max(Number(count) || 1, 1), 3);
        var base = audioCtx.currentTime;
        for (var i = 0; i < n; i++) {
            playTone(880, base + i * 0.42, 0.28);
            playTone(1174, base + i * 0.42 + 0.14, 0.22);
        }
    }

    function showHint() {
        var el = document.getElementById("station-audio-hint");
        if (!el) {
            el = document.createElement("button");
            el.id = "station-audio-hint";
            el.type = "button";
            el.className = "station-audio-hint";
            el.textContent = "🔔 Ton aktivieren";
            el.addEventListener("click", function () {
                unlockAudio();
                playNewOrderSound(1);
            });
            document.body.appendChild(el);
        }
        el.style.display = "block";
    }

    function hideHint() {
        var el = document.getElementById("station-audio-hint");
        if (el) el.style.display = "none";
    }

    function processOrders(orders, stationId) {
        if (!Array.isArray(orders)) return;
        var key = stationKey(stationId);
        var known = ensureKnown(stationId);
        var alertsReady = !!readyByStation[key];
        var fresh = [];

        orders.forEach(function (o) {
            if (!o) return;
            var id = Number(o.order_id);
            if (!Number.isFinite(id) || id <= 0) return;
            var source = o.source || "waiter";
            if (!isWaiterSideSource(source)) {
                known.add(id);
                return;
            }
            if (alertsReady && !known.has(id)) {
                fresh.push(o);
            }
            known.add(id);
        });

        readyByStation[key] = true;

        if (fresh.length) {
            playNewOrderSound(fresh.length);
        }
    }

    function bindUnlockOnInteraction() {
        if (window.__gastroStationAudioBound) return;
        window.__gastroStationAudioBound = true;
        var once = function () {
            unlockAudio();
        };
        document.addEventListener("pointerdown", once, { passive: true });
        document.addEventListener("keydown", once);
    }

    bindUnlockOnInteraction();

    window.GastroStationAlerts = {
        process: processOrders,
        unlock: unlockAudio,
        playTest: function () {
            playNewOrderSound(1);
        },
    };
})();
