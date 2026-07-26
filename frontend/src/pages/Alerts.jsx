import { useMemo } from 'react';
import useStore, { workerName } from '../store';

// Zone alerts carry no event timestamp from the backend yet, so stamp each
// alert id the first time it appears instead of re-stamping every render.
// Module scope keeps the stamps stable across re-renders and navigation.
const firstSeen = {};
const stampOnce = (id) => {
  if (!firstSeen[id]) {
    firstSeen[id] = new Date().toLocaleTimeString('en-GB', { hour12: false });
  }
  return firstSeen[id];
};

export default function Alerts() {
  const workers = useStore(s => s.workers);
  const zones = useStore(s => s.zones);
  const personnel = useStore(s => s.personnel);

  const workerList = Object.values(workers);

  const activeAlerts = useMemo(() => {
    const alerts = [];

    // Check zone alerts
    Object.entries(zones).forEach(([zoneId, data]) => {
      if (data.status === 'DANGER' || data.status === 'WARNING') {
        alerts.push({
          id: `zone-${zoneId}`,
          level: data.status,
          time: stampOnce(`zone-${zoneId}-${data.status}`),
          msg: `Toxic Gas Alert (${data.ch4} CH4, ${data.co} CO) detected in ${zoneId.replace('_', ' ')}`
        });
      }
    });

    // Check worker alerts
    workerList.forEach(w => {
      if (w.alert === 'DANGER' || w.alert === 'WARNING' || w.alert === 'OFFLINE' || w.fall_status === 'FALL') {
        const name = workerName(personnel, w.worker_id);
        const level = (w.alert === 'DANGER' || w.fall_status === 'FALL') ? 'CRITICAL WARNING' : w.alert;
        // Precedence: signal loss overrides a frozen pulse-loss flag so the
        // log keeps the last-known-location line responders need.
        let msg = `Health/safety anomaly detected for ${name} (${w.zone || 'UNKNOWN ZONE'})`;
        if (w.pulse_lost === 'DANGER') msg = `Pulse signal lost for worker ${name}. Check on worker immediately.`;
        if (w.alert === 'OFFLINE') msg = `Signal lost for worker ${name}. Last known location: ${w.zone || 'UNKNOWN'}`;
        if (w.fall_status === 'FALL') msg = `IMPACT / FALL DETECTED for worker ${name}. Immediate assistance required.`;

        alerts.push({
          id: `worker-${w.worker_id}`,
          level: level.toUpperCase(),
          // Stamp the episode's first appearance — last_active advances with
          // every telemetry packet and would make the time tick each second.
          time: stampOnce(`worker-${w.worker_id}-${level}`),
          msg: msg
        });
      }
    });

    return alerts;
  }, [workerList, zones, personnel]);

  return (
    <div className="p-8 h-full bg-gray-100 flex flex-col">
      <h1 className="text-3xl font-heavy border-b-4 border-brand-red pb-4 mb-8 uppercase tracking-tighter text-brand-red flex items-center gap-4">
        <span className="material-symbols-outlined text-4xl animate-ping" data-icon="warning">warning</span>
        INCIDENT & ALERTS LOGS
      </h1>
      <div className="flex flex-col gap-4 overflow-auto">
        {activeAlerts.length === 0 ? (
          <div className="text-center py-12 text-gray-500 font-heavy uppercase tracking-widest border-4 border-gray-300 border-dashed">
            ALL SYSTEMS NOMINAL. NO ACTIVE ALERTS.
          </div>
        ) : (
          activeAlerts.map((alert) => (
            <div key={alert.id} className="bg-white border-4 border-brand-red p-4 border-l-8 flex justify-between items-center transition-all hover:bg-gray-50">
              <div>
                <div className="flex items-center gap-3 mb-2">
                  <span className={`text-white text-[10px] uppercase font-heavy px-2 py-0.5 animate-pulse ${alert.level.includes('CRITICAL') || alert.level === 'DANGER' ? 'bg-brand-red' : 'bg-orange-600'}`}>{alert.level}</span>
                  <span className="font-headline text-xs text-black">TODAY, {alert.time}</span>
                </div>
                <p className="font-heavy uppercase text-xl">{alert.msg}</p>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
