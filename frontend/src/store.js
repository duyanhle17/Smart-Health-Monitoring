import { create } from 'zustand';

const useStore = create((set) => ({
  workers: {},
  zones: {}, // Store zone-wide env data
  anchors: [],
  // Server-authoritative assumptions for the physical UWB coordinate frame.
  // In particular, `anchor_baseline_m` is the tape-measured distance used by
  // the backend solver, not a visual distance inferred from the 3-D map.
  uwbConfig: null,
  // Registered personnel from /api/personnel — the single source of names.
  personnel: [],
  hoveredZone: null,
  systemTime: null,
  isConnected: false,
  lastUpdate: null,
  hiddenNodes: {}, // Support toggling global visibility
  // Map scene skin: SITE = the real presentation booth; MINE = the demo
  // tunnel used for presentations. Visual only — coordinates stay live.
  mapTheme: (typeof localStorage !== 'undefined' && localStorage.getItem('safework_map_theme')) || 'SITE',

  setMapTheme: (mapTheme) => {
    try { localStorage.setItem('safework_map_theme', mapTheme); } catch { /* private mode */ }
    set({ mapTheme });
  },

  toggleNodeVisibility: (id) => set((s) => ({
    hiddenNodes: { ...s.hiddenNodes, [id]: !s.hiddenNodes[id] }
  })),

  setWorkers: (workers, zones, hiddenNodes) => set((s) => ({
    workers: workers.reduce((acc, w) => ({ ...acc, [w.worker_id]: w }), {}),
    zones: zones || s.zones,
    hiddenNodes: hiddenNodes || s.hiddenNodes,
    lastUpdate: Date.now(),
    isConnected: true
  })),

  setAnchors: (anchors, uwbConfig) => set((s) => ({
    anchors: Array.isArray(anchors) ? anchors : s.anchors,
    uwbConfig: uwbConfig || s.uwbConfig,
  })),
  setPersonnel: (personnel) => set((s) => ({
    personnel: Array.isArray(personnel) ? personnel : s.personnel,
  })),
  setHoveredZone: (zone) => set({ hoveredZone: zone }),
  setSystemTime: (t) => set({ systemTime: t }),
  setConnected: (v) => set({ isConnected: v }),
}));

// Display name resolution: registry first, raw tag id as fallback.
export const workerName = (personnel, workerId) =>
  personnel.find((p) => p.id === workerId)?.name || workerId;

export default useStore;
