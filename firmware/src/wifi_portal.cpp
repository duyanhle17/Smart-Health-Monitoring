#include <Arduino.h>
#include <DNSServer.h>
#include <WiFi.h>
#include <errno.h>
#include <lwip/sockets.h>
#include <strings.h>

#include "config.h"
#include "netcfg.h"
#include "wifi_portal.h"

namespace {

constexpr byte DNS_PORT = 53;
constexpr uint32_t PORTAL_GRACE_AFTER_CONNECT_MS = 30UL * 1000UL;
constexpr int PORTAL_AP_CHANNEL = 11;

// Keep HTTP fully non-blocking. The Arduino WebServer owns only one client and
// has hard-coded 5 s waits for partial captive-portal requests, which makes the
// next browser request look frozen. A bounded, main-loop server cannot let one
// incomplete client stall the setup page.
constexpr size_t PORTAL_HTTP_CLIENTS = 4;
constexpr size_t PORTAL_HTTP_REQUEST_MAX = 2048;
constexpr uint32_t PORTAL_HTTP_REQUEST_TIMEOUT_MS = 650;
constexpr uint32_t PORTAL_HTTP_RESPONSE_TIMEOUT_MS = 1500;

enum class PortalHttpState : uint8_t { Empty, Reading, Writing };

struct PortalHttpClient {
    WiFiClient client;
    PortalHttpState state = PortalHttpState::Empty;
    uint32_t deadline = 0;
    size_t requestLength = 0;
    size_t requestExpected = 0;
    char request[PORTAL_HTTP_REQUEST_MAX + 1]{};
    String response;
    size_t responseSent = 0;
};

WiFiServer server(80, PORTAL_HTTP_CLIENTS);
DNSServer dns;
PortalHttpClient httpClients[PORTAL_HTTP_CLIENTS];
bool portalActive = false;
bool reconnectRequested = false;
uint32_t connectedAt = 0;
String portalSsid;

bool deadlinePassed(uint32_t deadline) {
    return static_cast<int32_t>(millis() - deadline) >= 0;
}

String htmlEscape(const String &input) {
    String out;
    out.reserve(input.length() + 16);
    for (size_t i = 0; i < input.length(); ++i) {
        switch (input[i]) {
            case '&': out += F("&amp;"); break;
            case '<': out += F("&lt;"); break;
            case '>': out += F("&gt;"); break;
            case '"': out += F("&quot;"); break;
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
        if (c == '\\' || c == '"') out += '\\';
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
              "The setup AP closes 30 seconds after a successful connection.</p></main></body></html>");
    return page;
}

void resetHttpClient(PortalHttpClient &slot) {
    slot.client.stop();
    slot.client = WiFiClient();
    slot.state = PortalHttpState::Empty;
    slot.deadline = 0;
    slot.requestLength = 0;
    slot.requestExpected = 0;
    slot.response = "";
    slot.responseSent = 0;
}

void beginHttpServer() {
    for (auto &slot : httpClients) resetHttpClient(slot);
    server.setNoDelay(true);
    server.begin();
}

void stopHttpServer() {
    for (auto &slot : httpClients) resetHttpClient(slot);
    server.stop();
}

const char *httpReason(int code) {
    switch (code) {
        case 200: return "OK";
        case 302: return "Found";
        case 400: return "Bad Request";
        case 413: return "Payload Too Large";
        default: return "Internal Server Error";
    }
}

void queueResponse(PortalHttpClient &slot, int code, const char *contentType,
                   const String &body, const char *location = nullptr) {
    String response;
    response.reserve(body.length() + 180);
    response += F("HTTP/1.1 ");
    response += String(code);
    response += ' ';
    response += httpReason(code);
    response += F("\r\nContent-Type: ");
    response += contentType;
    response += F("\r\nCache-Control: no-store");
    if (location) {
        response += F("\r\nLocation: ");
        response += location;
    }
    response += F("\r\nContent-Length: ");
    response += String(body.length());
    response += F("\r\nConnection: close\r\n\r\n");
    response += body;
    slot.response = response;
    slot.responseSent = 0;
    slot.state = PortalHttpState::Writing;
    slot.deadline = millis() + PORTAL_HTTP_RESPONSE_TIMEOUT_MS;
}

void queueRedirect(PortalHttpClient &slot) {
    queueResponse(slot, 302, "text/plain; charset=utf-8", "", "/");
}

int findHeaderEnd(const char *data, size_t length) {
    for (size_t i = 0; i + 3 < length; ++i) {
        if (data[i] == '\r' && data[i + 1] == '\n' &&
            data[i + 2] == '\r' && data[i + 3] == '\n') {
            return static_cast<int>(i + 4);
        }
    }
    return -1;
}

// 0 means no body. -1 is malformed; -2 exceeds this small provisioning form.
int contentLengthOf(const char *data, size_t headerLength) {
    size_t start = 0;
    while (start < headerLength) {
        size_t end = start;
        while (end < headerLength && data[end] != '\r' && data[end] != '\n') ++end;
        const size_t lineLength = end - start;
        constexpr char key[] = "Content-Length:";
        if (lineLength >= sizeof(key) - 1 &&
            strncasecmp(data + start, key, sizeof(key) - 1) == 0) {
            size_t pos = start + sizeof(key) - 1;
            while (pos < end && (data[pos] == ' ' || data[pos] == '\t')) ++pos;
            long value = 0;
            bool hasDigit = false;
            while (pos < end && data[pos] >= '0' && data[pos] <= '9') {
                hasDigit = true;
                value = value * 10 + (data[pos] - '0');
                if (value > static_cast<long>(PORTAL_HTTP_REQUEST_MAX)) return -2;
                ++pos;
            }
            while (pos < end && (data[pos] == ' ' || data[pos] == '\t')) ++pos;
            return hasDigit && pos == end ? static_cast<int>(value) : -1;
        }
        while (end < headerLength && (data[end] == '\r' || data[end] == '\n')) ++end;
        start = end;
    }
    return 0;
}

int hexValue(char c) {
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    if (c >= 'A' && c <= 'F') return c - 'A' + 10;
    return -1;
}

String urlDecode(const char *data, size_t length) {
    String out;
    out.reserve(length);
    for (size_t i = 0; i < length; ++i) {
        if (data[i] == '+') {
            out += ' ';
        } else if (data[i] == '%' && i + 2 < length) {
            const int high = hexValue(data[i + 1]);
            const int low = hexValue(data[i + 2]);
            if (high >= 0 && low >= 0) {
                out += static_cast<char>((high << 4) | low);
                i += 2;
            } else {
                out += data[i];
            }
        } else {
            out += data[i];
        }
    }
    return out;
}

String formValue(const char *data, size_t length, const char *wantedKey) {
    size_t start = 0;
    while (start < length) {
        size_t end = start;
        while (end < length && data[end] != '&') ++end;
        size_t equal = start;
        while (equal < end && data[equal] != '=') ++equal;
        String key = urlDecode(data + start, equal - start);
        if (key == wantedKey) {
            return equal < end ? urlDecode(data + equal + 1, end - equal - 1) : String();
        }
        start = end + 1;
    }
    return String();
}

void queueStatus(PortalHttpClient &slot) {
    String out = F("{\"portal\":true,\"ap_ssid\":\"");
    out += jsonEscape(portalSsid);
    out += F("\",\"wifi\":\"");
    out += wifiStatusText();
    out += F("\",\"connected\":");
    out += WiFi.status() == WL_CONNECTED ? F("true") : F("false");
    out += F(",\"ip\":\"");
    out += WiFi.status() == WL_CONNECTED ? WiFi.localIP().toString() : "";
    out += F("\"}");
    queueResponse(slot, 200, "application/json", out);
}

void queueSave(PortalHttpClient &slot, const char *body, size_t length) {
    String error;
    if (!netcfg_update(formValue(body, length, "ssid"), formValue(body, length, "pass"),
                       formValue(body, length, "url"), formValue(body, length, "worker"), error)) {
        queueResponse(slot, 400, "text/html; charset=utf-8", portalPage(error, true));
        return;
    }
    reconnectRequested = true;
    queueResponse(slot, 200, "text/html; charset=utf-8",
                  portalPage("Saved. The device is now joining the Wi-Fi network."));
}

void dispatchRequest(PortalHttpClient &slot, size_t headerLength) {
    slot.request[slot.requestLength] = '\0';
    size_t lineEnd = 0;
    while (lineEnd < headerLength && slot.request[lineEnd] != '\r' && slot.request[lineEnd] != '\n') ++lineEnd;
    String requestLine = String(slot.request).substring(0, lineEnd);
    const int firstSpace = requestLine.indexOf(' ');
    const int secondSpace = requestLine.indexOf(' ', firstSpace + 1);
    if (firstSpace <= 0 || secondSpace <= firstSpace + 1) {
        queueResponse(slot, 400, "text/plain; charset=utf-8", "Malformed request");
        return;
    }
    const String method = requestLine.substring(0, firstSpace);
    String path = requestLine.substring(firstSpace + 1, secondSpace);
    const int query = path.indexOf('?');
    if (query >= 0) path = path.substring(0, query);

    if (method == "GET" && (path == "/" || path == "/index.html")) {
        queueResponse(slot, 200, "text/html; charset=utf-8", portalPage());
    } else if (method == "GET" && path == "/status") {
        queueStatus(slot);
    } else if (method == "POST" && path == "/save") {
        queueSave(slot, slot.request + headerLength, slot.requestExpected - headerLength);
    } else {
        queueRedirect(slot);
    }
}

void serviceReading(PortalHttpClient &slot) {
    if (deadlinePassed(slot.deadline)) {
        resetHttpClient(slot);
        return;
    }
    if (!slot.client.connected() && slot.client.available() == 0) {
        resetHttpClient(slot);
        return;
    }

    while (slot.client.available() > 0 && slot.requestLength < PORTAL_HTTP_REQUEST_MAX) {
        size_t remaining = PORTAL_HTTP_REQUEST_MAX - slot.requestLength;
        if (remaining > 256) remaining = 256;
        const int received = slot.client.read(
            reinterpret_cast<uint8_t *>(slot.request + slot.requestLength), remaining);
        if (received <= 0) break;
        slot.requestLength += static_cast<size_t>(received);
    }
    slot.request[slot.requestLength] = '\0';

    int headerLength = findHeaderEnd(slot.request, slot.requestLength);
    if (headerLength < 0) {
        if (slot.requestLength == PORTAL_HTTP_REQUEST_MAX) {
            queueResponse(slot, 413, "text/plain; charset=utf-8", "Request too large");
        }
        return;
    }

    if (!slot.requestExpected) {
        const int bodyLength = contentLengthOf(slot.request, static_cast<size_t>(headerLength));
        if (bodyLength == -2 || static_cast<size_t>(headerLength) + static_cast<size_t>(bodyLength) > PORTAL_HTTP_REQUEST_MAX) {
            queueResponse(slot, 413, "text/plain; charset=utf-8", "Request too large");
            return;
        }
        if (bodyLength < 0) {
            queueResponse(slot, 400, "text/plain; charset=utf-8", "Invalid Content-Length");
            return;
        }
        slot.requestExpected = static_cast<size_t>(headerLength) + static_cast<size_t>(bodyLength);
    }
    if (slot.requestLength >= slot.requestExpected) {
        dispatchRequest(slot, static_cast<size_t>(headerLength));
    }
}

void serviceWriting(PortalHttpClient &slot) {
    if (deadlinePassed(slot.deadline) || !slot.client.connected()) {
        resetHttpClient(slot);
        return;
    }
    if (slot.responseSent >= slot.response.length()) {
        resetHttpClient(slot);
        return;
    }
    const int sent = send(slot.client.fd(), slot.response.c_str() + slot.responseSent,
                          slot.response.length() - slot.responseSent, MSG_DONTWAIT);
    if (sent > 0) {
        slot.responseSent += static_cast<size_t>(sent);
    } else if (sent < 0 && errno != EAGAIN && errno != EWOULDBLOCK) {
        resetHttpClient(slot);
    }
}

void acceptHttpClients() {
    for (size_t count = 0; count < PORTAL_HTTP_CLIENTS && server.hasClient(); ++count) {
        WiFiClient incoming = server.available();
        if (!incoming) return;
        PortalHttpClient *freeSlot = nullptr;
        for (auto &slot : httpClients) {
            if (slot.state == PortalHttpState::Empty) {
                freeSlot = &slot;
                break;
            }
        }
        if (!freeSlot) {
            incoming.stop();
            continue;
        }
        freeSlot->client = incoming;
        freeSlot->client.setNoDelay(true);
        freeSlot->state = PortalHttpState::Reading;
        freeSlot->deadline = millis() + PORTAL_HTTP_REQUEST_TIMEOUT_MS;
        freeSlot->requestLength = 0;
        freeSlot->requestExpected = 0;
        freeSlot->response = "";
        freeSlot->responseSent = 0;
    }
}

void serviceHttpServer() {
    acceptHttpClients();
    for (auto &slot : httpClients) {
        if (slot.state == PortalHttpState::Reading) serviceReading(slot);
        else if (slot.state == PortalHttpState::Writing) serviceWriting(slot);
    }
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
    if (portalActive) {
        // A failed attempt after Save may leave the portal visible in AP+STA
        // mode. Stop the station side so its auto-reconnect scans cannot make
        // the setup AP lag, while preserving the already running AP server.
        WiFi.disconnect(false, false);
        WiFi.mode(WIFI_AP);
        connectedAt = 0;
        return;
    }
    // Do not keep retrying/scanning the failed station network while someone is
    // configuring the device. On a single-radio ESP32 that channel hopping
    // makes the SoftAP slow or briefly unreachable. Credentials remain in NVS.
    WiFi.disconnect(false, false);
    WiFi.mode(WIFI_AP);
    portalSsid = makePortalSsid();
    WiFi.softAPConfig(IPAddress(192, 168, 4, 1), IPAddress(192, 168, 4, 1),
                      IPAddress(255, 255, 255, 0));
    if (!WiFi.softAP(portalSsid.c_str(), WIFI_PORTAL_AP_PASSWORD,
                     PORTAL_AP_CHANNEL, false, 4)) {
        Serial.println("{\"event\":\"error\",\"msg\":\"Wi-Fi setup AP failed\"}");
        return;
    }
    dns.start(DNS_PORT, "*", WiFi.softAPIP());
    beginHttpServer();
    portalActive = true;
    connectedAt = 0;
    Serial.printf("{\"event\":\"wifi_portal\",\"ssid\":\"%s\",\"pass\":\"%s\",\"channel\":%d,\"url\":\"http://%s/\"}\n",
                  portalSsid.c_str(), WIFI_PORTAL_AP_PASSWORD, PORTAL_AP_CHANNEL,
                  WiFi.softAPIP().toString().c_str());
}

void wifi_portal_begin() {
    if (!netcfg_has_wifi()) wifi_portal_start();
}

void wifi_portal_service() {
    if (!portalActive) return;
    dns.processNextRequest();
    serviceHttpServer();

    if (WiFi.status() != WL_CONNECTED) {
        connectedAt = 0;
        return;
    }
    if (!connectedAt) connectedAt = millis();
    if (millis() - connectedAt < PORTAL_GRACE_AFTER_CONNECT_MS) return;

    dns.stop();
    stopHttpServer();
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
