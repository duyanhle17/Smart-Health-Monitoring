import { useState } from 'react';
import useStore, { workerName } from '../../store';

// Full-width red alarm strip shown on every page when a worker's pulse signal
// is lost (tag still online) or a tag stops reporting entirely. Acknowledging
// hides one worker's row until their state changes again.
export default function VitalsAlarmBanner() {
  const workers = useStore((s) => s.workers);
  const personnel = useStore((s) => s.personnel);
  const [acked, setAcked] = useState({});

  const lastReading = (w) => {
    const numeric = (w.history_hr || []).filter((v) => typeof v === 'number' && v > 0);
    return numeric.length ? Math.round(numeric[numeric.length - 1]) : null;
  };
  const timeOf = (ts) =>
    ts ? new Date(ts * 1000).toLocaleTimeString('en-GB', { hour12: false }) : '—';

  const alarms = Object.values(workers)
    .map((w) => {
      if (w.alert === 'OFFLINE') {
        return {
          key: `${w.worker_id}:offline:${Math.round(w.last_active || 0)}`,
          id: w.worker_id,
          kind: 'SIGNAL LOST',
          detail: `last contact ${timeOf(w.last_active)}`,
        };
      }
      if (w.pulse_lost === 'DANGER') {
        const hr = lastReading(w);
        return {
          key: `${w.worker_id}:pulse:${Math.round(w.last_pulse_at || 0)}`,
          id: w.worker_id,
          kind: 'PULSE LOST',
          detail: `${hr ? `last reading ${hr} BPM ` : ''}at ${timeOf(w.last_pulse_at)}`,
        };
      }
      return null;
    })
    .filter(Boolean)
    .filter((a) => !acked[a.key]);

  if (alarms.length === 0) return null;

  return (
    <div className="shrink-0 w-full flex flex-col max-h-44 overflow-y-auto border-b-4 border-black">
      {alarms.map((a) => (
        <div key={a.key} className="flex items-center justify-between gap-4 bg-brand-red text-white border-b-4 border-black px-6 py-2 animate-alarm-flash">
          <div className="flex items-center gap-3 font-heavy uppercase text-sm tracking-wider">
            <span className="material-symbols-outlined">emergency_heat</span>
            {a.kind} — {workerName(personnel, a.id)} ({a.id}) — {a.detail} — CHECK ON WORKER IMMEDIATELY
          </div>
          <button
            onClick={() => setAcked((prev) => ({ ...prev, [a.key]: true }))}
            className="shrink-0 border-2 border-white px-4 py-1 font-heavy uppercase text-[10px] hover:bg-white hover:text-brand-red transition-colors"
          >
            Acknowledge
          </button>
        </div>
      ))}
    </div>
  );
}
