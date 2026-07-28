import { useEffect } from 'react';
import useStore from '../store';
import { io } from 'socket.io-client';
import { DEMO_GAS_ENABLED, DEMO_GAS_TICK_MS } from '../lib/demoZoneGas';

const API_BASE = '/api';
const STATUS_REFRESH_MS = 5000;
const ANCHOR_REFRESH_MS = 30000;
const PERSONNEL_REFRESH_MS = 60000;

export default function useWorkerData() {
  const setWorkers = useStore(s => s.setWorkers);
  const setAnchors = useStore(s => s.setAnchors);
  const setPersonnel = useStore(s => s.setPersonnel);
  const setConnected = useStore(s => s.setConnected);

  useEffect(() => {
    let disposed = false;

    // Socket.IO is the low-latency path. REST remains a bounded fallback for
    // startup races, backend restarts, and proxies that allow HTTP but lose a
    // websocket upgrade. Without it, a failed first request left the map blank
    // until a browser refresh or the next successful socket event.
    const refreshStatus = async () => {
      try {
        const response = await fetch('/latest_status');
        if (!response.ok) return;
        const data = await response.json();
        if (!disposed && Array.isArray(data?.workers)) {
          setWorkers(data.workers, data.zones, data.hiddenNodes);
        }
      } catch {
        // Keep the last known dashboard state while the backend comes online.
      }
    };

    // Registered names drive every label on screen; refresh occasionally so
    // registry edits propagate without a reload.
    const refreshPersonnel = async () => {
      try {
        const response = await fetch(`${API_BASE}/personnel`);
        if (!response.ok) return;
        const data = await response.json();
        if (!disposed && Array.isArray(data)) {
          setPersonnel(data);
        }
      } catch {
        // Names fall back to raw tag ids until the next refresh succeeds.
      }
    };

    // The backend currently exposes anchors through REST and does not emit an
    // `anchors_updated` event. Retrying prevents a single frontend-before-
    // backend startup race from leaving the live map without its anchor frame.
    const refreshAnchors = async () => {
      try {
        const response = await fetch(`${API_BASE}/anchors`);
        if (!response.ok) return;
        const data = await response.json();
        if (!disposed && Array.isArray(data?.anchors)) {
          setAnchors(data.anchors, data.uwb);
        }
      } catch {
        // A later refresh retries transient proxy or backend failures.
      }
    };

    refreshStatus();
    refreshAnchors();
    refreshPersonnel();
    const statusRefresh = setInterval(refreshStatus, STATUS_REFRESH_MS);
    const anchorRefresh = setInterval(refreshAnchors, ANCHOR_REFRESH_MS);
    const personnelRefresh = setInterval(refreshPersonnel, PERSONNEL_REFRESH_MS);

    // Generated gas readings drift on their own clock. Without this they would
    // only move when a telemetry packet lands, so a quiet backend would leave
    // the environmental panel frozen mid-demo.
    const demoGasTick = DEMO_GAS_ENABLED
      ? setInterval(() => useStore.getState().tickDemoZones(), DEMO_GAS_TICK_MS)
      : null;

    // Connect WebSocket
    const socket = io('/', { path: '/socket.io' }); // Proxied via vite config

    socket.on('connect', () => {
      setConnected(true);
    });

    socket.on('disconnect', () => {
      setConnected(false);
    });

    socket.on('latest_status', (data) => {
      if (Array.isArray(data?.workers)) {
        setWorkers(data.workers, data.zones, data.hiddenNodes);
        setConnected(true);
      }
    });

    socket.on('anchors_updated', (data) => {
      if (Array.isArray(data?.anchors)) {
        setAnchors(data.anchors, data.uwb);
      }
    });

    return () => {
      disposed = true;
      clearInterval(statusRefresh);
      clearInterval(anchorRefresh);
      clearInterval(personnelRefresh);
      if (demoGasTick) clearInterval(demoGasTick);
      socket.disconnect();
    };
  }, [setWorkers, setAnchors, setPersonnel, setConnected]);
}
