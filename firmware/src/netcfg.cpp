#include <Preferences.h>
#include "config.h"
#include "netcfg.h"

#define NVS_NAMESPACE "safework"

static Preferences prefs;
static NetConfig   cfg;
static String      line;          // buffer lenh dang go do

// Hoi isKey() truoc: goi getString() cho mot key chua ton tai van tra ve gia tri
// mac dinh nhung kem theo mot dong log [E] ...NOT_FOUND, lam log boot trong nhu
// dang loi trong khi day la duong chay binh thuong.
static String loadOr(const char *key, const char *fallback) {
    return prefs.isKey(key) ? prefs.getString(key) : String(fallback);
}

void netcfg_begin() {
    // Mo read-WRITE de namespace duoc tao neu chua co - mo read-only o lan boot
    // dau tien se in ra "nvs_open failed: NOT_FOUND".
    prefs.begin(NVS_NAMESPACE, false);
    cfg.ssid     = loadOr("ssid", WIFI_SSID);
    cfg.pass     = loadOr("pass", WIFI_PASS);
    cfg.url      = loadOr("url",  BACKEND_URL);
    cfg.workerId = loadOr("wid",  WORKER_ID);
    // Older firmware persisted its compile-time placeholders into NVS on some
    // boards. Do not make a freshly flashed unit show the retired private-LAN
    // URL in the setup portal; keep deliberately provisioned LAN URLs intact.
    if (cfg.ssid == "YOUR_WIFI" &&
        cfg.url == "http://192.168.1.100:5000/api/device_telemetry") {
        cfg.url = BACKEND_URL;
    }
    prefs.end();
}

const NetConfig &netcfg() { return cfg; }

bool netcfg_has_wifi() {
    return cfg.ssid.length() && cfg.ssid != "YOUR_WIFI";
}

bool netcfg_has_backend_url() {
    return cfg.url.startsWith("http://") || cfg.url.startsWith("https://");
}

static void store(const char *key, const String &val) {
    prefs.begin(NVS_NAMESPACE, false);             // read-write
    prefs.putString(key, val);
    prefs.end();
}

bool netcfg_update(const String &ssidIn, const String &passIn,
                   const String &urlIn, const String &workerIdIn, String &error) {
    String ssid = ssidIn;
    String pass = passIn;
    String url = urlIn;
    String workerId = workerIdIn;
    ssid.trim(); pass.trim(); url.trim(); workerId.trim();

    if (!ssid.length() || ssid.length() > 32) {
        error = "Wi-Fi name must contain 1-32 characters.";
        return false;
    }
    if (pass.length() && (pass.length() < 8 || pass.length() > 63)) {
        error = "Wi-Fi password must be empty (open network) or 8-63 characters.";
        return false;
    }
    if (!(url.startsWith("http://") || url.startsWith("https://"))) {
        error = "Backend URL must start with http:// or https://";
        return false;
    }
    if (!workerId.length() || workerId.length() > 50) {
        error = "Worker ID must contain 1-50 characters.";
        return false;
    }

    prefs.begin(NVS_NAMESPACE, false);
    prefs.putString("ssid", ssid);
    prefs.putString("pass", pass);
    prefs.putString("url", url);
    prefs.putString("wid", workerId);
    prefs.end();
    cfg = {ssid, pass, url, workerId};
    error = "";
    return true;
}

void netcfg_clear() {
    prefs.begin(NVS_NAMESPACE, false);
    prefs.clear();
    prefs.end();
    netcfg_begin();
}

static void printCfg(Stream &io) {
    io.printf("{\"event\":\"config\",\"ssid\":\"%s\",\"pass_len\":%u,"
              "\"url\":\"%s\",\"worker_id\":\"%s\"}\n",
              cfg.ssid.c_str(), (unsigned)cfg.pass.length(),
              cfg.url.c_str(), cfg.workerId.c_str());
}

static void printHelp(Stream &io) {
    io.println(F("lenh: show | wifi <ssid> <pass> | url <http://...> | id <WK_xxx> | clear | reboot"));
}

// Tra ve true neu WiFi vua doi
static bool handle(Stream &io, String cmd) {
    cmd.trim();
    if (!cmd.length()) return false;

    int sp = cmd.indexOf(' ');
    String verb = (sp < 0) ? cmd : cmd.substring(0, sp);
    String rest = (sp < 0) ? ""  : cmd.substring(sp + 1);
    rest.trim();
    verb.toLowerCase();

    if (verb == "help" || verb == "?") { printHelp(io); return false; }
    if (verb == "show")                { printCfg(io);  return false; }

    if (verb == "wifi") {
        // "wifi <ssid> <pass>" - tach o dau cach CUOI cung de SSID co the co dau cach
        int cut = rest.lastIndexOf(' ');
        String ssid = (cut < 0) ? rest : rest.substring(0, cut);
        String pass = (cut < 0) ? ""   : rest.substring(cut + 1);
        ssid.trim(); pass.trim();
        if (!ssid.length()) { io.println(F("!! thieu ssid")); return false; }
        cfg.ssid = ssid; cfg.pass = pass;
        store("ssid", ssid); store("pass", pass);
        printCfg(io);
        return true;                               // caller ket noi lai
    }
    if (verb == "url") {
        if (!rest.length()) { io.println(F("!! thieu url")); return false; }
        cfg.url = rest; store("url", rest); printCfg(io); return false;
    }
    if (verb == "id") {
        if (!rest.length()) { io.println(F("!! thieu worker id")); return false; }
        cfg.workerId = rest; store("wid", rest); printCfg(io); return false;
    }
    if (verb == "clear") {
        netcfg_clear();
        io.println(F("da xoa NVS, quay ve mac dinh trong config.h"));
        printCfg(io);
        return true;
    }
    if (verb == "reboot") { io.println(F("reboot...")); delay(100); ESP.restart(); }

    io.printf("!! khong hieu lenh '%s'\n", verb.c_str());
    printHelp(io);
    return false;
}

bool netcfg_service(Stream &io) {
    bool wifiChanged = false;
    while (io.available()) {
        char c = (char)io.read();
        if (c == '\r') continue;
        if (c == '\n') {
            wifiChanged |= handle(io, line);
            line = "";
        } else if (line.length() < 160) {
            line += c;
        }
    }
    return wifiChanged;
}
