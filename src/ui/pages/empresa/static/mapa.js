    (() => {
        const dataUrl = window.DATA_URL;
        let data = null;

        function loadStyleOnce(id, href) {
            if (document.getElementById(id)) return;
            const link = document.createElement('link');
            link.id = id;
            link.rel = 'stylesheet';
            link.href = href;
            document.head.appendChild(link);
        }

        function loadScriptOnce(id, src, globalName) {
            if (globalName && window[globalName]) return Promise.resolve();
            const existing = document.getElementById(id);
            if (existing) {
                return new Promise((resolve, reject) => {
                    existing.addEventListener('load', resolve, { once: true });
                    existing.addEventListener('error', reject, { once: true });
                    if (globalName && window[globalName]) resolve();
                });
            }
            return new Promise((resolve, reject) => {
                const script = document.createElement('script');
                script.id = id;
                script.src = src;
                script.onload = resolve;
                script.onerror = reject;
                document.head.appendChild(script);
            });
        }

        async function ensureMapAssets() {
            loadStyleOnce('leaflet-css', 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css');
            await loadScriptOnce('leaflet-js', 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js', 'L');
            await loadScriptOnce('chart-js', 'https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js', 'Chart');
        }

        async function init(attempt = 0) {
            const container = document.getElementById('demo-mapa-rmr');
            const selectedName = document.querySelector('.rs-selected-name');
            const totalInstallations = document.querySelector('.rs-total-installations');
            const totalPower = document.querySelector('.rs-total-power');
            const totalModules = document.querySelector('.rs-total-modules');
            const listHelper = document.querySelector('.rs-list-helper');
            const pageStatus = document.querySelector('.rs-page-status');
            const prevPageButton = document.querySelector('.rs-prev-page');
            const nextPageButton = document.querySelector('.rs-next-page');
            const installationsBody = document.querySelector('.rs-installations-body');
            const filterClasse = document.querySelector('.rs-filter-classe');
            const filterTipo = document.querySelector('.rs-filter-tipo');
            const filterPorte = document.querySelector('.rs-filter-porte');
            const filterBairro = document.querySelector('.rs-filter-bairro');
            const filterFabMod = document.querySelector('.rs-filter-fab-mod');
            const filterFabInv = document.querySelector('.rs-filter-fab-inv');
            const filterModalidade = document.querySelector('.rs-filter-modalidade');
            const chartTitle = document.querySelector('.rs-chart-title');
            const chartSeriesModalidade = document.getElementById('chart-series-modalidade');
            const chartModulos = document.getElementById('chart-modulos');
            const chartInversores = document.getElementById('chart-inversores');
            const chartTipo = document.getElementById('chart-tipo');
            const chartClasse = document.getElementById('chart-classe');
            const chartPorte = document.getElementById('chart-porte');
            const chartModalidade = document.getElementById('chart-modalidade');
            let chartSeriesModalidadeInstance = null;
            let chartModulosInstance = null;
            let chartInversoresInstance = null;
            let chartTipoInstance = null;
            let chartClasseInstance = null;
            let chartPorteInstance = null;
            let chartModalidadeInstance = null;
            if (!container) {
                if (attempt < 80) setTimeout(() => init(attempt + 1), 100);
                return;
            }
            if (container.dataset.loaded === 'true') return;
            container.dataset.loaded = 'true';

            try {
                await ensureMapAssets();
            } catch (error) {
                container.textContent = `Nao foi possivel carregar as bibliotecas do mapa (${error.message || 'erro de rede'}).`;
                console.error('Erro ao carregar bibliotecas do mapa:', error);
                return;
            }

            try {
                const response = await fetch(dataUrl, { credentials: 'same-origin' });
                if (!response.ok) throw new Error(`HTTP ${response.status}`);
                data = await response.json();
            } catch (error) {
                container.textContent = `Nao foi possivel carregar os dados do mapa (${error.message}).`;
                console.error('Erro ao carregar mapa:', error);
                return;
            }
            container.textContent = '';
            container.classList.add('rs-map-ready');

            const map = L.map(container, { zoomControl: true, scrollWheelZoom: true });
            L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
                maxZoom: 19,
                attribution: '&copy; OpenStreetMap'
            }).addTo(map);
            map.createPane('leadPane');
            map.getPane('leadPane').style.zIndex = 760;
            map.getPane('leadPane').style.pointerEvents = 'auto';

            map.on('popupopen', function (e) {
                if (e.popup._source && typeof e.popup._source.setZIndexOffset === 'function') e.popup._source.setZIndexOffset(99999);
            });
            map.on('popupclose', function (e) {
                if (e.popup._source && typeof e.popup._source.setZIndexOffset === 'function') e.popup._source.setZIndexOffset(9000);
            });

            const leadStatusColors = {
                'Novo': '#2563eb',
                'Em Contato': '#f97316',
                'Concluído': '#16a34a',
            };
            const leadStatusLabels = {
                'Novo': 'Novo',
                'Em Contato': 'Em andamento',
                'Concluído': 'Concluido',
            };
            const leadLayer = L.layerGroup([], { pane: 'leadPane' }).addTo(map);
            const pjLayer = L.layerGroup([], { pane: 'leadPane' });

            let activeLayer = null;
            let viewMode = 'rmr';
            let selectedMunicipio = null;
            let currentRows = [];
            let currentPage = 1;
            let legendBody = null;
            let unidentifiedBody = null;
            let backControlButton = null;
            let backControlWrapper = null;
            let labelsVisible = false;
            const pageSize = 100;

            const municipioStyle = {
                color: '#1D293B',
                weight: 1.4,
                fillColor: '#F97316',
                fillOpacity: 0.32,
            };
            const selectedMunicipioStyle = {
                color: '#FFFFFF',
                weight: 3.6,
                fillOpacity: 0.82,
            };

            function escapeHtml(value) {
                return String(value ?? '').replace(/[&<>"']/g, (char) => ({
                    '&': '&amp;',
                    '<': '&lt;',
                    '>': '&gt;',
                    '"': '&quot;',
                    "'": '&#39;',
                })[char]);
            }

            function formatCnpj(value) {
                const digits = String(value ?? '').replace(/\\D/g, '');
                if (digits.length !== 14) return escapeHtml(value);
                return `${digits.slice(0, 2)}.${digits.slice(2, 5)}.${digits.slice(5, 8)}/${digits.slice(8, 12)}-${digits.slice(12)}`;
            }

            function formatCep(value) {
                const digits = String(value ?? '').replace(/\\D/g, '');
                if (digits.length !== 8) return escapeHtml(value);
                return `${digits.slice(0, 2)}.${digits.slice(2, 5)}-${digits.slice(5)}`;
            }

            function computeChartData(installations) {
                const yearCounts = {};
                const modCounts = {};
                const invCounts = {};
                const tipoCounts = {};
                const classeCounts = {};
                const porteCounts = {};
                const modalidadeCounts = {};
                const yearModCounts = {};
                const modKeys = new Set();
                installations.forEach((item) => {
                    const y = item.data_conexao_ano;
                    const mod = item.modalidade_habilitado;
                    if (y) yearCounts[y] = (yearCounts[y] || 0) + 1;
                    if (item.fabricante_modulo) modCounts[item.fabricante_modulo] = (modCounts[item.fabricante_modulo] || 0) + 1;
                    if (item.fabricante_inversor) invCounts[item.fabricante_inversor] = (invCounts[item.fabricante_inversor] || 0) + 1;
                    if (item.tipo) tipoCounts[item.tipo] = (tipoCounts[item.tipo] || 0) + 1;
                    if (item.classe) classeCounts[item.classe] = (classeCounts[item.classe] || 0) + 1;
                    if (item.porte) porteCounts[item.porte] = (porteCounts[item.porte] || 0) + 1;
                    if (mod) modalidadeCounts[mod] = (modalidadeCounts[mod] || 0) + 1;
                    if (y && mod) {
                        const key = `${y}::${mod}`;
                        yearModCounts[key] = (yearModCounts[key] || 0) + 1;
                        modKeys.add(mod);
                    }
                });
                const years = Object.keys(yearCounts).sort((a, b) => a - b);
                const sortedMod = Object.entries(modCounts).sort((a, b) => b[1] - a[1]).slice(0, 15);
                const sortedInv = Object.entries(invCounts).sort((a, b) => b[1] - a[1]).slice(0, 15);
                const sortedTipo = Object.entries(tipoCounts).sort((a, b) => b[1] - a[1]);
                const sortedClasse = Object.entries(classeCounts).sort((a, b) => b[1] - a[1]);
                const sortedPorte = Object.entries(porteCounts).sort((a, b) => b[1] - a[1]);
                const sortedModalidade = Object.entries(modalidadeCounts).sort((a, b) => b[1] - a[1]);

                return {
                    topFabricantesModulo: {
                        labels: sortedMod.map((e) => e[0]),
                        values: sortedMod.map((e) => e[1]),
                    },
                    topFabricantesInversor: {
                        labels: sortedInv.map((e) => e[0]),
                        values: sortedInv.map((e) => e[1]),
                    },
                    porTipoPF_PJ: {
                        labels: sortedTipo.map((e) => e[0]),
                        values: sortedTipo.map((e) => e[1]),
                    },
                    porClasse: {
                        labels: sortedClasse.map((e) => e[0]),
                        values: sortedClasse.map((e) => e[1]),
                    },
                    porPorte: {
                        labels: sortedPorte.map((e) => e[0]),
                        values: sortedPorte.map((e) => e[1]),
                    },
                    porModalidade: {
                        labels: sortedModalidade.map((e) => e[0]),
                        values: sortedModalidade.map((e) => e[1]),
                    },
                    seriePorModalidade: {
                        labels: years.map(String),
                        datasets: Array.from(modKeys).sort().map((mod) => ({
                            label: mod,
                            data: years.map((y) => yearModCounts[`${y}::${mod}`] || 0),
                        })),
                    },
                };
            }

            function renderOneChart(instance, canvas, config) {
                if (instance) { instance.destroy(); instance = null; }
                if (!canvas) return null;
                try {
                    const ctx = canvas.getContext('2d');
                    if (!ctx) return null;
                    const total = config.data.datasets[0]?.data.reduce((a, b) => a + b, 0) || 1;
                    const colors = config.data.labels.map((_, i) => {
                        const ratio = total ? config.data.datasets[0].data[i] / total : 0;
                if (ratio > 0.75) return '#DC2626';
                if (ratio > 0.50) return '#F97316';
                if (ratio > 0.25) return '#FACC15';
                return '#22C55E';
                    });
                    config.data.datasets[0].backgroundColor = colors;
                    config.data.datasets[0].borderRadius = 4;
                    return new Chart(ctx, config);
                } catch (e) { return null; }
            }

            function renderPieChart(instance, canvas, config) {
                if (instance) { instance.destroy(); instance = null; }
                if (!canvas) return null;
                try {
                    const ctx = canvas.getContext('2d');
                    if (!ctx) return null;
                    const total = config.data.datasets[0]?.data.reduce((a, b) => a + b, 0) || 0;
                    config.options.plugins.tooltip = {
                        callbacks: {
                            label: (ctx) => {
                                const val = ctx.parsed || 0;
                                const pct = total ? ((val / total) * 100).toFixed(1) : 0;
                                return ` ${ctx.label}: ${val.toLocaleString('pt-BR')} (${pct}%)`;
                            },
                        },
                    };
                    return new Chart(ctx, config);
                } catch (e) { return null; }
            }

            function makeBarConfig(labels, values, label, horizontal) {
                return {
                    type: 'bar',
                    data: { labels, datasets: [{ label, data: values }] },
                    options: {
                        indexAxis: horizontal ? 'y' : undefined,
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: { legend: { display: false } },
                        scales: {
                            x: { beginAtZero: true, grid: horizontal ? { color: '#e2e8f0' } : { display: false }, ticks: { font: { size: horizontal ? 11 : 11 } } },
                            y: horizontal ? { grid: { display: false }, ticks: { font: { size: 10 } } } : { beginAtZero: true, grid: { color: '#e2e8f0' }, ticks: { font: { size: 11 } } },
                        },
                    },
                };
            }

            function makePieConfig(labels, values) {
                const palette = ['#F97316','#3B82F6','#22C55E','#FACC15','#DC2626','#8B5CF6','#06B6D4','#EC4899','#14B8A6','#EAB308','#64748B','#F472B6'];
                const colors = labels.map((_, i) => palette[i % palette.length]);
                const total = values.reduce((a, b) => a + b, 0) || 1;
                const legendLabels = labels.map((label, i) => {
                    const pct = ((values[i] / total) * 100).toFixed(1);
                    return `${label} (${pct}%)`;
                });
                return {
                    type: 'pie',
                    data: { labels: legendLabels, datasets: [{ data: values, backgroundColor: colors, borderWidth: 0 }] },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: {
                            legend: { position: 'bottom', labels: { boxWidth: 14, padding: 10, font: { size: 12 } } },
                        },
                    },
                };
            }

            function renderStackedBar(instance, canvas, config) {
                if (instance) { instance.destroy(); instance = null; }
                if (!canvas) return null;
                try {
                    const ctx = canvas.getContext('2d');
                    if (!ctx) return null;
                    return new Chart(ctx, config);
                } catch (e) { return null; }
            }

            function renderCharts(municipioName) {
                let c;
                if (municipioName) {
                    const rows = data.instalacoesPorMunicipio[municipioName] || [];
                    const filtered = rows.filter(passFilters);
                    c = computeChartData(filtered);
                    if (chartTitle) chartTitle.textContent = 'Graficos - ' + municipioName;
                } else {
                    c = data.charts || {};
                    if (chartTitle) chartTitle.textContent = 'Graficos - RMR';
                }
                const sm = c.seriePorModalidade;
                if (sm && sm.labels && sm.datasets) {
                    const palette = ['#F97316','#3B82F6','#22C55E','#FACC15','#DC2626','#8B5CF6','#06B6D4','#EC4899','#14B8A6','#EAB308'];
                    sm.datasets.forEach((ds, i) => {
                        ds.backgroundColor = palette[i % palette.length];
                        ds.borderWidth = 0;
                    });
                    chartSeriesModalidadeInstance = renderStackedBar(chartSeriesModalidadeInstance, chartSeriesModalidade, {
                        type: 'bar',
                        data: { labels: sm.labels, datasets: sm.datasets },
                        options: {
                            responsive: true,
                            maintainAspectRatio: false,
                            scales: { x: { stacked: true }, y: { stacked: true, beginAtZero: true } },
                            plugins: { legend: { position: 'bottom', labels: { boxWidth: 12, padding: 8, font: { size: 10 } } } },
                        },
                    });
                }
                chartModulosInstance = renderOneChart(chartModulosInstance, chartModulos, makeBarConfig(
                    c.topFabricantesModulo?.labels || [], c.topFabricantesModulo?.values || [], 'Instalacoes', true
                ));
                chartInversoresInstance = renderOneChart(chartInversoresInstance, chartInversores, makeBarConfig(
                    c.topFabricantesInversor?.labels || [], c.topFabricantesInversor?.values || [], 'Instalacoes', true
                ));
                chartClasseInstance = renderPieChart(chartClasseInstance, chartClasse, makePieConfig(
                    c.porClasse?.labels || [], c.porClasse?.values || []
                ));
                chartTipoInstance = renderPieChart(chartTipoInstance, chartTipo, makePieConfig(
                    c.porTipoPF_PJ?.labels || [], c.porTipoPF_PJ?.values || []
                ));
                chartPorteInstance = renderPieChart(chartPorteInstance, chartPorte, makePieConfig(
                    c.porPorte?.labels || [], c.porPorte?.values || []
                ));
                chartModalidadeInstance = renderPieChart(chartModalidadeInstance, chartModalidade, makePieConfig(
                    c.porModalidade?.labels || [], c.porModalidade?.values || []
                ));
            }

            function setupFilter(select, values) {
                select.innerHTML = '<option value="">Todos</option>' + values
                    .filter(Boolean)
                    .sort((a, b) => a.localeCompare(b, 'pt-BR'))
                    .map((value) => `<option value="${escapeHtml(value)}">${escapeHtml(value)}</option>`)
                    .join('');
            }

            const allRows = Object.values(data.instalacoesPorMunicipio).flat();

            const pjByCnpj = new Map();
            (data.pjs || []).forEach((pj) => {
                if (pj.cnpj) pjByCnpj.set(pj.cnpj, pj);
            });
            setupFilter(filterClasse, [...new Set(allRows.map((item) => item.classe))]);
            setupFilter(filterTipo, [...new Set(allRows.map((item) => item.tipo))]);
            setupFilter(filterPorte, [...new Set(allRows.map((item) => item.porte))]);
            setupFilter(filterBairro, []);
            setupFilter(filterFabMod, [...new Set(allRows.map((item) => item.fabricante_modulo).filter(Boolean))]);
            setupFilter(filterFabInv, [...new Set(allRows.map((item) => item.fabricante_inversor).filter(Boolean))]);
            setupFilter(filterModalidade, [...new Set(allRows.map((item) => item.modalidade_habilitado).filter(Boolean))]);

            function updateBairroFilter() {
                const current = filterBairro.value;
                const rows = selectedMunicipio ? (data.instalacoesPorMunicipio[selectedMunicipio.nome] ?? []) : allRows;
                const bairros = [...new Set(rows.flatMap((item) => item.bairros_possiveis ?? [item.bairro]))];
                setupFilter(filterBairro, bairros);
                filterBairro.value = bairros.includes(current) ? current : '';
            }

            function passFilters(item) {
                return (!filterClasse.value || item.classe === filterClasse.value)
                    && (!filterTipo.value || item.tipo === filterTipo.value)
                    && (!filterPorte.value || item.porte === filterPorte.value)
                    && (!filterBairro.value || (item.bairros_possiveis ?? [item.bairro]).includes(filterBairro.value))
                    && (!filterFabMod.value || item.fabricante_modulo === filterFabMod.value)
                    && (!filterFabInv.value || item.fabricante_inversor === filterFabInv.value)
                    && (!filterModalidade.value || item.modalidade_habilitado === filterModalidade.value);
            }

            function filteredRows(rows) {
                return rows.filter(passFilters);
            }

            function sumMetrics(rows) {
                return rows.reduce((acc, item) => {
                    acc.qtd_instalacoes += 1;
                    acc.potencia_kw += Number(item.potencia_kw || 0);
                    acc.qtd_modulos += Number(item.qtd_modulos || 0);
                    return acc;
                }, { qtd_instalacoes: 0, potencia_kw: 0, qtd_modulos: 0 });
            }

            function rowsForMunicipio(nomeMunicipio) {
                return filteredRows(data.instalacoesPorMunicipio[nomeMunicipio] ?? []);
            }

            function metricasMunicipio(nomeMunicipio) {
                return sumMetrics(rowsForMunicipio(nomeMunicipio));
            }

            function metricasBairro(nomeMunicipio, nomeBairro) {
                const rows = (data.instalacoesPorMunicipio[nomeMunicipio] ?? []).filter((item) => {
                    return (!filterClasse.value || item.classe === filterClasse.value)
                        && (!filterTipo.value || item.tipo === filterTipo.value)
                        && (!filterPorte.value || item.porte === filterPorte.value);
                });
                return rows.reduce((acc, item) => {
                    const bairros = item.bairros_possiveis ?? [item.bairro];
                    if (!bairros.includes(nomeBairro)) return acc;
                    const peso = 1 / bairros.length;
                    acc.qtd_instalacoes += peso;
                    acc.potencia_kw += Number(item.potencia_kw || 0) * peso;
                    acc.qtd_modulos += Number(item.qtd_modulos || 0) * peso;
                    return acc;
                }, { qtd_instalacoes: 0, potencia_kw: 0, qtd_modulos: 0 });
            }

            function metricValue(properties) {
                if (properties.tipo === 'municipio') return metricasMunicipio(properties.nome).qtd_instalacoes;
                return Number(properties.metricas?.qtd_instalacoes ?? 0);
            }

            function heatColor(value, maxValue) {
                if (!maxValue || value <= 0) return '#E0F2FE';
                const ratio = Math.min(value / maxValue, 1);
                if (ratio > 0.75) return '#DC2626';
                if (ratio > 0.50) return '#F97316';
                if (ratio > 0.25) return '#FACC15';
                return '#22C55E';
            }

            function municipioMax() {
                return Math.max(...data.municipios.features.map((feature) => metricasMunicipio(feature.properties.nome).qtd_instalacoes), 0);
            }

            function municipioHeatStyle(feature) {
                const value = metricValue(feature.properties);
                const maxValue = municipioMax();
                return {
                    color: '#1D293B',
                    weight: 1.4,
                    fillColor: heatColor(value, maxValue),
                    fillOpacity: 0.72,
                };
            }

            function updateLegend(maxValue, title = 'Instalacoes') {
                if (!legendBody) return;
                const ranges = [
                    { color: '#22C55E', label: `Ate ${Math.round(maxValue * 0.25).toLocaleString('pt-BR')}` },
                    { color: '#FACC15', label: `${Math.round(maxValue * 0.25).toLocaleString('pt-BR')} a ${Math.round(maxValue * 0.50).toLocaleString('pt-BR')}` },
                    { color: '#F97316', label: `${Math.round(maxValue * 0.50).toLocaleString('pt-BR')} a ${Math.round(maxValue * 0.75).toLocaleString('pt-BR')}` },
                    { color: '#DC2626', label: `Acima de ${Math.round(maxValue * 0.75).toLocaleString('pt-BR')}` },
                ];
                legendBody.innerHTML = `
                    <div class="rs-map-legend-title">${title}</div>
                    ${ranges.map((range) => `
                        <div class="rs-map-legend-row">
                            <span class="rs-map-legend-swatch" style="background:${range.color}"></span>
                            <span>${range.label}</span>
                        </div>
                    `).join('')}
                `;
            }

            function addLegend() {
                const legend = L.control({ position: 'bottomright' });
                legend.onAdd = () => {
                    const div = L.DomUtil.create('div', 'rs-map-legend');
                    legendBody = div;
                    L.DomEvent.disableClickPropagation(div);
                    return div;
                };
                legend.addTo(map);
                updateLegend(Number(data.maximos?.qtd_instalacoes ?? 0));
            }

            function updateUnidentified(codigoMunicipio = null) {
                if (!unidentifiedBody) return;
                if (!codigoMunicipio) {
                    unidentifiedBody.style.display = 'none';
                    return;
                }
                const municipio = data.municipios.features.find((feature) => feature.properties.codigo === codigoMunicipio)?.properties;
                const rows = municipio ? rowsForMunicipio(municipio.nome).filter((item) => (item.bairros_possiveis ?? []).includes('Nao identificado')) : [];
                const metrics = sumMetrics(rows);
                if (!metrics || !Number(metrics.qtd_instalacoes ?? 0)) {
                    unidentifiedBody.style.display = 'none';
                    return;
                }
                unidentifiedBody.style.display = 'block';
                unidentifiedBody.innerHTML = `
                    <div class="rs-map-unidentified-title">Nao identificado</div>
                    <div class="rs-map-unidentified-value">${Number(metrics.qtd_instalacoes ?? 0).toLocaleString('pt-BR', { maximumFractionDigits: 2 })}</div>
                    <div class="rs-map-unidentified-meta">${Number(metrics.potencia_kw ?? 0).toLocaleString('pt-BR', { maximumFractionDigits: 2 })} kW</div>
                    <div class="rs-map-unidentified-meta">${Number(metrics.qtd_modulos ?? 0).toLocaleString('pt-BR', { maximumFractionDigits: 2 })} modulos</div>
                `;
            }

            function addUnidentifiedBox() {
                const control = L.control({ position: 'topright' });
                control.onAdd = () => {
                    const div = L.DomUtil.create('div', 'rs-map-unidentified');
                    div.style.display = 'none';
                    unidentifiedBody = div;
                    L.DomEvent.disableClickPropagation(div);
                    return div;
                };
                control.addTo(map);
            }

            function renderLeadPins() {
                leadLayer.clearLayers();
                (data.leads || []).forEach((lead) => {
                    const lat = Number(lead.lat);
                    const lng = Number(lead.lng);
                    if (!Number.isFinite(lat) || !Number.isFinite(lng)) return;
                    const color = leadStatusColors[lead.status] || '#64748b';
                    const icon = L.divIcon({
                        className: '',
                        html: `<div class="rs-lead-pin" style="--lead-color:${color}"></div>`,
                        iconSize: [30, 42],
                        iconAnchor: [15, 39],
                        popupAnchor: [0, -38],
                    });
                    const marker = L.marker([lat, lng], { icon, pane: 'leadPane', zIndexOffset: 10000 });
                    marker.bindPopup(`
                        <strong>Lead #${escapeHtml(lead.id)}</strong><br>
                        ${escapeHtml(lead.nome)}<br>
                        <span>Status: ${escapeHtml(lead.status_label || leadStatusLabels[lead.status] || lead.status)}</span><br>
                        ${lead.telefone ? `<span>Contato: ${escapeHtml(lead.telefone)}</span><br>` : ''}
                        ${lead.endereco ? `<span>${escapeHtml(lead.endereco)}</span><br>` : ''}
                        ${lead.cep ? `<span>CEP: ${escapeHtml(lead.cep)}</span><br>` : ''}
                        ${lead.aproximado ? '<em>Localizacao aproximada</em><br>' : ''}
                        ${lead.descricao ? `<small>${escapeHtml(lead.descricao)}</small>` : ''}
                    `);
                    marker.addTo(leadLayer);
                });
            }

            const capturedCnpjs = new Set();

            function captureBtnHtml(cnpj, nome, endereco, telefone, captured) {
                if (!window.CAPTURE_LEAD_URL || captured) return '';
                const data = JSON.stringify({ cnpj: String(cnpj || ''), nome: String(nome || ''), endereco: String(endereco || ''), telefone: String(telefone || '') });
                return `<button class="rs-capture-btn" data-capture='${data.replace(/'/g, '&#39;')}' style="background:#7c3aed;color:white;border:none;border-radius:8px;padding:6px 14px;font-size:12px;cursor:pointer;width:100%">Capturar lead</button>`;
            }

            document.addEventListener('click', async function (e) {
                const btn = e.target.closest('.rs-capture-btn');
                if (!btn) return;
                e.preventDefault();
                try {
                    const data = JSON.parse(btn.dataset.capture);
                    console.log('capturar-lead data:', data.cnpj);
                    btn.disabled = true;
                    btn.textContent = 'Capturando...';
                    const r = await fetch(window.CAPTURE_LEAD_URL, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        credentials: 'same-origin',
                        body: JSON.stringify(data),
                    });
                    console.log('capturar-lead response:', r.status);
                    const resp = await r.json();
                    if (r.status === 409) {
                        capturedCnpjs.add(data.cnpj);
                        btn.textContent = 'Ja capturado';
                        btn.style.background = '#16a34a';
                    } else if (r.ok) {
                        capturedCnpjs.add(data.cnpj);
                        btn.textContent = 'Capturado!';
                        btn.style.background = '#16a34a';
                    } else {
                        throw new Error(`HTTP ${r.status}: ${resp.error || resp.detail || 'Erro'}`);
                    }
                    renderPjPins();
                    renderTablePage(currentPage);
                } catch (e) {
                    console.error('Erro ao capturar lead:', e.message, e);
                    btn.disabled = false;
                    btn.textContent = e.message || 'Erro';
                    btn.style.background = '#dc2626';
                }
            });

            function renderPjPins() {
                pjLayer.clearLayers();
                const pjs = (data.pjs || []).filter((pj) => {
                    if (!(viewMode === 'municipio' && selectedMunicipio)) return true;
                    return String(pj.municipio || '').toUpperCase() === String(selectedMunicipio.nome || '').toUpperCase();
                });
                pjs.forEach((pj) => {
                    const lat = Number(pj.lat);
                    const lng = Number(pj.lng);
                    if (!Number.isFinite(lat) || !Number.isFinite(lng)) return;
                    const captured = capturedCnpjs.has(pj.cnpj);
                    const pinColor = captured ? '#16a34a' : '#f97316';
                    const hasContact = pj.telefone1 || pj.telefone2 || pj.email;
                    const icon = L.divIcon({
                        className: '',
                        html: `<div class="rs-lead-pin" style="--lead-color:${pinColor}">${hasContact ? '<div class="rs-pin-badge">\u{1F4DE}</div>' : ''}</div>`,
                        iconSize: [30, 42],
                        iconAnchor: [15, 39],
                        popupAnchor: [0, -38],
                    });
                    const marker = L.marker([lat, lng], {
                        icon,
                        pane: 'leadPane',
                        zIndexOffset: 9000,
                    });
                    const logradouro = pj.logradouro
                        ? `${escapeHtml(String(pj.logradouro).toUpperCase())}${pj.numero ? ', ' + escapeHtml(String(pj.numero).toUpperCase()) : ''}`
                        : '-';
                    const cidadeUf = pj.municipio
                        ? `${escapeHtml(String(pj.municipio).toUpperCase())}${pj.uf ? '/' + escapeHtml(String(pj.uf).toUpperCase()) : ''}`
                        : '-';
                    const telefone = pj.telefone1
                        ? `${escapeHtml(pj.telefone1)}${pj.telefone2 ? ' / ' + escapeHtml(pj.telefone2) : ''}`
                        : '-';
                    const modulosPotencia = `${Number(pj.qtd_modulos || 0).toLocaleString('pt-BR')} mod / ${Number(pj.potencia_kw || 0).toLocaleString('pt-BR')} kW`;
                    const enderecoCompleto = `${logradouro}, ${cidadeUf}`;
                    const btnHtml = captureBtnHtml(pj.cnpj, pj.titular, enderecoCompleto, pj.telefone1 || '', captured);
                    marker.bindPopup(`
                        <div style="font-size:13px;line-height:1.6">
                        <strong>${escapeHtml(pj.codigo)}</strong><br>
                        ${captured ? '<span style="color:#16a34a;font-weight:bold">Ja capturado</span><br>' : ''}
                        <div style="border-top:1px solid #e2e8f0;margin:7px 0"></div>
                        CNPJ: ${formatCnpj(pj.cnpj)}<br>
                        ${escapeHtml(pj.titular)}<br>
                        ${logradouro}, ${cidadeUf}<br>
                        CEP: ${pj.cep ? formatCep(pj.cep) : '-'}<br>
                        <div style="border-top:1px solid #e2e8f0;margin:7px 0"></div>
                        <strong>Instalação de ${pj.data_instalacao ? escapeHtml(pj.data_instalacao) : '-'}</strong><br>
                        ${modulosPotencia}
                        <div style="border-top:1px solid #e2e8f0;margin:7px 0"></div>
                        <strong>Contato</strong><br>
                        Tel.: ${telefone}<br>
                        E-mail: ${pj.email ? escapeHtml(pj.email) : '-'}
                        ${btnHtml ? '<div style="border-top:1px solid #e2e8f0;margin:7px 0"></div>' + btnHtml : ''}
                        </div>
                    `, { autoPan: true, keepInView: true, closeButton: true, maxWidth: 380, className: 'rs-pj-popup' });
                    marker.addTo(pjLayer);
                });
            }

            let pjVisible = false;

            function addLeadLegend() {
                if (!(data.leads || []).length) return;
                const legend = L.control({ position: 'bottomleft' });
                legend.onAdd = () => {
                    const div = L.DomUtil.create('div', 'rs-lead-legend');
                    L.DomEvent.disableClickPropagation(div);
                    div.innerHTML = `
                        <div class="rs-lead-legend-title">Leads</div>
                        ${Object.entries(leadStatusColors).map(([status, color]) => `
                            <div class="rs-lead-legend-row">
                                <span class="rs-lead-legend-dot" style="background:${color}"></span>
                                <span>${leadStatusLabels[status] || status}</span>
                            </div>
                        `).join('')}
                    `;
                    return div;
                };
                legend.addTo(map);
            }

            function updateLabelToggle(button) {
                container.classList.toggle('rs-hide-labels', !labelsVisible);
                if (button) button.textContent = labelsVisible ? 'Ocultar nomes' : 'Mostrar nomes';
            }

            function addLabelToggle() {
                const control = L.control({ position: 'topleft' });
                control.onAdd = () => {
                    const container = L.DomUtil.create('div', 'rs-label-toggle-group');
                    L.DomEvent.disableClickPropagation(container);

                    const labelBtn = L.DomUtil.create('button', 'rs-label-toggle');
                    labelBtn.type = 'button';
                    L.DomEvent.on(labelBtn, 'click', (event) => {
                        L.DomEvent.preventDefault(event);
                        labelsVisible = !labelsVisible;
                        updateLabelToggle(labelBtn);
                    });
                    updateLabelToggle(labelBtn);
                    container.appendChild(labelBtn);

                    if ((data.pjs || []).length) {
                        const pjBtn = L.DomUtil.create('button', 'rs-label-toggle');
                        pjBtn.type = 'button';
                        L.DomEvent.on(pjBtn, 'click', (event) => {
                            L.DomEvent.preventDefault(event);
                            pjVisible = !pjVisible;
                            if (pjVisible) {
                                pjLayer.addTo(map);
                            } else {
                                map.removeLayer(pjLayer);
                            }
                            pjBtn.textContent = pjVisible ? 'Ocultar empresas' : 'Mostrar empresas';
                        });
                        pjBtn.textContent = 'Mostrar empresas';
                        container.appendChild(pjBtn);
                    }

                    return container;
                };
                control.addTo(map);
            }

            function updateBackControl() {
                if (!backControlButton) return;
                backControlButton.style.display = viewMode === 'municipio' ? 'block' : 'none';
                if (backControlWrapper) backControlWrapper.style.display = viewMode === 'municipio' ? 'block' : 'none';
            }

            function addBackControl() {
                const control = L.control({ position: 'topleft' });
                control.onAdd = () => {
                    const wrapper = L.DomUtil.create('div', 'rs-map-back-wrapper');
                    const button = L.DomUtil.create('button', 'rs-map-back-control');
                    button.type = 'button';
                    button.textContent = 'Voltar';
                    backControlButton = button;
                    backControlWrapper = wrapper;
                    L.DomEvent.disableClickPropagation(wrapper);
                    L.DomEvent.on(button, 'click', (event) => {
                        L.DomEvent.preventDefault(event);
                        if (viewMode === 'municipio') resetToRmr();
                    });
                    wrapper.appendChild(button);
                    updateBackControl();
                    return wrapper;
                };
                control.addTo(map);
            }

            function addLabels(layer, labelAccessor) {
                layer.eachLayer((item) => {
                    const label = labelAccessor(item.feature.properties);
                    item.bindTooltip(label, {
                        permanent: true,
                        direction: 'center',
                        className: 'rs-map-label',
                    });
                });
            }

            function setLayer(layer) {
                if (activeLayer) activeLayer.removeFrom(map);
                activeLayer = layer.addTo(map);
                map.fitBounds(activeLayer.getBounds(), { padding: [24, 24] });
            }

            function rowsForCurrentScope() {
                if (viewMode === 'municipio' && selectedMunicipio) return rowsForMunicipio(selectedMunicipio.nome);
                return filteredRows(allRows).sort((a, b) => b.potencia_kw - a.potencia_kw);
            }

            function metricsForCurrentScope() {
                return sumMetrics(rowsForCurrentScope());
            }

            function scopeLabel() {
                if (viewMode === 'municipio' && selectedMunicipio) return selectedMunicipio.nome;
                return 'RMR';
            }

            function updateSummary() {
                const metrics = metricsForCurrentScope();
                selectedName.textContent = scopeLabel();
                totalInstallations.textContent = Number(metrics.qtd_instalacoes ?? 0).toLocaleString('pt-BR');
                totalPower.textContent = `${Number(metrics.potencia_kw ?? 0).toLocaleString('pt-BR', { maximumFractionDigits: 2 })} kW`;
                totalModules.textContent = Number(metrics.qtd_modulos ?? 0).toLocaleString('pt-BR');
            }

            function renderTablePage(page = currentPage) {
                const totalPages = Math.max(Math.ceil(currentRows.length / pageSize), 1);
                currentPage = Math.min(Math.max(page, 1), totalPages);
                const start = (currentPage - 1) * pageSize;
                const visible = currentRows.slice(start, start + pageSize);

                pageStatus.textContent = `${currentPage} / ${totalPages}`;
                prevPageButton.disabled = currentPage <= 1;
                nextPageButton.disabled = currentPage >= totalPages;
                installationsBody.innerHTML = visible.map((item) => {
                    const isPj = window.CAPTURE_LEAD_URL && item.tipo === 'PJ' && item.cpf_cnpj;
                    const captured = capturedCnpjs.has(item.cpf_cnpj);
                    const plusBtn = isPj && !captured
                        ? `<button class="rs-capture-btn" data-capture='${JSON.stringify({ cnpj: String(item.cpf_cnpj), nome: String(item.titular || ''), endereco: String((item.municipio || '') + '/' + (item.uf || '')), telefone: '' }).replace(/'/g, '&#39;')}' style="background:#7c3aed;color:white;border:none;border-radius:4px;padding:0 6px;font-size:16px;cursor:pointer;line-height:24px" title="Capturar lead">+</button>`
                        : (isPj ? `<span style="display:inline-block;background:#16a34a;color:white;border-radius:4px;padding:0 6px;font-size:14px;line-height:24px">\u2713</span>` : '');
                    const cnpjClean = (item.cpf_cnpj || '').replace(/\D/g, '');
                    const contatoPj = cnpjClean.length === 14 ? pjByCnpj.get(cnpjClean) : null;
                    const telefone = contatoPj ? (contatoPj.telefone1 || contatoPj.telefone2 || '') : '';
                    const email = contatoPj ? (contatoPj.email || '') : '';
                    return `
                    <tr>
                        <td>${plusBtn}</td>
                        <td>${escapeHtml(item.codigo)}</td>
                        <td>${escapeHtml(item.cpf_cnpj)}</td>
                        <td>${escapeHtml(item.titular)}</td>
                        <td>${escapeHtml(item.municipio)}</td>
                        <td>${escapeHtml((item.bairros_possiveis ?? [item.bairro]).join(', '))}</td>
                        <td>${telefone ? escapeHtml(telefone) : '-'}</td>
                        <td>${email ? escapeHtml(email) : '-'}</td>
                        <td>${escapeHtml(item.classe)}</td>
                        <td>${escapeHtml(item.tipo)}</td>
                        <td>${escapeHtml(item.porte)}</td>
                        <td>${escapeHtml(item.modalidade_habilitado)}</td>
                        <td>${escapeHtml(item.data_conexao)}</td>
                        <td>${Number(item.potencia_kw).toLocaleString('pt-BR', { maximumFractionDigits: 2 })}</td>
                        <td>${Number(item.qtd_modulos).toLocaleString('pt-BR')}</td>
                        <td>${escapeHtml(item.fabricante_modulo)}</td>
                        <td>${escapeHtml(item.fabricante_inversor)}</td>
                        <td>${Number(item.qtd_uc_credito).toLocaleString('pt-BR')}</td>
                        <td>${escapeHtml(item.cep)}</td>
                    </tr>`;
                }).join('') || '<tr><td colspan="19">Nenhuma instalacao encontrada.</td></tr>';
            }

            function renderInstallations(page = 1) {
                currentRows = rowsForCurrentScope();
                const scope = scopeLabel();
                listHelper.textContent = `${scope}: ${currentRows.length.toLocaleString('pt-BR')} instalacoes encontradas. Ordenacao por maior potencia.`;
                renderTablePage(page);
            }

            function renderBairros(codigoMunicipio, nomeMunicipio) {
                const bairros = data.bairrosPorMunicipio[codigoMunicipio];
                const metricasPorBairro = Object.fromEntries(
                    bairros.features.map((feature) => [feature.properties.nome, metricasBairro(nomeMunicipio, feature.properties.nome)])
                );
                const maxBairro = Math.max(
                    ...Object.values(metricasPorBairro).map((metrics) => metrics.qtd_instalacoes),
                    0,
                );
                const estiloBairro = (feature) => {
                    const value = Number(metricasPorBairro[feature.properties.nome]?.qtd_instalacoes ?? 0);
                    return {
                        color: '#1D293B',
                        weight: 1.1,
                        fillColor: heatColor(value, maxBairro),
                        fillOpacity: 0.72,
                    };
                };
                const layer = L.geoJSON(bairros, {
                    style: estiloBairro,
                    onEachFeature: (feature, item) => {
                        const metrics = metricasPorBairro[feature.properties.nome] ?? { qtd_instalacoes: 0, potencia_kw: 0, qtd_modulos: 0 };
                        item.on('mouseover', () => {
                            item.setStyle(selectedMunicipioStyle);
                            item.bringToFront();
                        });
                        item.on('mouseout', () => item.setStyle(estiloBairro(feature)));
                        item.bindPopup(`
                            <strong>${feature.properties.nome}</strong><br>
                            ${Number(metrics.qtd_instalacoes ?? 0).toLocaleString('pt-BR', { maximumFractionDigits: 2 })} instalacoes estimadas<br>
                            ${Number(metrics.potencia_kw ?? 0).toLocaleString('pt-BR', { maximumFractionDigits: 2 })} kW<br>
                            ${Number(metrics.qtd_modulos ?? 0).toLocaleString('pt-BR', { maximumFractionDigits: 2 })} modulos
                        `);
                    },
                });
                addLabels(layer, (properties) => properties.nome);
                setLayer(layer);
                updateLegend(maxBairro, `Bairros de ${nomeMunicipio}`);
                updateUnidentified(codigoMunicipio);
                updateBackControl();
            }

            function renderMunicipios() {
                const layer = L.geoJSON(data.municipios, {
                    style: municipioHeatStyle,
                    onEachFeature: (feature, item) => {
                        item.on('mouseover', () => {
                            item.setStyle(selectedMunicipioStyle);
                            item.bringToFront();
                        });
                        item.on('mouseout', () => item.setStyle(municipioHeatStyle(feature)));
                        item.on('click', () => {
                            viewMode = 'municipio';
                            selectedMunicipio = feature.properties;
                            updateBairroFilter();
                            updateSummary();
                            renderInstallations(1);
                            renderBairros(feature.properties.codigo, feature.properties.nome);
                            renderPjPins();
                            renderCharts(feature.properties.nome);
                        });
                    },
                });
                addLabels(layer, (properties) => properties.nome);
                setLayer(layer);
                updateSummary();
                updateLegend(municipioMax(), 'Instalacoes');
                updateUnidentified(null);
                updateBackControl();
            }

            function resetToRmr() {
                viewMode = 'rmr';
                selectedMunicipio = null;
                filterBairro.value = '';
                filterFabMod.value = '';
                filterFabInv.value = '';
                updateBairroFilter();
                renderMunicipios();
                renderPjPins();
                renderCharts();
                renderInstallations(1);
            }
            prevPageButton?.addEventListener('click', () => renderTablePage(currentPage - 1));
            nextPageButton?.addEventListener('click', () => renderTablePage(currentPage + 1));
            [filterClasse, filterTipo, filterPorte, filterBairro, filterFabMod, filterFabInv, filterModalidade].forEach((select) => select.addEventListener('change', () => {
                if (select !== filterBairro && select !== filterFabMod && select !== filterFabInv && select !== filterModalidade) updateBairroFilter();
                if (viewMode === 'municipio' && selectedMunicipio) renderBairros(selectedMunicipio.codigo, selectedMunicipio.nome);
                else renderMunicipios();
                renderPjPins();
                updateSummary();
                renderInstallations(1);
                if (viewMode === 'municipio' && selectedMunicipio) renderCharts(selectedMunicipio.nome);
                else renderCharts();
            }));
            addLegend();
            addUnidentifiedBox();
            addBackControl();
            addLabelToggle();
            addLeadLegend();
            renderLeadPins();
            renderPjPins();
            viewMode = 'rmr';
            updateBairroFilter();
            renderMunicipios();
            renderCharts();
            updateSummary();
            renderInstallations(1);
            setTimeout(() => map.invalidateSize(), 100);
        }

        init();
    })();