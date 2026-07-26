import { BorderCard } from '../ui/BorderCard';
import { AlertBadge } from '../ui/AlertBadge';
import useStore, { workerName } from '../../store';

const statusMap = {
  DANGER: { text: 'DANGER', status: 'alert' },
  WARNING: { text: 'WARNING', status: 'alert' },
  NORMAL: { text: 'STABLE', status: 'stable' },
  FALL: { text: 'FALL DETECTED', status: 'alert' },
  OFFLINE: { text: 'SIGNAL LOST', status: 'alert' },
  PULSE_LOST: { text: 'PULSE LOST', status: 'alert' },
  NO_PULSE: { text: 'NO PULSE READING', status: 'alert' },
};

export default function LeftSidebar() {
  const workers = useStore(s => s.workers);
  const personnel = useStore(s => s.personnel);
  const hiddenNodes = useStore(s => s.hiddenNodes);

  const workerList = Object.values(workers).filter(w => !hiddenNodes[w.worker_id]);
  const onlineCount = workerList.filter(w => w.alert !== 'OFFLINE').length;
  const registeredCount = personnel.length;

  // Sort: DANGER/OFFLINE first, then WARNING, then NORMAL
  const sorted = [...workerList].sort((a, b) => {
    const getPriority = (w) => {
      if (w.alert === 'OFFLINE') return 0;
      if (w.alert === 'DANGER' || w.fall_status === 'FALL') return 1;
      if (w.alert === 'WARNING') return 2;
      return 3;
    };
    return getPriority(a) - getPriority(b);
  });

  return (
    <aside className="w-80 shrink-0 min-h-0 flex flex-col bg-white border-r-4 border-black">
      <div className="p-4 bg-black text-white flex justify-between items-end">
        <div>
          <h2 className="font-headline font-heavy text-sm uppercase leading-none">PERSONNEL</h2>
          <span className="font-label text-[8px] opacity-70 uppercase">ONLINE / REGISTERED</span>
        </div>
        <span className="font-headline text-xl font-heavy tabular-nums">{onlineCount}/{registeredCount}</span>
      </div>

      <div className="flex-1 overflow-y-auto custom-scrollbar">
        {sorted.length === 0 && (
          <div className="p-8 text-center text-gray-400 font-headline text-xs uppercase">
            Waiting for telemetry...
          </div>
        )}

        {sorted.map(w => {
          const isOffline = w.alert === 'OFFLINE';
          const isDanger = w.alert === 'DANGER' || w.fall_status === 'FALL' || isOffline;

          // Signal loss outranks everything; a frozen pulse-loss flag on a
          // silent tag must not mislabel the failure mode.
          let alertInfo = isOffline
            ? statusMap.OFFLINE
            : w.fall_status === 'FALL'
              ? statusMap.FALL
              : w.pulse_lost === 'DANGER'
                ? statusMap.PULSE_LOST
                : w.pulse_lost === 'WARNING'
                  ? statusMap.NO_PULSE
                  : (statusMap[w.alert] || statusMap.NORMAL);

          const hr = (isOffline || w.hr === '--' || w.hr === 0) ? '--' : Math.round(w.hr);
          const temp = (isOffline || w.temp === '--' || w.temp === 0) ? '--' : Number(w.temp).toFixed(1);
          const displayName = workerName(personnel, w.worker_id);
          const uwb = w.uwb || null;
          const hasRanges = Number.isFinite(Number(uwb?.d1_m)) && Number.isFinite(Number(uwb?.d2_m));
          const isLineEstimate = Boolean(
            w.location_degraded || uwb?.degraded || uwb?.geometry_mode === 'line'
          );
          const isLowGeometry = !isLineEstimate && w.location_valid === true && Boolean(
            uwb?.low_geometry || uwb?.branch_ambiguous
          );
          const isDirectRangeFusion = uwb?.fusion_mode === 'direct_two_range_ekf';
          const isUncalibratedLiveEstimate = w.location_valid === true && w.location_calibrated === false;
          const calibration = w.uwb_calibration;
          const calibrationProgress = calibration
            ? `CAL: ${calibration.accepted_samples || 0}/${calibration.required_samples || '?'}${calibration.ready ? ' · REVIEW OFFSETS' : ' · HOLD STILL'}`
            : null;
          // Operator-facing 3-tier position status; the engineering detail
          // lives in the hover tooltip, not on the card.
          const uwbDetail = !uwb
            ? 'No UWB ranges received yet'
            : w.location_last_known
              ? (isLineEstimate ? 'Last known 1-D line estimate, awaiting range recovery' : 'Last known fix, awaiting range recovery')
              : w.location_stale
              ? (isLineEstimate ? 'Holding last 1-D line estimate through an RF dropout' : 'Holding last fix through an RF dropout')
              : isLineEstimate
                ? 'On-baseline deployment: along-line coordinate only (1-D)'
              : isLowGeometry
                ? 'Close to the anchor baseline: cross-track coordinate weakly observed'
              : isUncalibratedLiveEstimate
                ? (isDirectRangeFusion ? 'Two-range EKF running; link offsets not yet surveyed' : 'Live estimate; link offsets not yet surveyed')
              : w.location_valid
              ? (isDirectRangeFusion ? 'Two-range EKF, calibrated' : 'Two-circle fix, calibrated')
              : !uwb.valid
                ? uwb.reason === 'ranges_shorter_than_anchor_baseline'
                  ? 'Range pair shorter than the anchor baseline'
                  : 'No valid two-circle fix'
                : 'Calibration required';
          const uwbLabel = !uwb || (w.location_valid !== true && !w.location_last_known)
            ? 'POSITION: AWAITING'
            : w.location_last_known
              ? 'POSITION: LAST KNOWN'
              : (isLineEstimate || isLowGeometry || isUncalibratedLiveEstimate || w.location_stale)
                ? 'POSITION: DEGRADED'
                : 'POSITION: LOCKED';
          const uwbTone = w.location_last_known || !w.location_valid
            ? 'text-gray-600'
            : w.location_valid && !isLineEstimate && !isLowGeometry && !isUncalibratedLiveEstimate && !w.location_stale
              ? 'text-green-700'
              : 'text-orange-700';
          const ex = typeof w.exhaustion_score === 'number' ? w.exhaustion_score : null;
          const exLevel = w.exhaustion_status || null;
          const exTone = exLevel === 'SEVERE' ? 'text-brand-red' : exLevel === 'MODERATE' ? 'text-orange-600' : exLevel === 'MILD' ? 'text-yellow-600' : '';
          const tempLabel = w.temp_source === 'max30205'
            ? (w.temp_fresh ? 'BODY TEMP · LIVE' : 'BODY TEMP · CACHED')
            : w.temp_source === 'max30102_chip'
              ? 'DEVICE TEMP (APPROX)'
              : 'TEMP SOURCE UNKNOWN';

          return (
            <div key={w.worker_id} className={`p-4 border-b-2 border-black flex flex-col gap-3 ${isDanger ? 'bg-red-100/50' : 'hover:bg-gray-100'} ${isOffline ? 'animate-glitch opacity-80' : ''}`}>
              <div className="flex gap-3">
                <div className={`w-12 h-12 ${isDanger ? 'bg-brand-red' : 'bg-black'} ${isOffline ? 'bg-gray-700' : ''} flex items-center justify-center text-white text-[10px] font-heavy shrink-0 transition-colors`}>
                  {w.worker_id.replace('WK_', '')}
                </div>
                <div className="flex-1 overflow-hidden">
                  <div className="flex justify-between items-center mb-1">
                    <span className={`font-headline font-heavy text-xs uppercase truncate ${isDanger && !isOffline ? 'text-brand-red' : ''} ${isOffline ? 'text-gray-500 line-through' : ''}`}>
                      {displayName}
                    </span>
                    <span className="font-label text-[8px] text-gray-500 ml-2">{w.worker_id}</span>
                  </div>
                  <AlertBadge text={alertInfo.text} status={alertInfo.status} />
                </div>
              </div>
              <div className={`grid grid-cols-3 gap-2 ${isOffline ? 'opacity-50 grayscale' : ''}`}>
                <BorderCard className={`p-2 border-2 ${isDanger && !isOffline ? 'border-brand-red bg-white' : ''}`}>
                  <span className={`block font-label text-[8px] font-heavy ${isDanger && !isOffline ? 'text-brand-red' : ''} opacity-60`}>BPM</span>
                  <span className={`font-headline text-xl font-heavy tabular-nums ${isDanger && !isOffline ? 'text-brand-red' : ''}`}>{hr}</span>
                </BorderCard>
                <BorderCard className={`p-2 border-2 ${isDanger && !isOffline ? 'border-brand-red bg-white' : ''}`}>
                  <span className={`block font-label text-[8px] font-heavy ${isDanger && !isOffline ? 'text-brand-red' : ''} opacity-60`}>TEMP</span>
                  <span className={`font-headline text-xl font-heavy tabular-nums ${isDanger && !isOffline ? 'text-brand-red' : ''}`}>{temp}°</span>
                </BorderCard>
                <BorderCard className={`p-2 border-2 ${exLevel === 'SEVERE' ? 'border-brand-red bg-white' : ''}`} tooltip={exLevel ? `Fatigue level: ${exLevel}` : 'Fatigue score unavailable'}>
                  <span className="block font-label text-[8px] font-heavy opacity-60">FATIGUE</span>
                  <span className={`font-headline text-xl font-heavy tabular-nums ${exTone}`}>{ex !== null ? ex.toFixed(1) : '--'}</span>
                </BorderCard>
              </div>
              {!isOffline && (
                <div className="border-l-2 border-black pl-2 text-[8px] font-heavy uppercase leading-4">
                  <div className={uwbTone} title={uwbDetail}>{uwbLabel}{hasRanges ? ` · ${Number(uwb.d1_m).toFixed(2)}m / ${Number(uwb.d2_m).toFixed(2)}m` : ''}</div>
                  {calibrationProgress && <div className="text-orange-700">{calibrationProgress}</div>}
                  <div className="text-gray-500">{tempLabel}</div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </aside>
  );
}
