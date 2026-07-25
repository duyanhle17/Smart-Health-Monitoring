import { create } from 'zustand';

const useStore = create((set) => ({
  workers: {},
  zones: {}, // Store zone-wide env data
  anchors: [],
  // Server-authoritative assumptions for the physical UWB coordinate frame.
  // In particular, `anchor_baseline_m` is the tape-measured distance used by
  // the backend solver, not a visual distance inferred from the 3-D map.
  uwbConfig: null,
  hoveredZone: null,
  systemTime: null,
  isConnected: false,
  lastUpdate: null,
  scenario: 'NORMAL',
  mapMode: 'NORMAL', // NORMAL | LOBBY | ELEVATED — controls map geometry
  isSimulation: false,
  hiddenNodes: {}, // Support toggling global visibility
  customAnchors: {}, // Sync dragged anchor positions from backend

  toggleNodeVisibility: (id) => set((s) => ({
    hiddenNodes: { ...s.hiddenNodes, [id]: !s.hiddenNodes[id] }
  })),

  setIsSimulation: (v) => set({ isSimulation: v }),
  setScenario: (scenario) => set({ scenario }),
  setMapMode: (mapMode) => set({ mapMode }),

  setWorkers: (workers, zones, hiddenNodes, customAnchors) => set((s) => ({
    workers: workers.reduce((acc, w) => ({ ...acc, [w.worker_id]: w }), {}),
    zones: zones || s.zones,
    hiddenNodes: hiddenNodes || s.hiddenNodes,
    customAnchors: customAnchors || s.customAnchors,
    lastUpdate: Date.now(),
    isConnected: true
  })),

  setAnchors: (anchors, uwbConfig) => set((s) => ({
    anchors: Array.isArray(anchors) ? anchors : s.anchors,
    uwbConfig: uwbConfig || s.uwbConfig,
  })),
  setHoveredZone: (zone) => set({ hoveredZone: zone }),
  setSystemTime: (t) => set({ systemTime: t }),
  setConnected: (v) => set({ isConnected: v }),
}));

export default useStore;
