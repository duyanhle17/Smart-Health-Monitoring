import os

html_content = """<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <title>S.H.M - Trung Tâm Điều Hành Chuyên Sâu</title>
    <!-- THƯ VIỆN BẢN ĐỒ: LEAFLET & LEAFLET-HEAT -->
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <script src="https://unpkg.com/leaflet.heat/dist/leaflet-heat.js"></script>
    <!-- THƯ VIỆN BIỂU ĐỒ: CHART.JS -->
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        :root {
            --bg-color: #0b0f19;
            --panel-bg: #151b2b;
            --text-color: #f1f1f1;
            --color-safe: #00e676;
            --color-warn: #ff9100;
            --color-danger: #ff1744;
            --color-cyan: #00e5ff;
        }

        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            margin: 0; padding: 0;
            background-color: var(--bg-color);
            color: var(--text-color);
            height: 100vh; display: flex; flex-direction: column;
        }

        .header {
            background-color: #06090f; padding: 10px 25px;
            display: flex; justify-content: space-between; align-items: center;
            border-bottom: 2px solid #1f293d;
            box-shadow: 0 4px 6px rgba(0,0,0,0.5);
            z-index: 100;
        }
        .header h1 { margin: 0; font-size: 20px; color: #fff; text-shadow: 0 0 10px #00e5ff; letter-spacing: 1px;}

        /* Bố cục 3 cột: Danh sách trái | Bản đồ giữa | Biểu đồ phải */
        .dashboard { display: flex; flex: 1; overflow: hidden; }

        .sidebar {
            width: 320px; background-color: var(--panel-bg); padding: 15px;
            overflow-y: auto; border-right: 2px solid #1f293d; z-index: 10;
        }

        .worker-card {
            background: #1c2438; border-radius: 10px; padding: 12px; margin-bottom: 15px;
            border-left: 6px solid var(--color-safe); transition: all 0.3s;
            position: relative; overflow: hidden; cursor: pointer;
            box-shadow: 0 4px 10px rgba(0,0,0,0.3);
        }
        .worker-card:hover { transform: scale(1.02); border-color: #00e5ff; }
        .worker-card.active { border: 2px solid #00e5ff; box-shadow: 0 0 15px rgba(0, 229, 255, 0.4); }
        
        .worker-card.danger { border-left-color: var(--color-danger); animation: glow-danger 0.8s infinite alternate; }
        .worker-card.warning { border-left-color: var(--color-warn); }

        @keyframes glow-danger { from { box-shadow: 0 0 5px rgba(255, 23, 68, 0.2); } to { box-shadow: 0 0 25px rgba(255, 23, 68, 0.7); } }

        .worker-header { display: flex; justify-content: space-between; align-items: center; font-weight: bold; font-size: 16px; margin-bottom: 8px; border-bottom: 1px solid #2d3748; padding-bottom: 6px; }
        .worker-status-badge { font-size: 11px; padding: 3px 8px; border-radius: 10px; background: var(--color-safe); color: #000; font-weight:bold;}
        .worker-card.danger .worker-status-badge { background: var(--color-danger); color: #fff; }
        .worker-card.warning .worker-status-badge { background: var(--color-warn); color: #000; }

        .stat-row { display: flex; justify-content: space-between; align-items: center; margin: 6px 0; font-size: 13px; }
        .stat-val { font-weight: bold; font-size: 14px; text-align: right; }
        .stat-val.err { color: var(--color-danger); }

        .map-wrapper { flex: 1; position: relative; background-color: #000; }
        #map-container { width: 100%; height: 100%; outline: 0; background: #000 !important; cursor: crosshair;}
        .leaflet-container { background: #000 !important; }

        /* Cột biểu đồ bên phải */
        .chart-panel {
            width: 450px; background-color: var(--panel-bg); padding: 15px;
            display: flex; flex-direction: column; overflow-y: auto;
            border-left: 2px solid #1f293d; z-index: 10;
        }

        .chart-box {
            background: #0f1524; border: 1px solid #1f293d; border-radius: 8px;
            padding: 10px; margin-bottom: 15px; height: 200px;
            box-shadow: inset 0 0 10px rgba(0,0,0,0.5);
        }
        .chart-title { font-size: 13px; color: #94a3b8; margin: 0 0 5px 0; text-transform: uppercase; letter-spacing: 1px; display: flex; justify-content: space-between;}

        /* Icon Marker */
        .worker-marker { position: relative; }
        .worker-marker .dot { width: 16px; height: 16px; border-radius: 50%; border: 2px solid #fff; position: absolute; top: -8px; left: -8px; z-index: 2;}
        .worker-marker .pulsing { width: 40px; height: 40px; border-radius: 50%; position: absolute; top: -20px; left: -20px; animation: pulse 1.5s infinite; opacity: 0; z-index: 1;}
        @keyframes pulse { 0% { transform: scale(0.4); opacity: 0.8; } 100% { transform: scale(1.5); opacity: 0; } }
        .worker-label { position: absolute; top: 12px; left: -12px; color: white; font-weight: bold; font-size: 11px; background: rgba(0,0,0,0.7); padding: 2px 6px; border-radius: 4px; border: 1px solid #444; white-space: nowrap; z-index: 3;}
    </style>
</head>
<body>
    <div class="header">
        <h1>⛏️ Edge AI: Giám Sát Cảnh Báo Sớm</h1>
        <div id="env-alert" style="font-weight:bold; color:var(--color-safe);">✓ Hệ thống ổn định</div>
    </div>

    <div class="dashboard">
        <!-- Cột trái: Worker List -->
        <div class="sidebar">
            <h3 style="margin-top: 0; border-bottom: 1px solid #2d3748; padding-bottom: 10px; color: #94a3b8; font-size: 14px;">DANH SÁCH NHÂN SỰ</h3>
            <div id="worker-list"><p style="text-align:center; color:#555;">Đang load...</p></div>
        </div>

        <!-- Cột giữa: Bản đồ -->
        <div class="map-wrapper">
            <div id="map-container"></div>
        </div>

        <!-- Cột phải: Biểu đồ thời gian thực -->
        <div class="chart-panel">
            <h3 style="margin-top: 0; color: #00e5ff; font-size: 15px; border-bottom: 1px solid #2d3748; padding-bottom: 10px;">
                📊 PHÂN TÍCH TELEMETRY: <span id="current-worker-name" style="color:#fff;">W1</span>
            </h3>
            
            <div class="chart-box">
                <div class="chart-title"><span>Gia tốc kế (Accel)</span> <span>Đơn vị: G</span></div>
                <canvas id="accChart"></canvas>
            </div>
            
            <div class="chart-box">
                <div class="chart-title"><span>Con quay (Gyro)</span> <span>Đơn vị: °/s</span></div>
                <canvas id="gyroChart"></canvas>
            </div>
            
            <div class="chart-box" style="height: 220px;">
                <div class="chart-title"><span>Nhịp tim & Môi trường Gas</span></div>
                <canvas id="healthChart"></canvas>
            </div>
        </div>
    </div>

    <script>
        let selectedWorkerId = "W1";

        // ==========================================
        // 1. CHART.JS CẤU HÌNH BIỂU ĐỒ
        // ==========================================
        Chart.defaults.color = '#64748b';
        Chart.defaults.font.family = "'Segoe UI', sans-serif";
        
        const commonOptions = {
            responsive: true, maintainAspectRatio: false,
            animation: false, // Tắt animation để vẽ real-time mượt như điện tâm đồ
            elements: { point: { radius: 0 }, line: { tension: 0.3, borderWidth: 2 } },
            scales: {
                x: { display: false }, // Ẩn cột thời gian X cho gọn
                y: { grid: { color: '#1e293b' } }
            },
            plugins: { legend: { position: 'top', labels: { boxWidth: 10, font: {size: 10} } } }
        };

        const ctxAcc = document.getElementById('accChart').getContext('2d');
        const accChart = new Chart(ctxAcc, {
            type: 'line',
            data: { labels: Array(20).fill(''), datasets: [
                { label: 'Ax', borderColor: '#ff4d4d', data: Array(20).fill(0) },
                { label: 'Ay', borderColor: '#00e676', data: Array(20).fill(1) },
                { label: 'Az', borderColor: '#4d94ff', data: Array(20).fill(0) }
            ]},
            options: { ...commonOptions, scales: { y: { min: -5, max: 5, grid: {color: '#1e293b'} } } }
        });

        const ctxGyro = document.getElementById('gyroChart').getContext('2d');
        const gyroChart = new Chart(ctxGyro, {
            type: 'line',
            data: { labels: Array(20).fill(''), datasets: [
                { label: 'Gx', borderColor: '#ffb84d', data: Array(20).fill(0) },
                { label: 'Gy', borderColor: '#e600e6', data: Array(20).fill(0) },
                { label: 'Gz', borderColor: '#00ccff', data: Array(20).fill(0) }
            ]},
            options: { ...commonOptions, scales: { y: { min: -250, max: 250, grid: {color: '#1e293b'} } } }
        });

        const ctxHealth = document.getElementById('healthChart').getContext('2d');
        const healthChart = new Chart(ctxHealth, {
            type: 'line',
            data: { labels: Array(20).fill(''), datasets: [
                { label: 'Nhịp Tim (BPM)', borderColor: '#ff1744', backgroundColor: 'rgba(255, 23, 68, 0.1)', fill: true, data: Array(20).fill(70), yAxisID: 'y' },
                { label: 'Khí CH4/CO (ppm)', borderColor: '#00e5ff', backgroundColor: 'rgba(0, 229, 255, 0.1)', fill: true, data: Array(20).fill(0), yAxisID: 'y1' }
            ]},
            options: { 
                ...commonOptions, 
                scales: { 
                    y: { type: 'linear', display: true, position: 'left', min: 40, max: 180 },
                    y1: { type: 'linear', display: true, position: 'right', min: 0, max: 100, grid: {drawOnChartArea: false} }
                } 
            }
        });

        // Chọn công nhân để xem đồ thị
        function selectWorker(wid) {
            selectedWorkerId = wid;
            document.getElementById('current-worker-name').innerText = wid;
            updateWorkers(); // Force render lại highlight
        }

        // ==========================================
        // 2. KHỞI TẠO BẢN ĐỒ LEAFLET
        // ==========================================
        const map = L.map('map-container', { crs: L.CRS.Simple, minZoom: -1, maxZoom: 5, zoomControl: true, attributionControl: false });
        const viewBounds = [[-15, -15], [115, 115]];
        map.fitBounds(viewBounds);
        map.setView([50, 50], 3);

        for (let i = 0; i <= 100; i += 10) {
            L.polyline([[0, i], [100, i]], {color: '#1a2235', weight: i%50===0 ? 2 : 1, dashArray: '4, 4'}).addTo(map);
            L.polyline([[i, 0], [i, 100]], {color: '#1a2235', weight: i%50===0 ? 2 : 1, dashArray: '4, 4'}).addTo(map);
        }

        const minePolygon = [[10, 43], [43, 43], [43, 10], [57, 10], [57, 90], [43, 90], [43, 57], [10, 57]];
        L.polygon(minePolygon, { color: '#8b7355', weight: 6, fillColor: '#0a0f18', fillOpacity: 1.0, dashArray: '15, 10' }).addTo(map);
        
        // Ray xe goòng
        L.polyline([[48.5, 10], [48.5, 90]], {color: '#334155', weight: 2}).addTo(map);
        L.polyline([[51.5, 10], [51.5, 90]], {color: '#334155', weight: 2}).addTo(map);
        L.polyline([[50, 10], [50, 90]], {color: '#94a3b8', weight: 3, dashArray: '1, 8'}).addTo(map);
        L.polyline([[10, 48.5], [50, 48.5]], {color: '#334155', weight: 2}).addTo(map);
        L.polyline([[10, 51.5], [50, 51.5]], {color: '#334155', weight: 2}).addTo(map);
        L.polyline([[10, 50], [50, 50]], {color: '#94a3b8', weight: 3, dashArray: '1, 8'}).addTo(map);

        const heat = L.heatLayer([], { radius: 35, blur: 25, maxZoom: 3, max: 1.0, gradient: { 0.1: 'rgba(0, 50, 255, 0.5)', 0.3: 'cyan', 0.5: 'lime', 0.7: 'yellow', 1.0: 'red' } }).addTo(map);
        const workerMarkers = {};

        const getStatusHex = (w) => {
            if (w.gas_status === "DANGER") return "#00e5ff";
            if (w.fall_status === "FALL" || w.alert === "DANGER") return "#ff1744";
            if (w.alert === "WARNING") return "#ff9100";
            return "#00e676";
        };

        // ==========================================
        // 3. VÒNG LẶP DỮ LIỆU
        // ==========================================
        async function updateWorkers() {
            try {
                const res = await fetch("/latest_status");
                const data = await res.json();
                
                const listContainer = document.getElementById("worker-list");
                let listHTML = '';
                let hasEmergency = false; let gasLeak = false;

                data.workers.sort((a,b) => a.worker_id.localeCompare(b.worker_id)).forEach(w => {
                    let hexValue = getStatusHex(w);

                    // Update Map Marker
                    if (!workerMarkers[w.worker_id]) {
                        workerMarkers[w.worker_id] = L.marker([w.y, w.x]).addTo(map);
                    } else {
                        workerMarkers[w.worker_id].setLatLng([w.y, w.x]);
                    }
                    let pulsingCss = (w.alert !== "NORMAL" || w.gas_status === "DANGER" || w.fall_status === "FALL") ? `<div class="pulsing" style="background: ${hexValue};"></div>` : '';
                    workerMarkers[w.worker_id].setIcon(L.divIcon({ className: 'worker-marker', html: `${pulsingCss}<div class="dot" style="background: ${hexValue}; box-shadow: 0 0 15px ${hexValue};"></div><div class="worker-label">${w.worker_id}</div>` }));

                    // Update Dashboard HTML
                    let isGas = w.gas_status === "DANGER";
                    let isFall = w.fall_status === "FALL";
                    let cardClass = isGas ? "danger" : (isFall ? "danger" : (w.alert==="WARNING"? "warning":""));
                    let badgeText = isGas ? "KHÍ GAS MỨC 2!" : (isFall ? "ĐÃ NGÃ (TINY-ML)!" : (w.alert==="WARNING"? "Cảnh báo":"An toàn"));
                    if (isGas || isFall) hasEmergency = true;
                    if (isGas) gasLeak = true;
                    
                    let activeClass = (w.worker_id === selectedWorkerId) ? "active" : "";

                    listHTML += `
                        <div class="worker-card ${cardClass} ${activeClass}" onclick="selectWorker('${w.worker_id}')">
                            <div class="worker-header">
                                <span style="color: ${hexValue};">👷 ${w.worker_id}</span>
                                <span class="worker-status-badge">${badgeText}</span>
                            </div>
                            <div class="stat-row"><span>❤️ Nhịp tim:</span> <span class="stat-val ${w.hr_status.includes('DANGER')?'err':''}">${Math.round(w.hr)} bpm</span></div>
                            <div class="stat-row"><span>☁️ Khí gas:</span> <span class="stat-val ${isGas?'err':''}">${w.gas} ppm</span></div>
                            <div class="stat-row"><span>📍 Radar:</span> <span style="font-family:monospace">[Y:${w.y.toFixed(1)} X:${w.x.toFixed(1)}]</span></div>
                        </div>
                    `;

                    // Vẽ Line Chart nếu đang chọn ông này
                    if (w.worker_id === selectedWorkerId && w.history_imu) {
                        try {
                            // Update Accel Chart
                            accChart.data.datasets[0].data = w.history_imu.ax || [];
                            accChart.data.datasets[1].data = w.history_imu.ay || [];
                            accChart.data.datasets[2].data = w.history_imu.az || [];
                            accChart.update();

                            // Update Gyro Chart
                            gyroChart.data.datasets[0].data = w.history_imu.gx || [];
                            gyroChart.data.datasets[1].data = w.history_imu.gy || [];
                            gyroChart.data.datasets[2].data = w.history_imu.gz || [];
                            gyroChart.update();

                            // Update Health Chart
                            healthChart.data.datasets[0].data = w.history_hr || [];
                            healthChart.data.datasets[1].data = w.history_gas || [];
                            healthChart.update();
                        } catch (e) { console.error(e); }
                    }
                });

                listContainer.innerHTML = listHTML;

                const alertEl = document.getElementById("env-alert");
                if (gasLeak) { alertEl.innerHTML = "🚨 SỰ CỐ: PHÁT HIỆN RÒ RỈ KHÍ ĐỘC!"; alertEl.style.color = "var(--color-cyan)"; alertEl.style.animation = "glow-danger 0.5s infinite alternate";}
                else if (hasEmergency) { alertEl.innerHTML = "⚠️ CẢNH BÁO TAI NẠN LAO ĐỘNG NGHIÊM TRỌNG!"; alertEl.style.color = "var(--color-danger)"; alertEl.style.animation = "glow-danger 1s infinite alternate";}
                else { alertEl.innerHTML = "✓ Hệ thống mỏ hoạt động ổn định"; alertEl.style.animation = "none"; alertEl.style.color = "var(--color-safe)";}

            } catch(e) { console.log(e); }
        }

        async function updateHeatmap() {
            try {
                const res = await fetch("/api/heatmap");
                const data = await res.json();
                if (data.length > 0) {
                    const heatPoints = [];
                    data.forEach(p => {
                        let baseIntensity = 0.05;
                        if (p.type === "DANGER") {
                            heatPoints.push([p.y, p.x, 1.0], [p.y+1, p.x+1, 0.6], [p.y-1, p.x-1, 0.6], [p.y+1, p.x-1, 0.6], [p.y-1, p.x+1, 0.6]); 
                        } else if (p.type === "WARNING") {
                            heatPoints.push([p.y, p.x, 0.5], [p.y+0.5, p.x, 0.3]);
                        } else {
                            heatPoints.push([p.y, p.x, baseIntensity]);
                        }
                    });
                    heat.setLatLngs(heatPoints);
                }
            } catch(e) {}
        }

        // Tốc độ update mượt mà
        setInterval(updateWorkers, 500); // 0.5s để biểu đồ chạy cực mượt
        setInterval(updateHeatmap, 2500);
        setTimeout(() => { map.invalidateSize(); }, 500);

    </script>
</body>
</html>
"""

with open("templates/index.html", "w", encoding="utf-8") as f:
    f.write(html_content)

print("Giao diện UI đã được chèn biểu đồ Chart.js!")
