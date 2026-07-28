import { useCallback, useEffect, useRef, useState } from 'react';
import FlatMap from '../components/map/FlatMap';
import Joystick from '../components/map/Joystick';
import { PinGate } from './AdminPanel';
import { advancePosition, isCentred, jitterOffset } from '../lib/joystickMotion';
import { adminPost, clearAdminPin, getAdminPin, verifyAdminPin } from '../lib/adminApi';
import useStore, { workerName } from '../store';

/** One save fires this long after the stick returns to centre. */
export const COMMIT_DEBOUNCE_MS = 500;

/**
 * The phone presentation of the admin console: a flat map and nothing else.
 *
 * The vitals alarm banner is deliberately absent — this screen is a placement
 * tool, not a monitoring station, and that was a considered choice. Monitoring
 * stays on the desktop dashboard.
 */
export default function MobileAdminMap({ onOpenFullConsole }) {
  const workers = useStore((s) => s.workers);
  const personnel = useStore((s) => s.personnel);

  const [unlocked, setUnlocked] = useState(false);
  const [checking, setChecking] = useState(true);
  const [selectedId, setSelectedId] = useState(null);
  const [overrides, setOverrides] = useState({});
  const [uncommittedIds, setUncommittedIds] = useState(new Set());

  const vectorRef = useRef({ x: 0, y: 0 });
  const frameRef = useRef(null);
  const commitTimerRef = useRef(null);

  // Where the selected worker sat when this placement session began. The
  // joystick is leashed to it, so a long push corrects a position rather than
  // teleporting the worker across the site.
  const anchorRef = useRef(null);

  // Cosmetic wobble on the worker under the joystick. Held in state purely so
  // the frame loop can repaint it; it never touches the committed coordinate.
  const [jitter, setJitter] = useState(null);

  // The stored PIN is a convenience, not an authorization: re-verify against
  // the backend on mount, exactly as the desktop console does.
  useEffect(() => {
    verifyAdminPin(getAdminPin())
      .then((ok) => setUnlocked(ok))
      .catch(() => setUnlocked(false))
      .finally(() => setChecking(false));
  }, []);

  // The position is passed in rather than looked up, so a commit can never race
  // a parent render that has not landed yet.
  const commit = useCallback(async (workerId, position) => {
    if (!position) return;
    try {
      const res = await adminPost('/api/admin/node', {
        worker_id: workerId,
        x: position.x.toFixed(1),
        y: position.y.toFixed(1),
      });
      if (res.status === 403) {
        clearAdminPin();
        setUnlocked(false);
        return;
      }
      if (!res.ok) {
        // Keep the operator's placement on screen and flag it. Snapping the dot
        // back without a word would read as "saved".
        setUncommittedIds((prev) => new Set(prev).add(workerId));
        return;
      }
      setUncommittedIds((prev) => {
        const next = new Set(prev);
        next.delete(workerId);
        return next;
      });
      // The backend override now owns the coordinate; drop the local overlay so
      // the next socket update renders server truth.
      setOverrides((prev) => {
        const next = { ...prev };
        delete next[workerId];
        return next;
      });
    } catch {
      setUncommittedIds((prev) => new Set(prev).add(workerId));
    }
  }, []);

  const scheduleCommit = useCallback((workerId, position) => {
    clearTimeout(commitTimerRef.current);
    commitTimerRef.current = setTimeout(() => commit(workerId, position), COMMIT_DEBOUNCE_MS);
  }, [commit]);

  // Anchor the leash the moment a worker is selected, and drop any wobble left
  // over from the previous selection. Reading the anchor from the store keeps
  // this effect off the `overrides` identity, which changes every frame while
  // the joystick is held.
  // No need to clear the wobble here: jitterFor below only hands it to the
  // selected worker, so with nothing selected it reaches nobody.
  useEffect(() => {
    if (!selectedId) {
      anchorRef.current = null;
      return;
    }
    const worker = useStore.getState().workers[selectedId] || { x: 0, y: 0 };
    anchorRef.current = { x: Number(worker.x) || 0, y: Number(worker.y) || 0 };
  }, [selectedId]);

  // A held thumb fires no further pointer events, so the stick's last vector is
  // applied every frame here rather than on input. The same loop drives the
  // wobble, which only runs while the stick is actually deflected.
  useEffect(() => {
    if (!selectedId) return undefined;
    let last = performance.now();
    const step = (now) => {
      const dtMs = now - last;
      last = now;
      const vector = vectorRef.current;
      if (isCentred(vector)) {
        setJitter(null);
      } else {
        setJitter(jitterOffset(now));
        setOverrides((prev) => {
          const worker = useStore.getState().workers[selectedId];
          if (!worker) return prev;
          const from = prev[selectedId] || { x: Number(worker.x) || 0, y: Number(worker.y) || 0 };
          return {
            ...prev,
            [selectedId]: advancePosition(from, vector, dtMs, anchorRef.current),
          };
        });
      }
      frameRef.current = requestAnimationFrame(step);
    };
    frameRef.current = requestAnimationFrame(step);
    return () => cancelAnimationFrame(frameRef.current);
  }, [selectedId]);

  useEffect(() => () => clearTimeout(commitTimerRef.current), []);

  // Only the worker under the joystick wobbles. Every other dot keeps showing
  // exactly what the server reported.
  const jitterFor = useCallback(
    (workerId) => (workerId === selectedId ? jitter : null),
    [selectedId, jitter]
  );

  const handleDragMove = useCallback((workerId, position) => {
    setOverrides((prev) => ({ ...prev, [workerId]: position }));
  }, []);

  const handleDragEnd = useCallback((workerId, position) => {
    clearTimeout(commitTimerRef.current);
    commit(workerId, position);
  }, [commit]);

  if (checking) {
    return (
      <div className="w-full h-full flex justify-center items-center bg-gray-100">
        <span className="font-heavy uppercase text-xs tracking-widest text-gray-400">
          Checking admin access…
        </span>
      </div>
    );
  }
  if (!unlocked) return <PinGate onUnlocked={() => setUnlocked(true)} />;

  const selectionIsLive = Boolean(selectedId && workers[selectedId]);

  return (
    <div className="w-full h-full relative bg-gray-200 overflow-hidden">
      <FlatMap
        selectedId={selectedId}
        onSelect={setSelectedId}
        overrides={overrides}
        uncommittedIds={uncommittedIds}
        jitterFor={jitterFor}
        onDragMove={handleDragMove}
        onDragEnd={handleDragEnd}
      />

      <button
        data-testid="open-full-console"
        onClick={onOpenFullConsole}
        className="absolute top-4 left-4 z-30 bg-white border-4 border-black px-3 py-2 font-heavy uppercase text-[10px] tracking-widest"
      >
        Console
      </button>

      {selectionIsLive && (
        <div className="absolute bottom-8 left-6 z-30">
          <Joystick
            label={workerName(personnel, selectedId)}
            onVector={(vector) => { vectorRef.current = vector; }}
            onRelease={() => scheduleCommit(selectedId, overrides[selectedId])}
          />
        </div>
      )}
    </div>
  );
}
