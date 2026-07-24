#include <Arduino.h>
#include <DNSServer.h>
#include <WebServer.h>
#include <WiFi.h>

#include "config.h"
#include "netcfg.h"
#include "wifi_portal.h"

namespace {

constexpr byte DNS_PORT = 53;
constexpr uint32_t PORTAL_GRACE_AFTER_CONNECT_MS = 5UL * 60UL * 1000UL;

WebServer server(80);
DNSServer dns;
bool routesReady = false;
bool portalActive = false;
bool reconnectRequested = false;
uint32_t connectedAt = 0;
String portalSsid;

String htmlEscape(const String &input) {
    String out;
    out.reserve(input.length() + 16);
    for (size_t i = 0; i < input.length(); ++i) {
        switch (input[i]) {
            case '&': out += F("&amp;"); break;
            case '<': out += F("&lt;"); break;
            case '>': out += F("&gt;"); break;
            case '\"': out += F("&quot;"); break;
            case '\'': out += F("&#39;"); break;
            default: out += input[i]; break;
        }
    }
    return out;
}

String jsonEscape(const String &input) {
    String out;
    out.reserve(input.length() + 8);
    for (size_t i = 0; i < input.length(); ++i) {
        char c = input[i];
        if (c == '\\' || c == '\"') out += '\\';
        if (c == '\n') out += F("\\n");
        else if (c == '\r') out += F("\\r");
        else out += c;
    }
    return out;
}

const char *wifiStatusText() {
    switch (WiFi.status()) {
        case WL_CONNECTED: return "Connected";
        case WL_NO_SSID_AVAIL: return "Wi-Fi name not found";
        case WL_CONNECT_FAILED: return "Authentication failed";
        case WL_CONNECTION_LOST: return "Connection lost";
        case WL_IDLE_STATUS: return "Connecting";
        default: return "Not connected";
    }
}

String portalPage(const String &notice = "", bool isError = false) {
    const NetConfig &cfg = netcfg();
    String page;
    page.reserve(4600);
    page += F("<!doctype html><html lang='en'><head><meta charset='utf-8'>"
              "<meta name='viewport' content='width=device-width,initial-scale=1'>"
              "<title>SafeWork device setup</title><style>"
              "*{box-sizing:border-box}body{margin:0;background:#eff3f6;color:#17212b;"
              "font-family:Arial,sans-serif}.card{max-width:570px;margin:28px auto;padding:24px;"
              "background:#fff;border-radius:16px;box-shadow:0 10px 28px #0002}h1{margin:0 0 6px}"
              ".muted{color:#52616f;font-size:14px;line-height:1.45}.status{margin:16px 0;padding:12px;"
              "border-radius:9px;background:#e8f4ec;color:#14532d}.error{background:#fff0f0;color:#991b1b}"
              "label{display:block;font-weight:700;margin:16px 0 6px}input{width:100%;padding:12px;"
              "border:1px solid #aab7c4;border-radius:8px;font-size:16px}button{width:100%;margin-top:22px;"
              "padding:13px;border:0;border-radius:8px;background:#146c94;color:white;font-weight:700;font-size:16px}"
              "code{background:#eef2f5;padding:2px 5px;border-radius:4px}.foot{margin-top:20px;font-size:12px;color:#52616f}"
              "</style></head><body><main class='card'><h1>SafeWork setup</h1>");
    page += F("<p class='muted'>This ESP32 joins your Wi-Fi, then sends live telemetry to the selected SafeWork server.</p>");
    page += F("<div class='status'>AP: <b>");
    page += htmlEscape(portalSsid);
    page += F("</b><br>Station: <b>");
    page += wifiStatusText();
    page += F("</b>");
    if (WiFi.status() == WL_CONNECTED) {
        page += F("<br>IP: <code>");
        page += WiFi.localIP().toString();
        page += F("</code>");
    }
    page += F("</div>");
    if (notice.length()) {
        page += F("<div class='status");
        if (isError) page += F(" error");
        page += F("'>");
        page += htmlEscape(notice);
        page += F("</div>");
    }
    page += F("<form method='POST' action='/save'><label for='ssid'>Wi-Fi name (SSID)</label>"
              "<input id='ssid' name='ssid' required maxlength='32' autocomplete='username' value='");
    page += htmlEscape(cfg.ssid == "YOUR_WIFI" ? "" : cfg.ssid);
    page += F("'><label for='pass'>Wi-Fi password</label>"
              "<input id='pass' name='pass' type='password' maxlength='63' autocomplete='current-password' "
              "placeholder='Leave empty only for an open network'>"
              "<label for='url'>Telemetry URL</label><input id='url' name='url' type='url' required maxlength='160' value='");
    page += htmlEscape(cfg.url);
    page += F("'><label for='worker'>Worker ID</label><input id='worker' name='worker' required maxlength='50' value='");
    page += htmlEscape(cfg.workerId);
    page += F("'><button type='submit'>Save and connect</button></form>"
              "<p class='foot'>The Wi-Fi password is saved only in this device's NVS and is never shown here. "
              "The setup AP closes five minutes after a successful connection.</p></main></body></html>");
    return page;
}

void sendRoot() {
    server.sendHeader("Cache-Control", "no-store");
    server.send(200, "text/html; charset=utf-8", portalPage());
}

void saveConfig() {
    String error;
    if (!netcfg_update(server.arg("ssid"), server.arg("pass"),
                       server.arg("url"), server.arg("worker"), error)) {
        server.send(400, "text/html; charset=utf-8", portalPage(error, true));
        return;
    }
    reconnectRequested = true;
    server.send(200, "text/html; charset=utf-8",
                portalPage("Saved. The device is now joining the Wi-Fi network."));
}

void sendStatus() {
    String out = F("{\"portal\":true,\"ap_ssid\":\"");
    out += jsonEscape(portalSsid);
    out += F("\",\"wifi\":\"");
    out += wifiStatusText();
    out += F("\",\"connected\":");
    out += WiFi.status() == WL_CONNECTED ? F("true") : F("false");
    out += F(",\"ip\":\"");
    out += WiFi.status() == WL_CONNECTED ? WiFi.localIP().toString() : "";
    out += F("\"}");
    server.send(200, "application/json", out);
}

void installRoutes() {
    if (routesReady) return;
    server.on("/", HTTP_GET, sendRoot);
    server.on("/save", HTTP_POST, saveConfig);
    server.on("/status", HTTP_GET, sendStatus);
    server.onNotFound([]() {
        server.sendHeader("Location", "/", true);
        server.send(302, "text/plain", "");
    });
    routesReady = true;
}

String makePortalSsid() {
    String mac = WiFi.macAddress();
    mac.replace(":", "");
    if (mac.length() < 6) mac = "ESP32";
    else mac = mac.substring(mac.length() - 6);
    return String(WIFI_PORTAL_AP_PREFIX) + mac;
}

} // namespace

