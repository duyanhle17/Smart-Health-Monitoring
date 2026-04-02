import { useEffect, useRef } from 'react';
import useStore from '../store';
import { io } from 'socket.io-client';

const API_BASE = '/api';

export default function useWorkerData() {
  const setWorkers = useStore(s => s.setWorkers);
  const setAnchors = useStore(s => s.setAnchors);
  const setConnected = useStore(s => s.setConnected);
  const anchorsLoaded = useRef(false);

  useEffect(() => {
    // Load anchors once via REST
    if (!anchorsLoaded.current) {
      fetch(`${API_BASE}/anchors`)
        .then(r => r.json())
        .then(data => {
          if (data.anchors) setAnchors(data.anchors);
          anchorsLoaded.current = true;
        })
        .catch(() => {});
    }

    // Connect WebSocket
    const socket = io('/', { path: '/socket.io' }); // Proxied via vite config

    socket.on('connect', () => {
      setConnected(true);
    });

    socket.on('disconnect', () => {
      setConnected(false);
    });

    socket.on('latest_status', (data) => {
      if (data.workers) {
        setWorkers(data.workers, data.zones);
        setConnected(true);
      }
    });

    socket.on('anchors_updated', (data) => {
      if (data.anchors) {
        setAnchors(data.anchors);
      }
    });

    return () => socket.disconnect();
  }, [setWorkers, setAnchors, setConnected]);
}
