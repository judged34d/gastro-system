/**
 * Deckel-Kacheln: alphabetisch (Ä→A), Reiter, Rendering + Loader.
 */
(function () {
    const CACHE_PREFIX = "gastro_tabs_v1:";
    const FETCH_TIMEOUT_MS = 12000;
    const CACHE_FRESH_MS = 90000;

    function tabSortKey(name) {
        return String(name || "")
            .trim()
            .toLocaleLowerCase("de")
            .replace(/ä/g, "a")
            .replace(/ö/g, "o")
            .replace(/ü/g, "u")
            .replace(/ß/g, "ss");
    }

    function tabGroupLetter(name) {
        const k = tabSortKey(name);
        const c = k.charAt(0).toUpperCase();
        if (c >= "A" && c <= "Z") return c;
        if (c >= "0" && c <= "9") return "#";
        return "#";
    }

    function sortTabsAlpha(tabs) {
        return (tabs || []).slice().sort(function (a, b) {
            const ka = tabSortKey(a.name);
            const kb = tabSortKey(b.name);
            const cmp = ka.localeCompare(kb, "de");
            if (cmp !== 0) return cmp;
            return Number(a.id) - Number(b.id);
        });
    }

    function groupTabsByLetter(tabs) {
        const groups = {};
        sortTabsAlpha(tabs).forEach(function (t) {
            const letter = tabGroupLetter(t.name);
            if (!groups[letter]) groups[letter] = [];
            groups[letter].push(t);
        });
        return Object.keys(groups)
            .sort(function (a, b) {
                if (a === "#") return 1;
                if (b === "#") return -1;
                return a.localeCompare(b, "de");
            })
            .map(function (letter) {
                return { letter: letter, tabs: groups[letter] };
            });
    }

    function formatEuro(v) {
        return Number(v || 0).toFixed(2).replace(".", ",") + " €";
    }

    function tabsCacheKey(stationId) {
        return CACHE_PREFIX + (stationId != null && stationId !== "" ? String(stationId) : "all");
    }

    function readTabsCacheEntry(stationId) {
        try {
            const raw = sessionStorage.getItem(tabsCacheKey(stationId));
            if (!raw) return null;
            const parsed = JSON.parse(raw);
            if (!parsed || !Array.isArray(parsed.tabs)) return null;
            return parsed;
        } catch (_) {
            return null;
        }
    }

    function readTabsCache(stationId) {
        const entry = readTabsCacheEntry(stationId);
        return entry ? entry.tabs : null;
    }

    function isTabsCacheFresh(stationId) {
        const entry = readTabsCacheEntry(stationId);
        if (!entry || !entry.ts) return false;
        return Date.now() - Number(entry.ts) < CACHE_FRESH_MS;
    }

    function writeTabsCache(stationId, tabs) {
        try {
            sessionStorage.setItem(
                tabsCacheKey(stationId),
                JSON.stringify({ ts: Date.now(), tabs: tabs })
            );
        } catch (_) {}
    }

    function invalidateTabsCache(stationId) {
        try {
            sessionStorage.removeItem(tabsCacheKey(stationId));
            sessionStorage.removeItem(tabsCacheKey(null));
        } catch (_) {}
    }

    function getTabsWrap(container) {
        if (!container) return null;
        return container.closest(".tabs-wrap") || container.parentElement;
    }

    function setTabsFetching(container, busy) {
        const wrap = getTabsWrap(container);
        if (!wrap) return;
        wrap.classList.toggle("tabs-wrap-fetching", !!busy);
    }

    function hasTabContent(container) {
        if (!container) return false;
        return !!container.querySelector(
            ".tabs-unified-grid, .tab-tile, .tab-empty-msg, .tab-loading-msg"
        );
    }

    function showTabsLoading(container) {
        if (!container || hasTabContent(container)) return;
        const el = document.createElement("div");
        el.className = "tab-loading-msg";
        el.textContent = "Deckel werden geladen…";
        container.replaceChildren(el);
    }

    function renderTabTiles(container, tabs, opts) {
        if (!container) return;
        opts = opts || {};

        const grid = document.createElement("div");
        grid.className = "tabs-unified-grid";

        if (opts.leadAddButton && typeof opts.onAdd === "function") {
            const add = document.createElement("button");
            add.type = "button";
            add.className = "tab-tile tab-tile-add";
            add.onclick = opts.onAdd;
            add.innerHTML =
                '<div class="tab-name">+ Deckel</div><div class="tab-balance">Hinzufügen</div>';
            grid.appendChild(add);
        }

        const list = Array.isArray(tabs) ? tabs : [];
        const groups = groupTabsByLetter(list);

        if (!groups.length && !opts.leadAddButton) {
            const empty = document.createElement("div");
            empty.className = "tab-empty-msg";
            empty.textContent = "Keine Deckel vorhanden.";
            container.replaceChildren(empty);
            container.classList.add("tabs-list");
            container.classList.remove("tabs-row");
            return;
        }

        groups.forEach(function (g) {
            const hdr = document.createElement("div");
            hdr.className = "tab-section-letter";
            hdr.textContent = g.letter;
            grid.appendChild(hdr);

            g.tabs.forEach(function (t) {
                const balance = Math.max(0, Number(t.balance || 0));

                const b = document.createElement("button");
                b.type = "button";
                b.className = "tab-tile";
                if (balance <= 0.0001) {
                    b.classList.add("tab-tile-zero");
                } else {
                    b.classList.add("tab-tile-open");
                }
                if (
                    opts.disableTabId != null &&
                    Number(opts.disableTabId) === Number(t.id)
                ) {
                    b.disabled = true;
                }

                const balLine =
                    balance > 0.0001
                        ? "Offen: " + formatEuro(balance)
                        : "Ausgeglichen";

                b.innerHTML =
                    '<div class="tab-name">' +
                    String(t.name || "") +
                    "</div>" +
                    '<div class="tab-balance">' +
                    balLine +
                    (opts.onSelect ? "<br><small>Tippen = auswählen</small>" : "") +
                    "</div>";

                if (typeof opts.onSelect === "function") {
                    b.addEventListener("click", function () {
                        opts.onSelect(t);
                    });
                }

                if (typeof opts.onRename === "function") {
                    const ren = document.createElement("button");
                    ren.type = "button";
                    ren.className = "tab-tile-edit";
                    ren.title = "Name bearbeiten";
                    ren.textContent = "✎";
                    ren.onclick = function (ev) {
                        ev.stopPropagation();
                        opts.onRename(t);
                    };
                    b.appendChild(ren);
                }

                grid.appendChild(b);
            });
        });

        container.replaceChildren(grid);
        container.classList.add("tabs-list");
        container.classList.remove("tabs-row");
    }

    function fetchTabsWithTimeout(url, timeoutMs) {
        const inflight = (window.__gastroTabsInflight =
            window.__gastroTabsInflight || new Map());
        if (inflight.has(url)) {
            return inflight.get(url);
        }

        const controller = new AbortController();
        const timer = setTimeout(function () {
            controller.abort();
        }, timeoutMs);

        const promise = fetch(url, {
            cache: "no-store",
            signal: controller.signal,
        })
            .finally(function () {
                clearTimeout(timer);
                inflight.delete(url);
            });

        inflight.set(url, promise);
        return promise;
    }

    function createTabListLoader(config) {
        let loadGen = 0;
        let loadPromise = null;
        let containerEl = null;

        function resolveContainer() {
            if (typeof config.getContainer === "function") {
                containerEl = config.getContainer();
            }
            return containerEl;
        }

        function paintFromCache(stationId, skipCache) {
            if (skipCache) return false;
            const entry = readTabsCacheEntry(stationId);
            if (!entry) return false;
            config.onRender(entry.tabs);
            return true;
        }

        async function load(options) {
            const opts = options || {};
            if (loadPromise) {
                if (opts.skipCache) {
                    await loadPromise.catch(function () {});
                    return doLoad(opts);
                }
                return loadPromise;
            }
            loadPromise = doLoad(opts).finally(function () {
                loadPromise = null;
            });
            return loadPromise;
        }

        async function doLoad(opts) {
            const gen = ++loadGen;
            const container = resolveContainer();
            const stationId =
                typeof config.getStationId === "function"
                    ? config.getStationId()
                    : null;

            const showedCache = paintFromCache(stationId, !!opts.skipCache);
            if (!showedCache) {
                showTabsLoading(container);
            }

            const cacheFresh = !opts.skipCache && isTabsCacheFresh(stationId);
            if (cacheFresh && showedCache) {
                setTimeout(function () {
                    if (gen === loadGen) {
                        fetchTabsNetwork(gen, stationId, container, true);
                    }
                }, 600);
                return;
            }

            await fetchTabsNetwork(gen, stationId, container, showedCache);
        }

        async function fetchTabsNetwork(gen, stationId, container, showedCache) {
            if (container) {
                setTabsFetching(container, true);
            }

            const qs =
                stationId != null && stationId !== ""
                    ? "?station_id=" + encodeURIComponent(stationId)
                    : "";
            const url = config.api + "/tabs" + qs;

            try {
                const res = await fetchTabsWithTimeout(url, FETCH_TIMEOUT_MS);
                if (!res.ok) {
                    const t = await res.text();
                    throw new Error(t || "HTTP " + res.status);
                }
                const data = await res.json();
                if (gen !== loadGen) return;
                const tabs = Array.isArray(data) ? data : [];
                writeTabsCache(stationId, tabs);
                config.onRender(tabs);
            } catch (e) {
                if (gen !== loadGen) return;
                if (e && e.name === "AbortError") {
                    if (!showedCache && typeof config.onError === "function") {
                        config.onError(new Error("Zeitüberschreitung beim Laden"));
                    }
                    return;
                }
                if (!showedCache && typeof config.onError === "function") {
                    config.onError(e);
                }
            } finally {
                if (gen === loadGen && container) {
                    setTabsFetching(container, false);
                }
            }
        }

        var lastVisibilityLoad = 0;

        window.addEventListener("pageshow", function () {
            load({ skipCache: false });
        });

        document.addEventListener("visibilitychange", function () {
            if (document.visibilityState !== "visible") return;
            const now = Date.now();
            if (now - lastVisibilityLoad < 2000) return;
            lastVisibilityLoad = now;
            const stationId =
                typeof config.getStationId === "function"
                    ? config.getStationId()
                    : null;
            if (!isTabsCacheFresh(stationId)) {
                load({ skipCache: false });
            }
        });

        return {
            load: load,
            refresh: function () {
                return load({ skipCache: true });
            },
        };
    }

    window.sortTabsAlpha = sortTabsAlpha;
    window.groupTabsByLetter = groupTabsByLetter;
    window.renderTabTiles = renderTabTiles;
    window.tabSortKey = tabSortKey;
    window.invalidateTabsCache = invalidateTabsCache;
    window.createTabListLoader = createTabListLoader;
})();
