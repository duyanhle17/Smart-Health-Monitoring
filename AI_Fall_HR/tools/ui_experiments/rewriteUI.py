import io
import os

html_content = """<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <title>Giám sát Hầm Lò Đa Tác Vụ</title>
    <!-- THƯ VIỆN BẢN ĐỒ CHUẨN: LEAFLET & LEAFLET-HEAT -->
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <script src="https://unpkg.com/leaflet.heat/dist/leaflet-heat.js"></script>
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
            background-color: #06090f; padding: 15px 30px;
            display: flex; justify-content: space-between; align-items: center;
            border-bottom: 2px solid #1f293d;
            box-shadow: 0 4px 6px rgba(0,0,0,0.5);
            z-index: 100;
        }
        .header h1 { margin: 0; font-size: 22px; color: #fff; text-shadow: 0 0 10px #00e5ff; letter-spacing: 1px;}

        .dashboard { display: flex; flex: 1; overflow: hidden; }

        .sidebar {
            width: 400px; background-color: var(--panel-bg); padding: 20px;
            overflow-y: auto; border-right: 2px solid #1f293d; z-index: 10;
            box-shadow: 4px 0 15px rgba(0,0,0,0.5);
        }

        .worker-card {
            background: #1c2438; border-radius: 12px; padding: 15px; margin-bottom: 15px;
            border-left: 6px solid var(--color-safe); transition: all 0.3s;
            position: relative; overflow: hidden;
            box-shadow: 0 4px 10px rgba(0,0,0,0.3);
        }
        .worker-card.danger { border-left-color: var(--color-danger); animation: glow-danger 0.8s infinite alternate; }
        .worker-card.warning { border-left-color: var(--color-warn); }

        @keyframes glow-danger {
            from { box-shadow: 0 0 5px rgba(255, 23, 68, 0.2); }
            to { box-shadow: 0 0 25px rgba(255, 23, 68, 0.7); }
        }

        .worker-header {
            display: flex; justify-content: space-between; align-items: center;
            font-weight: bold; font-size: 17px; margin-bottom: 12px; border-bottom: 1px solid #2d3748; padding-bottom: 8px;
        }
        
        .worker-status-badge { font-size: 12px; padding: 4px 10px; border-radius: 12px; background: var(--color-safe); color: #000; font-weight:bold; letter-spacing: 0.5px;}
        .worker-card.danger .worker-status-badge { background: var(--color-danger); color: #fff; }
        .worker-card.warning .worker-status-badge { background: var(--color-warn); color: #000; }

        .stat-row { display: flex; justify-content: space-between; align-items: center; margin: 10px 0; font-size: 14px; }
        .stat-val { font-weight: bold; font-size: 15px; text-align: right; }
        .stat-val.safe { color: var(--color-safe); }
        .stat-val.warn { color: var(--color-warn); }
        .stat-val.err { color: var(--color-danger); }

        .map-wrapper { flex: 1; display: flex; flex-direction: column; position: relative; }
        
        .map-title {
            position: absolute; top: 20px; left: 30px; z-index: 1000;
            background: rgba(15, 23, 42, 0.9); padding: 12px 25px; border-radius: 8px;
            border: 1px solid #1f293d; backdrop-filter: blur(10px);
            box-shadow: 0 4px 15px rgba(0,0,0,0.5);
        }
        .map-title h2 { margin: 0 0 5px 0; font-size: 18px; color: #e2e8f0;}
        #env-alert { color: var(--color-cyan); font-weight: bold; font-size: 15px; }

        /* BẢN ĐỒ BẢN CHẤT */
        #map-container { flex: 1; outline: 0; background: #000 !important; cursor: crosshair;}
        .leaflet-container { background: #000 !important; }

        /* Icon Marker Định vị Công nhân */
        .worker-marker { position: relative; }
        .worker-marker .dot {
            width: 16px; height: 16px; border-radius: 50%;
            border: 2px solid #fff; position: absolute; top: -8px; left: -8px;
            z-index: 2;
        }
        .worker-marker .pulsing {
            width: 40px; height: 40px; border-radius: 50%;
            position: absolute; top: -20px; left: -20px;
            animation: pulse 1.5s infinite; opacity: 0; z-index: 1;
        }
        @keyframes pulse {
            0% { transform: scale(0.4); opacity: 0.8; }
            100% { transform: scale(1.5); opacity: 0; }
        }
        .worker-label {
            position: absolute; top: 12px; left: -12px; color: white;
            font-weight: bold; font-size: 11px; background: rgba(0,0,0,0.7);
            padding: 2px 6px; border-radius: 4px; border: 1px solid #444;
            white-space: nowrap; z-index: 3;
        }

        .legend-badge { display: inline-block; width: 12px; height: 12px; border-radius: 50%; margin-right: 5px; vertical-align: middle;}
        .legend-item { display: inline-flex; align-items: center; margin-left: 15px; font-size: 13px; color: #cbd5e1;}
        
        .legend-wrapper { 
            position: absolute; bottom: 30px; right: 30px; z-index: 1000; 
            background: rgba(15, 23, 42, 0.9); padding: 15px; border-radius: 8px; 
            border: 1px solid #333; box-shadow: 0 4px 15px rgba(0,0,0,0.5); backdrop-filter: blur(10px);
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>⛏️ Hệ Thống Giám Sát Cảnh Báo Sớm</h1>
        <div>
            <span class="legend-item"><span class="legend-badge" style="background:var(--color-safe)"></span> An toàn</span>
            <span class="legend-item"><span class="legend-badge" style="background:var(--color-warn)"></span> Nhịp tim cao</span>
            <span class="legend-item"><span class="legend-badge" style="background:var(--color-cyan)"></span> Rò khí độc (Ngạt)</span>
            <span class="legend-item"><span class="legend-badge" style="background:var(--color-danger)"></span> Ngã/Nguy kịch</span>
        </div>
    </div>

    <div class="dashboard">
        <div class="sidebar">
            <h3 style="margin-top: 0; border-bottom: 1px solid #2d3748; padding-bottom: 10px; color: #94a3b8; font-size: 15px; text-transform: uppercase;">Real-time Status</h3>
            <div id="worker-list"><p style="text-align:center; color:#555;">Đang kết nối vệ tinh hầm lò...</p></div>
        </div>

        <div class="map-wrapper">
            <div class="map-title">
                <h2>BẢN ĐỒ TỎA NHIỆT RỦI RO (MẶT BẰNG Y-X)</h2>
                <div id="env-alert"><span style='color:#00e676;'>✓ Hệ thống không gian ngầm ổn định</span></div>
            </div>
            
            <!-- VÙNG VẼ BẢN ĐỒ -->
            <div id="map-container"></div>
            
            <div class="legend-wrapper">
                <h4 style="margin:0 0 8px 0; font-size: 13px; color: #94a3b8;">THANG ĐO MẬT ĐỘ RỦI RO (HEAT)</h4>
                <div style="width: 250px; height: 12px; background: linear-gradient(90deg, transparent 0%, rgba(0,229,255,0.7) 30%, rgba(0,255,0,0.8) 50%, rgba(255,255,0,0.9) 75%, rgba(255,0,0,1) 100%); border-radius: 6px;"></div>
                <div style="display: flex; justify-content: space-between; font-size: 11px; color:#64748b; margin-top:6px; font-weight: bold;">
                    <span>Hoạt động đi lại (Vết)</span>
                    <span>Tụ điểm Tai Nạn / Khí độc</span>
                </div>
            </div>
        </div>
    </div>

    <script>
        // ==========================================
        // 1. CẤU HÌNH HỆ TỌA ĐỘ PHẲNG (L.CRS.Simple)
        // Dùng chuẩn của lập trình Game/Indoor map thay cho Lat-Lng Trái đất
        // ==========================================
        const map = L.map('map-container', {
            crs: L.CRS.Simple,
            minZoom: 0,
            maxZoom: 5,
            zoomControl: true,
            attributionControl: false
        });

        // Định nghĩa không gian hầm mỏ X, Y (0 -> 100 mét)
        // Trong Leaflet: Tọa độ truyền vào là [Y, X]
        const bounds = [[0, 0], [100, 100]];
        map.fitBounds(bounds);
        // Map viewport mặc định zoom vào sát vừa vặn hầm
        map.setView([50, 50], 3);

        // Vẽ Khung Lưới (Grid) nền
        L.rectangle(bounds, {color: '#1e293b', weight: 1, fill: false, opacity: 0.8}).addTo(map);

        // Phát họa sơ đồ Tường hầm (Layout Hầm mỏ thực tế)
        const tunnels = [
            [[45, 10], [55, 90]], // Nhánh ngang Y: 45->55, X: 10->90
            [[10, 45], [45, 55]]  // Nhánh rẽ dọc Y: 10->45, X: 45->55
        ];

        tunnels.forEach(coords => {
            L.rectangle(coords, {
                color: '#475569', weight: 2, 
                fillColor: '#0f172a', fillOpacity: 0.8,
                dashArray: '4, 4'
            }).addTo(map);
        });

        // Text Ghi chú trên bề mặt hầm
        L.marker([50, 95], { icon: L.divIcon({className: '', html: '<div style="color:#64748b; font-weight:bold; width: 120px;">Khu Phay Khai Thác</div>'}) }).addTo(map);
        L.marker([5, 50], { icon: L.divIcon({className: '', html: '<div style="color:#00e676; font-weight:bold; width: 60px; text-align:center;">Cửa Hầm</div>'}) }).addTo(map);

        // ==========================================
        // 2. KHỞI TẠO LỚP HEATMAP (LEAFLET-HEAT NGUYÊN BẢN)
        // Sinh ra hiệu ứng lan toả nhiệt (glowing) chuẩn xác 100%
        // ==========================================
        const heat = L.heatLayer([], {
            radius: 35,       // Bán kính lan tỏa đám lửa
            blur: 25,         // Độ nhòe lông chim (Lông mịn)
            maxZoom: 3,
            max: 1.0,         // Ngưỡng cường độ đỏ nhất
            gradient: {
                0.1: 'rgba(0, 50, 255, 0.5)',   // Mát: Xanh sẫm (vết đi mờ)
                0.3: 'cyan',                    // Hơi ấm (vết thường xuyên qua lại)
                0.5: 'lime',                    // Tụ họp vài người (Màu ngả lục)
                0.7: 'yellow',                  // Nóng (1 sự cố)
                1.0: 'red'                      // Rực lửa (Sự cố nghiêm trọng lặp lại)
            }
        }).addTo(map);

        // Quản lý Object Marker (vệ tinh worker)
        const workerMarkers = {};

        const getStatusHex = (w) => {
            if (w.gas_status === "DANGER") return "#00e5ff"; // Xanh Cyan
            if (w.fall_status === "FALL" || w.alert === "DANGER") return "#ff1744"; // Đỏ
            if (w.alert === "WARNING") return "#ff9100"; // Cam
            return "#00e676"; // Xanh chuối
        };

        // ==========================================
        // 3. VÒNG LẶP UPDATE DỮ LIỆU
        // ==========================================
        async function updateWorkers() {
            try {
                const res = await fetch("/latest_status");
                const data = await res.json();
                
                const listContainer = document.getElementById("worker-list");
                listContainer.innerHTML = '';
                let hasEmergency = false;
                let gasLeak = false;

                data.workers.sort((a,b) => a.worker_id.localeCompare(b.worker_id)).forEach(w => {
                    let hexValue = getStatusHex(w);

                    // 3.1. Cập nhật vị trí Marker Vệ tinh trên bản đồ
                    if (!workerMarkers[w.worker_id]) {
                        workerMarkers[w.worker_id] = L.marker([w.y, w.x]).addTo(map);
                    } else {
                        // Leaflet sẽ move tự động marker này tới tọa độ mới
                        workerMarkers[w.worker_id].setLatLng([w.y, w.x]);
                    }

                    // Radar pulse nếu có biến
                    let pulsingCss = (w.alert !== "NORMAL" || w.gas_status === "DANGER" || w.fall_status === "FALL") 
                                     ? `<div class="pulsing" style="background: ${hexValue};"></div>` : '';

                    workerMarkers[w.worker_id].setIcon(L.divIcon({
                        className: 'worker-marker',
                        html: `
                            ${pulsingCss}
                            <div class="dot" style="background: ${hexValue}; box-shadow: 0 0 15px ${hexValue};"></div>
                            <div class="worker-label">${w.worker_id}</div>
                        `
                    }));

                    // 3.2. Cập nhật Dashboard dọc
                    let isGas = w.gas_status === "DANGER";
                    let isFall = w.fall_status === "FALL";
                    let cardClass = isGas ? "danger" : (isFall ? "danger" : (w.alert==="WARNING"? "warning":""));
                    let badgeText = isGas ? "CẢNH BÁO MÔI TRƯỜNG!" : (isFall ? "PHÁT HIỆN NGÃ!" : (w.alert==="WARNING"? "Nhịp tim rủi ro":"Bình thường tĩnh"));
                    
                    if (isGas || isFall) hasEmergency = true;
                    if (isGas) gasLeak = true;

                    listContainer.innerHTML += `
                        <div class="worker-card ${cardClass}">
                            <div class="worker-header">
                                <span style="color: ${hexValue}; text-shadow: 0 0 8px ${hexValue}40;">👷‍♂️ ${w.worker_id}</span>
                                <span class="worker-status-badge">${badgeText}</span>
                            </div>
                            <div class="stat-row">
                                <span><span style="font-size:16px;">❤️</span> Nhịp sinh học:</span>
                                <span class="stat-val ${w.hr_status.includes("DANGER")?'err':''}">${w.hr} <span>bpm</span></span>
                            </div>
                            <div class="stat-row">
                                <span><span style="font-size:16px;">☁️</span> Khí CH4/CO:</span>
                                <span class="stat-val ${isGas?'err':''}">${w.gas} <span>ppm</span></span>
                            </div>
                            <div class="stat-row">
                                <span><span style="font-size:16px;">🏃</span> Trục Gia tốc (Ngã):</span>
                                <span class="stat-val ${isFall?'err':'safe'}">${isFall ? 'Đã ngã / Ngất!' : 'Ổn định thăng bằng'}</span>
                            </div>
                            <div style="font-size:12px; color:#64748b; margin-top: 10px; border-top: 1px dashed #2d3748; padding-top: 8px; display:flex; justify-content:space-between;">
                                <span>Định vị Radar</span>
                                <span style="font-family:monospace; font-size:13px;">[ Y: ${w.y.toFixed(1)} m | X: ${w.x.toFixed(1)} m ]</span>
                            </div>
                        </div>
                    `;
                });

                // Cảnh báo chớp tổng
                const alertEl = document.getElementById("env-alert");
                if (gasLeak) {
                    alertEl.innerHTML = "🚨 CẢNH BÁO: RÒ RỈ KHÍ ĐỘC TẠI PHÂN KHU HẦM!";
                    alertEl.style.animation = "glow-danger 0.5s infinite alternate";
                    alertEl.style.color = "var(--color-cyan)";
                } else if (hasEmergency) {
                    alertEl.innerHTML = "⚠️ PHÁT HIỆN RỦI RO NGHIÊM TRỌNG TỪ CÔNG NHÂN!";
                    alertEl.style.animation = "glow-danger 1s infinite alternate";
                    alertEl.style.color = "var(--color-danger)";
                } else {
                    alertEl.innerHTML = "<span style='color:#00e676;'>✓ Hệ thống không gian ngầm ổn định</span>";
                    alertEl.style.animation = "none";
                }

            } catch(e) {}
        }

        async function updateHeatmap() {
            try {
                const res = await fetch("/api/heatmap");
                const data = await res.json();
                
                if (data.length > 0) {
                    const heatPoints = [];
                    
                    data.forEach(p => {
                        // Tùy theo mức độ, gán cường độ nung nóng cho điểm này
                        let baseIntensity = 0.05; // Để lại vết đi rất mờ xanh lam
                        
                        if (p.type === "DANGER") {
                            // "Bơm" hẳn 1 điểm nóng cục bộ rực lửa đỏ ngay giữa:
                            heatPoints.push([p.y, p.x, 1.0]); 
                            // Cộng thêm hiệu ứng tán nhiệt xung quanh (Nướng chín đồ thị tại vùng đó)
                            heatPoints.push([p.y + 1, p.x + 1, 0.6]); 
                            heatPoints.push([p.y - 1, p.x - 1, 0.6]);
                            heatPoints.push([p.y + 1, p.x - 1, 0.6]);
                            heatPoints.push([p.y - 1, p.x + 1, 0.6]);
                        } else if (p.type === "WARNING") {
                            // Nhiệt mức trung bình (Vàng/Xanh lá)
                            heatPoints.push([p.y, p.x, 0.5]);
                            heatPoints.push([p.y + 0.5, p.x, 0.3]);
                        } else {
                            // Bình thường
                            heatPoints.push([p.y, p.x, baseIntensity]);
                        }
                    });

                    // Cung cấp mảng lưới điểm cho Plugin vẽ tản sáng Radial Gradient!
                    heat.setLatLngs(heatPoints);
                }
            } catch(e) {}
        }

        // Tốc độ update mượt mà
        setInterval(updateWorkers, 1000);
        setInterval(updateHeatmap, 2500);
        
        // Anti-bug Leaflet rendering empty tiles on start
        setTimeout(() => { map.invalidateSize(); }, 500);

    </script>
</body>
</html>
"""

# Ghi đè vào file HTML
with open(os.path.join("templates", "index.html"), "w", encoding="utf-8") as f:
    f.write(html_content)

print("Đã làm lại toàn bộ hệ thống Heatmap mới siêu mượt!")
