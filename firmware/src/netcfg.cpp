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
    prefs.end();
}

const NetConfig &netcfg() { return cfg; }

static void store(const char *key, const String &val) {
    prefs.begin(NVS_NAMESPACE, false);             // read-write
    prefs.putString(key, val);
    prefs.end();
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
        prefs.begin(NVS_NAMESPACE, false);
        prefs.clear();
        prefs.end();
        netcfg_begin();
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
