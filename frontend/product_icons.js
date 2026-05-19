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
        if (/^https?:\/\//i.test(url)) return url;
        const base = apiBase().replace(/\/$/, "");
        return base + (url.startsWith("/") ? url : "/" + url);
    }

    function productIconHtml(product, className) {
        const cls = className || "product-icon";
        if (product && product.icon_emoji) {
            return '<span class="' + cls + ' product-icon-emoji" aria-hidden="true">' + product.icon_emoji + "</span>";
        }
        if (product && product.icon_url) {
            const src = resolveIconUrl(product.icon_url);
            const alt = (product.name || "Artikel").replace(/"/g, "&quot;");
            return '<img class="' + cls + ' product-icon-img" src="' + src + '" alt="' + alt + '">';
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
        const iconHtml = productIconHtml(product);
        return (
            productQtyBadgeHtml(qty) +
            productTileRemoveHtml(product.id, qty) +
            iconHtml +
            "<b>" +
            (product.name || "") +
            "</b><br>" +
            priceText
        );
    }

    function bindProductTile(tileEl, productId, onAdd, onRemove) {
        if (!tileEl) return;
        const pid = Number(productId);
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
    window.productQtyBadgeHtml = productQtyBadgeHtml;
    window.productTileRemoveHtml = productTileRemoveHtml;
    window.productTileHtml = productTileHtml;
    window.bindProductTile = bindProductTile;
    window.resolveProductIconUrl = resolveIconUrl;
})();
