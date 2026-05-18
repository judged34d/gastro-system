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

    window.productIconHtml = productIconHtml;
    window.resolveProductIconUrl = resolveIconUrl;
})();
