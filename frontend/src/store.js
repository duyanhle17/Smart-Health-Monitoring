import { create } from 'zustand';

const useStore = create((set) => ({
  workers: {},
  zones: {}, // Store zone-wide env data
  anchors: [],
  hoveredZone: null,
  systemTime: null,
  isConnected: false,
  lastUpdate: null,

  setWorkers: (workersList, zonesData) => {
    const map = {};
    workersList.forEach(w => { map[w.worker_id] = w; });
    set({ 
      workers: map, 
      zones: zonesData || {}, 
      lastUpdate: Date.now(), 
      isConnected: true 
    });
  },

  setAnchors: (anchors) => set({ anchors }),
  setHoveredZone: (zone) => set({ hoveredZone: zone }),
  setSystemTime: (t) => set({ systemTime: t }),
  setConnected: (v) => set({ isConnected: v }),
}));

export default useStore;
