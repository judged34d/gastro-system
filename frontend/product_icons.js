/**
 * Shared product icon rendering (standard emoji + uploaded images).
 */
(function () {
    function apiBase() {
        if (typeof window.getGastroApiBase === "function") {
            return window.getGastroApiBase();
        }
        return window.GASTRO_API_BASE || "";
    }

    function resolveIconUrl(url) {
        if (!url) return "";
        var path = url;
        if (/^https?:\/\//i.test(url)) {
            try {
                var parsed = new URL(url);
                if (parsed.pathname.indexOf("/media/") === 0) {
                    return window.location.origin + parsed.pathname;
                }
            } catch (_e) {
                return url;
            }
            return url;
        }
        path = url.startsWith("/") ? url : "/" + url;
        if (path.indexOf("/media/") === 0) {
            return window.location.origin + path;
        }
        var base = apiBase().replace(/\/$/, "");
        return base + path;
    }

    function emojiForProduct(product) {
        if (!product) return null;
        if (product.icon_emoji) return String(product.icon_emoji);
        if (product.icon_type === "standard" && product.icon_ref) {
            var map = window.__gastroStandardEmojiMap;
            if (map && map[product.icon_ref]) return map[product.icon_ref];
        }
        return null;
    }

    function loadStandardEmojiMap() {
        if (window.__gastroStandardEmojiMap) {
            return Promise.resolve(window.__gastroStandardEmojiMap);
        }
        var base = apiBase().replace(/\/$/, "");
        if (!base) {
            window.__gastroStandardEmojiMap = {};
            return Promise.resolve(window.__gastroStandardEmojiMap);
        }
        return fetch(base + "/icons/standard", { cache: "no-store" })
            .then(function (r) {
                return r.ok ? r.json() : { icons: [] };
            })
            .then(function (data) {
                var map = {};
                (data.icons || []).forEach(function (item) {
                    if (item.id && item.emoji) map[item.id] = item.emoji;
                });
                window.__gastroStandardEmojiMap = map;
                return map;
            })
            .catch(function () {
                window.__gastroStandardEmojiMap = {};
                return window.__gastroStandardEmojiMap;
            });
    }

    function appendFallbackIcon(parent, className) {
        const span = document.createElement("span");
        span.className = (className || "product-icon") + " product-icon-fallback";
        span.setAttribute("aria-hidden", "true");
        span.textContent = "🍽️";
        parent.appendChild(span);
    }

    /** Icons per DOM (zuverlässiger auf iOS/Safari als innerHTML). */
    function mountProductIcon(parent, product, className) {
        if (!parent) return;
        const cls = className || "product-icon";
        parent.textContent = "";
        parent.classList.add("product-icon-slot");

        var emoji = emojiForProduct(product);
        if (emoji) {
            const span = document.createElement("span");
            span.className = cls + " product-icon-emoji";
            span.setAttribute("aria-hidden", "true");
            span.textContent = emoji;
            parent.appendChild(span);
            return;
        }

        if (product && product.icon_url) {
            const img = document.createElement("img");
            img.className = cls + " product-icon-img";
            img.src = resolveIconUrl(product.icon_url);
            img.alt = product.name || "Artikel";
            img.loading = "eager";
            img.decoding = "async";
            img.onerror = function () {
                img.remove();
                appendFallbackIcon(parent, cls);
            };
            parent.appendChild(img);
            return;
        }

        appendFallbackIcon(parent, cls);
    }

    function productIconHtml(product, className) {
        const cls = className || "product-icon";
        var emoji = emojiForProduct(product);
        if (emoji) {
            return (
                '<span class="' +
                cls +
                ' product-icon-emoji" aria-hidden="true">' +
                emoji +
                "</span>"
            );
        }
        if (product && product.icon_url) {
            const src = resolveIconUrl(product.icon_url);
            const alt = (product.name || "Artikel").replace(/"/g, "&quot;");
            return (
                '<img class="' +
                cls +
                ' product-icon-img" src="' +
                src +
                '" alt="' +
                alt +
                '" loading="eager" decoding="async">'
            );
        }
        return '<span class="' + cls + ' product-icon-fallback" aria-hidden="true">🍽️</span>';
    }

    function productQtyBadgeHtml(qty) {
        const n = Math.floor(Number(qty) || 0);
        if (n <= 0) return "";
        return (
            '<span class="product-qty-badge" aria-label="Gebucht: ' +
            n +
            '">' +
            String(n) +
            "</span>"
        );
    }

    function productTileRemoveHtml(productId, qty) {
        const n = Math.floor(Number(qty) || 0);
        if (n <= 0) return "";
        const id = Number(productId);
        return (
            '<button type="button" class="product-tile-remove" data-product-id="' +
            id +
            '" aria-label="Einen Artikel entfernen" title="Einen entfernen">🗑</button>'
        );
    }

    function productTileHtml(product, priceText, qty) {
        return (
            productQtyBadgeHtml(qty) +
            '<div class="product-tile-main">' +
            '<span class="product-icon-slot" aria-hidden="true"></span>' +
            '<div class="product-tile-info">' +
            "<b>" +
            (product.name || "") +
            "</b>" +
            '<span class="product-tile-price">' +
            priceText +
            "</span>" +
            "</div>" +
            "</div>" +
            '<div class="product-tile-actions">' +
            productTileRemoveHtml(product.id, qty) +
            "</div>"
        );
    }

    function bindProductTile(tileEl, product, onAdd, onRemove) {
        if (!tileEl) return;
        const p = product && typeof product === "object" ? product : { id: product };
        const pid = Number(p.id);

        const iconSlot = tileEl.querySelector(".product-icon-slot");
        if (iconSlot) {
            loadStandardEmojiMap().then(function () {
                mountProductIcon(iconSlot, p);
            });
        }

        tileEl.onclick = function (ev) {
            if (ev.target.closest(".product-tile-remove")) return;
            if (typeof onAdd === "function") onAdd();
        };
        const removeBtn = tileEl.querySelector(".product-tile-remove");
        if (removeBtn) {
            removeBtn.onclick = function (ev) {
                ev.stopPropagation();
                if (typeof onRemove === "function") onRemove(pid);
            };
        }
    }

    window.productIconHtml = productIconHtml;
    window.mountProductIcon = mountProductIcon;
    window.productQtyBadgeHtml = productQtyBadgeHtml;
    window.productTileRemoveHtml = productTileRemoveHtml;
    window.productTileHtml = productTileHtml;
    window.bindProductTile = bindProductTile;
    window.resolveProductIconUrl = resolveIconUrl;
    loadStandardEmojiMap();
})();
