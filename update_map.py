import re

with open("templates/index.html", "r", encoding="utf-8") as f:
    html = f.read()

new_map_code = """
        const map = L.map('map-container', {
            crs: L.CRS.Simple,
            minZoom: -1,
            maxZoom: 5,
            zoomControl: true,
            attributionControl: false
        });

        // Mở rộng view để vẽ thêm trục tọa độ
        const viewBounds = [[-15, -15], [115, 115]];
        map.fitBounds(viewBounds);
        // Map viewport mặc định zoom vào sát vừa vặn hầm
        map.setView([50, 50], 3);

        // 1. VẼ LƯỚI TỌA ĐỘ BỀ MẶT (GRID) ĐỂ TRỰC QUAN X,Y
        for (let i = 0; i <= 100; i += 10) {
            // Đường dọc X
            L.polyline([[0, i], [100, i]], {color: '#1a2235', weight: i%50===0 ? 2 : 1, dashArray: '4, 4'}).addTo(map);
            if (i >= 0 && i <= 100) {
                L.marker([-4, i], {icon: L.divIcon({className: '', html: `<div style="color:#64748b; font-size:11px; font-weight:bold; margin-left:-8px;">${i}m</div>`})}).addTo(map);
            }
            // Đường ngang Y
            L.polyline([[i, 0], [i, 100]], {color: '#1a2235', weight: i%50===0 ? 2 : 1, dashArray: '4, 4'}).addTo(map);
            if (i >= 0 && i <= 100) {
                L.marker([i, -4], {icon: L.divIcon({className: '', html: `<div style="color:#64748b; font-size:11px; font-weight:bold;">${i}m</div>`})}).addTo(map);
            }
        }

        // Tên trục tọa độ
        L.marker([-12, 50], {icon: L.divIcon({className: '', html: `<div style="color:#00e5ff; font-weight:bold; font-size:13px; text-align:center; width:250px; margin-left:-125px;">TRỤC X (CHIỀU NGANG HẦM) ➔</div>`})}).addTo(map);
        L.marker([50, -12], {icon: L.divIcon({className: '', html: `<div style="color:#00e5ff; font-weight:bold; font-size:13px; white-space:nowrap; transform: rotate(-90deg); transform-origin: left top;">TRỤC Y (CHIỀU SÂU HẦM) ➔</div>`})}).addTo(map);

        // 2. VẼ SA BÀN ĐỊA CHẤT HẦM LÒ (ROCK & TUNNELS POLYGON)
        // Tạo polygon chữ T nguyên khối để nhìn giống đường hầm đục vào trong đá
        const minePolygon = [
            [10, 43], // Cửa hầm trái
            [43, 43], // Góc ngã ba trái
            [43, 10], // Cuối ngách trái (dưới)
            [57, 10], // Cuối ngách trái (trên)
            [57, 90], // Cuối ngách phải (trên)
            [43, 90], // Cuối ngách phải (dưới)
            [43, 57], // Góc ngã ba phải
            [10, 57]  // Cửa hầm phải
        ];

        L.polygon(minePolygon, {
            color: '#8b7355', // Màu kè gỗ/đá nâu (tường hầm)
            weight: 6,
            fillColor: '#0a0f18', // Màu nền ngầm tăm tối
            fillOpacity: 1.0,
            dashArray: '15, 10' // Kè chống đứt đoạn (giống các vì kèo chống vách)
        }).addTo(map);

        // 3. VẼ ĐƯỜNG RAY XE GOÒNG (MINECART TRACKS TÀ VẸT)
        // Ray dọc (Y)
        L.polyline([[10, 48.5], [50, 48.5]], {color: '#334155', weight: 2}).addTo(map);
        L.polyline([[10, 51.5], [50, 51.5]], {color: '#334155', weight: 2}).addTo(map);
        L.polyline([[10, 50], [50, 50]], {color: '#94a3b8', weight: 3, dashArray: '1, 8'}).addTo(map);
        
        // Ray ngang (X)
        L.polyline([[48.5, 10], [48.5, 90]], {color: '#334155', weight: 2}).addTo(map);
        L.polyline([[51.5, 10], [51.5, 90]], {color: '#334155', weight: 2}).addTo(map);
        L.polyline([[50, 10], [50, 90]], {color: '#94a3b8', weight: 3, dashArray: '1, 8'}).addTo(map);

        // Khu vực cảnh báo nhãn mác
        L.marker([58, 94], { icon: L.divIcon({className: '', html: '<div style="color:#d97706; font-weight:bold; font-size:12px; width: 120px;">⛏️ Gương Khai Thác</div>'}) }).addTo(map);
        L.marker([58, 5], { icon: L.divIcon({className: '', html: '<div style="color:#0ea5e9; font-weight:bold; font-size:12px; width: 120px; text-align:right; margin-left:-120px;">Phân xưởng vật tư ⚙️</div>'}) }).addTo(map);
        L.marker([0, 50], { icon: L.divIcon({className: '', html: '<div style="color:#00e676; font-weight:bold; font-size:15px; width: 120px; text-align:center; border: 2px solid #00e676; padding: 6px; border-radius: 4px; background: rgba(0,230,118,0.1); margin-left:-60px; box-shadow: 0 0 10px rgba(0,230,118,0.3);">▼ CỬA LÒ (0m)</div>'}) }).addTo(map);

        // 4. LỚP HEATMAP NGUYÊN BẢN
        const heat = L.heatLayer([], {
"""

new_html = re.sub(
    r"const map = L\.map\('map-container'.*?const heat = L\.heatLayer\(\[\]\, \{",
    new_map_code,
    html,
    flags=re.DOTALL
)

with open("templates/index.html", "w", encoding="utf-8") as f:
    f.write(new_html)

print("Đã update UI hầm mỏ thành công!")
