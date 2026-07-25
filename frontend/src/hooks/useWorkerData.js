import { useEffect } from 'react';
import useStore from '../store';
import { io } from 'socket.io-client';

const API_BASE = '/api';
const STATUS_REFRESH_MS = 5000;
const ANCHOR_REFRESH_MS = 30000;

export default function useWorkerData() {
  const setWorkers = useStore(s => s.setWorkers);
  const setAnchors = useStore(s => s.setAnchors);
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
          setWorkers(data.workers, data.zones, data.hiddenNodes, data.customAnchors);
        }
      } catch {
        // Keep the last known dashboard state while the backend comes online.
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
    const statusRefresh = setInterval(refreshStatus, STATUS_REFRESH_MS);
    const anchorRefresh = setInterval(refreshAnchors, ANCHOR_REFRESH_MS);

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
        setWorkers(data.workers, data.zones, data.hiddenNodes, data.customAnchors);
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
      socket.disconnect();
    };
  }, [setWorkers, setAnchors, setConnected]);
}
