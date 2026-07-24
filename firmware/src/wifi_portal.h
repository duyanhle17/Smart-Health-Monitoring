#pragma once
#include <Arduino.h>

// Local AP + captive configuration page for the tag. The portal is opened
// automatically on a fresh board and after a failed station connection.
void wifi_portal_begin();
void wifi_portal_start();
void wifi_portal_service();
bool wifi_portal_active();
bool wifi_portal_take_reconnect_request();
const String &wifi_portal_ssid();
