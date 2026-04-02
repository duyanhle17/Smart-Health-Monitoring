export const FALLBACK_ANCHORS = [
  { id: 'ANC_STAGE', x: 50, y: 12 },
  { id: 'ANC_LEFT', x: 0, y: 60 },
  { id: 'ANC_RIGHT', x: 93, y: 60 },
];

export const FALLBACK_WORKERS = [
  { worker_id: 'WK_077', x: 50, y: 27, zone: 'GAMMA_STAGE' },
];

export const SCENARIO_ANCHORS = {
  CAVE_IN: [
    { id: 'ANC_UPPER', x: 80, y: -17, z: 2 },
    { id: 'ANC_DEEP_L', x: 15, y: 90, z: 2 },
    { id: 'ANC_DEEP_R', x: 63, y: 84, z: 2 },
    { id: 'ANC_DEEP_C', x: 30, y: 50, z: 2 },
  ],
  EVACUATION: [
    { id: 'ANC_UPPER', x: 80, y: -17, z: 2 },
    { id: 'ANC_DEEP_L', x: 15, y: 90, z: 2 },
    { id: 'ANC_DEEP_R', x: 63, y: 84, z: 2 },
    { id: 'ANC_DEEP_C', x: 30, y: 50, z: 2 },
  ]
};

export const SCENARIO_WORKERS = {
  CAVE_IN: [
    { worker_id: 'WK_004', x: 23, y: 110, alert: 'OFFLINE', zone: 'CAVE_ZONE', z: 2, hr: '--', temp: '--', ch4: 10.5, co: 200, fall_status: 'SAFE' },
    { worker_id: 'WK_077', x: 56, y: 40, alert: 'WARNING', zone: 'CAVE_ZONE', z: 2, hr: 145, temp: 39.5, ch4: 8.2, co: 150, fall_status: 'FALL' },
    { worker_id: 'WK_089', x: 37, y: 64, alert: 'DANGER', zone: 'CAVE_ZONE', z: 2, hr: 110, temp: 37.5, ch4: 4.5, co: 90, fall_status: 'SAFE' },
    { worker_id: 'WK_048', x: 63, y: 57, alert: 'NORMAL', zone: 'SAFE_ZONE', z: 2, hr: 75, temp: 36.5, ch4: 0.1, co: 5.0, fall_status: 'SAFE' },
    { worker_id: 'WK_055', x: 63, y: 53, alert: 'NORMAL', zone: 'SAFE_ZONE', z: 2, hr: 80, temp: 36.6, ch4: 0.2, co: 3.0, fall_status: 'SAFE' }
  ],
  EVACUATION: [
    { worker_id: 'WK_089', x: 25, y: 80, alert: 'DANGER', zone: 'EVAC_ROUTE', z: 2, hr: 140, temp: 38.0, ch4: 6.5, co: 110, fall_status: 'SAFE' },
    { worker_id: 'WK_004', x: 18, y: 95, alert: 'DANGER', zone: 'EVAC_ROUTE', z: 2, hr: 115, temp: 37.5, ch4: 3.5, co: 70, fall_status: 'SAFE' },
    { worker_id: 'WK_077', x: 37, y: 65, alert: 'DANGER', zone: 'EVAC_ROUTE', z: 2, hr: 155, temp: 39.5, ch4: 8.5, co: 140, fall_status: 'SAFE' },
    { worker_id: 'WK_012', x: 55, y: 65, alert: 'WARNING', zone: 'CENTER_PATH', z: 2, hr: 105, temp: 37.0, ch4: 2.5, co: 50, fall_status: 'SAFE' },
    { worker_id: 'WK_048', x: 60, y: 35, alert: 'WARNING', zone: 'SAFE_ZONE', z: 2, hr: 90, temp: 36.8, ch4: 1.0, co: 10, fall_status: 'SAFE' },
    { worker_id: 'WK_055', x: 75, y: 10, alert: 'WARNING', zone: 'SAFE_ZONE', z: 2, hr: 85, temp: 36.5, ch4: 0.2, co: 5, fall_status: 'SAFE' }
  ]
};

export const MODE_ANCHORS = {
  LOBBY: [
    { id: 'ANC_LOBBY_LEFT', x: 5, y: 90, z: 2 },
    { id: 'ANC_LOBBY_MID', x: 50, y: 7.5, z: 80 },
    { id: 'ANC_LOBBY_RIGHT', x: 95, y: 90, z: 2 },
  ],
  ELEVATED: [
    { id: 'ANC_TUBE_LEFT', x: 14, y: 90, z: 6 },
    { id: 'ANC_TUBE_MID', x: 50, y: 50, z: 6 },
    { id: 'ANC_TUBE_RIGHT', x: 95, y: 50, z: 6 },
  ]
};

export const MODE_WORKERS = {
  LOBBY: [
    { worker_id: 'WK_077', x: 30, y: 70, alert: 'NORMAL', zone: 'LOBBY_FLOOR', z: 2, hr: 78, temp: 36.6, ch4: 0.2, co: 3, fall_status: 'SAFE' },
    { worker_id: 'WK_048', x: 50, y: 70, alert: 'NORMAL', zone: 'LOBBY_FLOOR', z: 2, hr: 72, temp: 36.4, ch4: 0.1, co: 2, fall_status: 'SAFE' },
    { worker_id: 'WK_089', x: 65, y: 85, alert: 'NORMAL', zone: 'LOBBY_FLOOR', z: 2, hr: 80, temp: 36.8, ch4: 0.3, co: 4, fall_status: 'SAFE' },
    { worker_id: 'WK_004', x: 80, y: 70, alert: 'WARNING', zone: 'LOBBY_FLOOR', z: 2, hr: 110, temp: 37.5, ch4: 1.5, co: 30, fall_status: 'SAFE' },
  ],
  ELEVATED: [
    { worker_id: 'WK_077', x: 12, y: 70, alert: 'NORMAL', zone: 'TUBE_PATH', z: 6, hr: 75, temp: 36.5, ch4: 0.1, co: 2, fall_status: 'SAFE' },
    { worker_id: 'WK_048', x: 50, y: 48, alert: 'NORMAL', zone: 'TUBE_PATH', z: 6, hr: 70, temp: 36.3, ch4: 0.2, co: 3, fall_status: 'SAFE' },
    { worker_id: 'WK_089', x: 80, y: 52, alert: 'WARNING', zone: 'TUBE_PATH', z: 6, hr: 95, temp: 37.0, ch4: 1.0, co: 20, fall_status: 'SAFE' },
  ]
};