void wifi_portal_start() {
    if (portalActive) return;
    WiFi.mode(WIFI_AP_STA);
    portalSsid = makePortalSsid();
    WiFi.softAPConfig(IPAddress(192, 168, 4, 1), IPAddress(192, 168, 4, 1),
                      IPAddress(255, 255, 255, 0));
    if (!WiFi.softAP(portalSsid.c_str(), WIFI_PORTAL_AP_PASSWORD)) {
        Serial.println("{\"event\":\"error\",\"msg\":\"Wi-Fi setup AP failed\"}");
        return;
    }
    installRoutes();
    dns.start(DNS_PORT, "*", WiFi.softAPIP());
    server.begin();
    portalActive = true;
    connectedAt = 0;
    Serial.printf("{\"event\":\"wifi_portal\",\"ssid\":\"%s\",\"pass\":\"%s\",\"url\":\"http://%s/\"}\n",
                  portalSsid.c_str(), WIFI_PORTAL_AP_PASSWORD, WiFi.softAPIP().toString().c_str());
}

void wifi_portal_begin() {
    installRoutes();
    if (!netcfg_has_wifi()) wifi_portal_start();
}

void wifi_portal_service() {
    if (!portalActive) return;
    dns.processNextRequest();
    server.handleClient();

    if (WiFi.status() != WL_CONNECTED) {
        connectedAt = 0;
        return;
    }
    if (!connectedAt) connectedAt = millis();
    if (millis() - connectedAt < PORTAL_GRACE_AFTER_CONNECT_MS) return;

    dns.stop();
    server.stop();
    WiFi.softAPdisconnect(true);
    WiFi.mode(WIFI_STA);
    portalActive = false;
    Serial.println("{\"event\":\"wifi_portal\",\"state\":\"closed\"}");
}

bool wifi_portal_active() { return portalActive; }

bool wifi_portal_take_reconnect_request() {
    bool result = reconnectRequested;
    reconnectRequested = false;
    return result;
}

const String &wifi_portal_ssid() { return portalSsid; }
