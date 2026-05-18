/**
 * Layout presets: auto | phone | tablet | wall
 * Effective layout is always phone | tablet | wall on <html data-layout="…">.
 */
(function () {
    const STORAGE_KEY = "gastro_layout_preset";
    const VALID = ["auto", "phone", "tablet", "wall"];

    function detectLayout() {
        const w = window.innerWidth;
        const h = window.innerHeight;
        const minSide = Math.min(w, h);
        const maxSide = Math.max(w, h);
        const landscape = w >= h;

        if (maxSide >= 1100 && landscape && minSide >= 500) {
            return "wall";
        }
        if (!landscape && w < 520) {
            return "phone";
        }
        if (w < 640) {
            return "phone";
        }
        if (w < 900 && !landscape) {
            return "phone";
        }
        return "tablet";
    }

    function getStoredPreset() {
        try {
            const v = (localStorage.getItem(STORAGE_KEY) || "auto").trim().toLowerCase();
            return VALID.indexOf(v) >= 0 ? v : "auto";
        } catch (_) {
            return "auto";
        }
    }

    function getEffectiveLayout() {
        const preset = getStoredPreset();
        if (preset === "auto") {
            return detectLayout();
        }
        return preset;
    }

    function applyLayout() {
        const preset = getStoredPreset();
        const effective = getEffectiveLayout();
        const root = document.documentElement;
        root.dataset.layout = effective;
        root.dataset.layoutPreset = preset;
    }

    let resizeTimer = null;
    function onResize() {
        clearTimeout(resizeTimer);
        resizeTimer = setTimeout(applyLayout, 150);
    }

    applyLayout();
    window.addEventListener("resize", onResize);
    window.addEventListener("orientationchange", function () {
        setTimeout(applyLayout, 100);
    });

    window.GastroLayout = {
        STORAGE_KEY: STORAGE_KEY,
        VALID_PRESETS: VALID,
        detectLayout: detectLayout,
        getStoredPreset: getStoredPreset,
        getEffectiveLayout: getEffectiveLayout,
        setPreset: function (preset) {
            const p = String(preset || "auto").trim().toLowerCase();
            const value = VALID.indexOf(p) >= 0 ? p : "auto";
            try {
                localStorage.setItem(STORAGE_KEY, value);
            } catch (_) {}
            applyLayout();
            return value;
        },
        applyLayout: applyLayout,
    };
})();
