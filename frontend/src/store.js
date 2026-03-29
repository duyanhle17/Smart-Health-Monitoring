import { create } from 'zustand';

const useStore = create((set) => ({
  workers: {},
  anchors: [],
  systemTime: null,
  isConnected: false,
  lastUpdate: null,

  setWorkers: (workersList) => {
    const map = {};
    workersList.forEach(w => { map[w.worker_id] = w; });
    set({ workers: map, lastUpdate: Date.now(), isConnected: true });
  },

  setAnchors: (anchors) => set({ anchors }),
  setSystemTime: (t) => set({ systemTime: t }),
  setConnected: (v) => set({ isConnected: v }),
}));

export default useStore;
