// admin/auth.js
(function () {
    "use strict";

    /**
     * ============================
     * 🔐 CONTROLE DE AUTENTICAÇÃO
     * ============================
     */
    const isLogged = sessionStorage.getItem('admin_logged');

    if (!isLogged && !window.location.pathname.includes('login.html')) {
        const redirect = window.location.pathname.includes('/forms/')
            ? '../login.html'
            : 'login.html';

        window.location.href = redirect;
        return;
    }

    /**
     * ============================
     * 🌐 RESOLUÇÃO DE URL DA API
     * ============================
     */
    function apiUrl(path) {
        const normalized = path.startsWith('/') ? path : `/${path}`;
        const savedBase = sessionStorage.getItem('admin_api_base');

        if (savedBase) return `${savedBase}${normalized}`;

        // Caso esteja rodando local sem servidor (file://)
        if (window.location.protocol === 'file:') {
            return `http://127.0.0.1:5000${normalized}`;
        }

        // Caso esteja usando Live Server (porta diferente)
        if (
            (window.location.hostname === 'localhost' ||
                window.location.hostname === '127.0.0.1') &&
            window.location.port &&
            window.location.port !== '5000'
        ) {
            return `http://127.0.0.1:5000${normalized}`;
        }

        return `${window.location.origin}${normalized}`;
    }

    window.apiUrl = apiUrl;

    /**
     * ============================
     * 🚪 LOGOUT
     * ============================
     */
    window.logout = function () {
        sessionStorage.removeItem('admin_logged');
        sessionStorage.removeItem('admin_api_base');

        const loginPath = window.location.pathname.includes('/forms/')
            ? '../login.html'
            : 'login.html';

        window.location.href = loginPath;
    };

    /**
     * ============================
     * 📡 CLIENTE DE API (PADRÃO)
     * ============================
     */
    async function apiRequest(path, options = {}) {
        try {
            const response = await fetch(apiUrl(path), {
                headers: {
                    'Content-Type': 'application/json',
                    ...(options.headers || {})
                },
                ...options
            });

            if (!response.ok) {
                throw new Error(`Erro HTTP: ${response.status}`);
            }

            return await response.json();

        } catch (error) {
            console.error('Erro na API:', error);
            throw error;
        }
    }

    /**
     * ============================
     * 📦 ENDPOINTS CENTRALIZADOS
     * ============================
     */
    const API = {
        dashboard: () => apiRequest('/api/dashboard'),
        locais: () => apiRequest('/api/locais'),
        regioes: () => apiRequest('/api/regioes'),
        status: () => apiRequest('/status'),
        rebuild: () => apiRequest('/rebuild', { method: 'POST' }),
        limpar: () => apiRequest('/limpar', { method: 'POST' }),

        delete: (body) => apiRequest('/delete', {
            method: 'POST',
            body: JSON.stringify(body)
        })
    };

    window.API = API;

    /**
     * ============================
     * 📊 INICIALIZAÇÃO DO DASHBOARD
     * ============================
     */
    async function carregarDashboard() {
        try {
            const data = await API.dashboard();

            console.log('Dashboard:', data);

            const el = document.getElementById('resultado');
            if (!el) return;

            el.innerText =
                `📍 Locais: ${data.total_locais} | 🌎 Regiões: ${data.total_regioes} | ⚙️ Status: ${data.status}`;

        } catch (error) {
            console.error('Erro ao carregar dashboard:', error);
        }
    }

    /**
     * ============================
     * 🔄 AUTO START
     * ============================
     */
    document.addEventListener('DOMContentLoaded', () => {
        carregarDashboard();
    });

})();