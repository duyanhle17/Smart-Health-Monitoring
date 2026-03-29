import { useEffect, useRef } from 'react';
import useStore from '../store';

const API_BASE = '/api';
const POLL_INTERVAL = 800; // ms

export default function useWorkerData() {
  const setWorkers = useStore(s => s.setWorkers);
  const setAnchors = useStore(s => s.setAnchors);
  const setConnected = useStore(s => s.setConnected);
  const anchorsLoaded = useRef(false);

  useEffect(() => {
    // Load anchors once
    if (!anchorsLoaded.current) {
      fetch(`${API_BASE}/anchors`)
        .then(r => r.json())
        .then(data => {
          if (data.anchors) setAnchors(data.anchors);
          anchorsLoaded.current = true;
        })
        .catch(() => {});
    }

    // Poll workers
    const poll = async () => {
      try {
        const res = await fetch('/latest_status');
        const data = await res.json();
        if (data.workers) {
          setWorkers(data.workers);
        }
      } catch {
        setConnected(false);
      }
    };

    poll(); // initial
    const id = setInterval(poll, POLL_INTERVAL);
    return () => clearInterval(id);
  }, [setWorkers, setAnchors, setConnected]);
}
