import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import useStore from '../store';
import IsometricMap from '../components/map/IsometricMap';
import { adminPost, adminRequest, clearAdminPin, getAdminPin, setAdminPin, verifyAdminPin } from '../lib/adminApi';

function PinGate({ onUnlocked }) {
  const [pin, setPin] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError('');
    const ok = await verifyAdminPin(pin).catch(() => false);
    if (ok) {
      setAdminPin(pin);
      onUnlocked();
    } else {
      setError('Invalid PIN');
    }
    setBusy(false);
  };

  return (
    <div className="w-full h-full flex justify-center items-center bg-gray-100">
      <form onSubmit={submit} className="border-4 border-black bg-white p-8 flex flex-col items-center w-96 shadow-[8px_8px_0px_0px_rgba(0,0,0,1)]">
        <h1 className="text-2xl font-heavy mb-2 uppercase tracking-tighter">ADMIN CONSOLE</h1>
        <p className="font-label text-xs uppercase mb-6 border-b-2 border-black pb-2 w-full text-center">Enter admin PIN</p>
        <input
          type="password"
          value={pin}
          onChange={(e) => setPin(e.target.value)}
          placeholder="PIN"
          autoFocus
          className="border-2 border-black p-3 mb-4 w-full bg-gray-100 font-headline uppercase"
        />
        {error && <p className="text-brand-red font-heavy text-xs uppercase mb-4">{error}</p>}
        <button type="submit" disabled={busy} className="w-full bg-black text-white py-3 font-heavy uppercase tracking-wider hover:bg-gray-800 border-2 border-black disabled:opacity-50">
          {busy ? 'CHECKING…' : 'UNLOCK'}
        </button>
        <Link
          to="/dashboard"
          className="mt-3 w-full text-center border-2 border-black py-2 text-[10px] font-heavy uppercase tracking-widest hover:bg-black hover:text-white transition-colors"
        >
          ← Back to dashboard
        </Link>
      </form>
    </div>
  );
}

export default function AdminPanel() {
  const workers = useStore(s => s.workers);
  const anchors = useStore(s => s.anchors);
  const hiddenNodes = useStore(s => s.hiddenNodes);
  // The stored PIN is a convenience, not an authorization: re-verify it
  // against the backend on every mount before opening the console.
  const [unlocked, setUnlocked] = useState(false);
  const [checking, setChecking] = useState(true);
  const [adminError, setAdminError] = useState('');

  useEffect(() => {
    verifyAdminPin(getAdminPin())
      .then(ok => setUnlocked(ok))
      .catch(() => setUnlocked(false))
      .finally(() => setChecking(false));
  }, []);

  // Custom states for the manual override form
  const [selectedTarget, setSelectedTarget] = useState('');
  const [overrideForm, setOverrideForm] = useState({ alert: 'NORMAL', x: '', y: '', ch4: '', co: '' });
  // UWB known-point calibration capture: start / monitor / clear.
  const [calibForm, setCalibForm] = useState({ worker: '', d1: '1.000', d2: '1.000' });

  const currentWorkers = Object.values(workers);
  const currentAnchors = anchors;
  const diagWorker = currentWorkers[0] || null;

  // Every admin write funnels through here so a rejected PIN relocks the
  // console instead of failing silently in the console log.
  const runAdmin = async (url, body) => {
    const res = await adminPost(url, body);
    if (res.status === 403) {
      clearAdminPin();
      setUnlocked(false);
      setAdminError('Admin PIN was rejected by the server — unlock again.');
      throw new Error('admin-pin-rejected');
    }
    if (!res.ok) {
      const e = await res.json().catch(() => ({}));
      setAdminError(e.msg || `Request failed (${res.status})`);
      throw new Error('admin-request-failed');
    }
    setAdminError('');
    return res;
  };

  const handleToggle = async (id) => {
      // Optimistic update for absolute instant UI response
      useStore.getState().toggleNodeVisibility(id);
      try {
          await runAdmin('/api/admin/toggle_node', { node_id: id });
      } catch (err) {
          console.error(err);
          // Revert if failed
          useStore.getState().toggleNodeVisibility(id);
      }
  };

  const handleForceFallStatus = async (status) => {
    if (!diagWorker) return;
    try {
      await runAdmin('/api/admin/node', { worker_id: diagWorker.worker_id, fall_status: status });
    } catch (e) {
      console.error(e);
    }
  };

  const handleAdminSubmit = async (e) => {
    e.preventDefault();
    if (!selectedTarget) return;
    try {
      const payload = { ...overrideForm };
      if (!payload.x) delete payload.x;
      if (!payload.y) delete payload.y;
      if (!payload.ch4) delete payload.ch4;
      if (!payload.co) delete payload.co;

      if (selectedTarget.startsWith('ANC_')) {
          payload.anchor_id = selectedTarget;
          delete payload.alert;
      } else {
          payload.worker_id = selectedTarget;
      }

      await runAdmin('/api/admin/node', payload);
    } catch (err) {
      console.error(err);
    }
  };

  const calibTarget = calibForm.worker || currentWorkers[0]?.worker_id || '';
  const calibStatus = workers[calibTarget]?.uwb_calibration;

  const handleStartCalibration = async (e) => {
    e.preventDefault();
    if (!calibTarget) return;
    try {
      await runAdmin('/api/uwb/calibration/start', {
        worker_id: calibTarget,
        known_d1_m: parseFloat(calibForm.d1),
        known_d2_m: parseFloat(calibForm.d2),
      });
    } catch (err) { console.error(err); }
  };

  const handleClearCalibration = async () => {
    if (!calibTarget) return;
    try { await adminRequest(`/api/uwb/calibration/${calibTarget}`, 'DELETE'); } catch (err) { console.error(err); }
  };

  const handleApplyCalibration = async () => {
    if (!calibTarget) return;
    try { await runAdmin('/api/uwb/calibration/apply', { worker_id: calibTarget }); } catch (err) { console.error(err); }
  };

  const handleClearOverride = async () => {
    if (!selectedTarget) return;
    const payload = selectedTarget.startsWith('ANC_')
      ? { anchor_id: selectedTarget }
      : { worker_id: selectedTarget };
    try {
      await runAdmin('/api/admin/clear_override', payload);
    } catch (err) {
      console.error(err);
    }
  };

  const handleLoadTarget = (id) => {
    setSelectedTarget(id);
    let newForm = { ...overrideForm, x: '', y: '' };
    if (id.startsWith('ANC_')) {
      const anchor = currentAnchors.find(a => a.id === id);
      if (anchor) {
        newForm.x = parseFloat(anchor.x).toFixed(1);
        newForm.y = parseFloat(anchor.y).toFixed(1);
      }
    } else {
      const worker = currentWorkers.find(w => w.worker_id === id);
      if (worker) {
        newForm.x = worker.x !== undefined ? parseFloat(worker.x).toFixed(1) : '';
        newForm.y = worker.y !== undefined ? parseFloat(worker.y).toFixed(1) : '';
        newForm.alert = worker.alert || 'NORMAL';
      }
    }
    setOverrideForm(newForm);
  };

  if (checking) {
    return (
      <div className="w-full h-full flex justify-center items-center bg-gray-100">
        <span className="font-heavy uppercase text-xs tracking-widest text-gray-400">Checking admin access…</span>
      </div>
    );
  }
  if (!unlocked) {
    return <PinGate onUnlocked={() => setUnlocked(true)} />;
  }

  return (
    <div className="w-full h-full flex bg-gray-100 overflow-hidden font-body text-black">
      {/* Left column: overrides & diagnostics */}
      <aside className="w-[450px] shrink-0 h-full border-r-4 border-black bg-white flex flex-col z-20 shadow-2xl relative custom-scrollbar overflow-y-auto pb-20">
        <div className="p-6 bg-black text-white">
          <div className="flex justify-between items-start">
            <h1 className="text-2xl font-heavy uppercase tracking-widest flex items-center gap-3">
              <span className="material-symbols-outlined text-brand-yellow">admin_panel_settings</span>
              ADMIN CONSOLE
            </h1>
            <Link
              to="/dashboard"
              className="shrink-0 flex items-center gap-1 border-2 border-white px-3 py-1.5 text-[10px] font-heavy uppercase tracking-widest hover:bg-white hover:text-black transition-colors"
            >
              <span className="material-symbols-outlined text-sm">arrow_back</span>
              Dashboard
            </Link>
          </div>
          <p className="text-xs uppercase mt-2 opacity-70 font-label tracking-wide">System overrides & commissioning tools</p>
        </div>

        {adminError && (
          <div className="px-6 py-3 bg-brand-red text-white font-heavy uppercase text-[10px] tracking-wider border-b-4 border-black">
            {adminError}
          </div>
        )}

        {/* Fall diagnostics for the first live tag */}
        <div className="p-6 border-b-4 border-black bg-blue-50 relative overflow-hidden">
          {diagWorker?.fall_status === 'FALL' && (
            <div className="absolute inset-0 bg-red-600/20 animate-pulse pointer-events-none z-0"></div>
          )}
          <h2 className="text-sm font-heavy uppercase mb-3 border-b-2 border-black pb-2 flex justify-between items-center relative z-10 transition-colors">
            Fall Diagnostics {diagWorker ? `· ${diagWorker.worker_id}` : ''}
            <span className={`text-[10px] px-2 py-1 flex items-center gap-1 ${(diagWorker?.fall_status || 'SAFE') === 'FALL' ? 'bg-red-600 text-white animate-pulse' : 'bg-green-600 text-white'}`}>
              {(diagWorker?.fall_status || 'SAFE') === 'FALL' ? 'FALL DETECTED!' : 'SAFE'}
            </span>
          </h2>
          <div className="flex flex-col gap-2 font-mono text-[10px] uppercase relative z-10">
            {['ax', 'ay', 'az'].map(axis => (
              <div key={axis} className="flex justify-between border-b border-black/20 pb-1">
                <span className="opacity-70">Acc {axis.charAt(1).toUpperCase()} :</span>
                <span className="font-heavy tabular-nums">
                  {diagWorker?.history_imu?.[axis]?.length > 0 ? diagWorker.history_imu[axis][diagWorker.history_imu[axis].length - 1].toFixed(2) : '0.00'}
                </span>
              </div>
            ))}
            {!diagWorker && (
               <div className="text-brand-red font-heavy animate-pulse mt-1">WAITING FOR DEVICE CONNECTION...</div>
            )}
            <div className="mt-2 text-gray-500 font-label normal-case text-xs leading-tight">
              Backend fall model receives the live IMU stream (10 Hz).<br/>
              Tilt & shake the wearable to trigger `FALL`.
            </div>

            <div className="flex gap-2 mt-2 pt-2 border-t border-black/20">
              <button
                onClick={() => handleForceFallStatus('SAFE')}
                disabled={!diagWorker}
                className="flex-1 py-1 px-2 border border-green-700 bg-white text-green-700 hover:bg-green-700 hover:text-white transition-colors text-[9px] font-heavy whitespace-nowrap disabled:opacity-40"
              >
                FORCE SAFE
              </button>
              <button
                onClick={() => handleForceFallStatus('FALL')}
                disabled={!diagWorker}
                className="flex-1 py-1 px-2 border border-red-700 bg-white text-red-700 hover:bg-red-700 hover:text-white transition-colors text-[9px] font-heavy whitespace-nowrap shadow-[0_0_8px_rgba(220,38,38,0.5)] disabled:opacity-40"
              >
                FORCE FALL
              </button>
            </div>
          </div>
        </div>

        {/* UWB known-point range calibration */}
        <div className="p-6 border-b-4 border-black bg-yellow-50">
          <h2 className="text-sm font-heavy uppercase mb-3 border-b-2 border-black pb-2">UWB Range Calibration</h2>
          <p className="text-xs font-label text-gray-600 leading-tight mb-3">
            Park the tag perfectly still at a known point (baseline midpoint: both
            distances = baseline ÷ 2), then start. The capture only produces a
            recommendation — offsets are applied in the server environment after review.
          </p>
          <form onSubmit={handleStartCalibration} className="flex flex-col gap-3">
            <label className="flex flex-col gap-1 font-heavy text-[10px] uppercase">
              Worker:
              <select
                className="border-2 border-black p-2 font-mono text-xs bg-white cursor-pointer"
                value={calibTarget}
                onChange={e => setCalibForm({ ...calibForm, worker: e.target.value })}
              >
                {currentWorkers.length === 0 && <option value="">-- no live workers --</option>}
                {currentWorkers.map(w => <option key={w.worker_id} value={w.worker_id}>{w.worker_id}</option>)}
              </select>
            </label>
            <div className="flex gap-2">
              <label className="flex-1 flex flex-col gap-1 font-heavy text-[10px] uppercase">
                True D1 (m):
                <input
                  type="number" step="0.001" min="0.05"
                  className="border-2 border-black p-2 font-mono text-xs bg-white"
                  value={calibForm.d1}
                  onChange={e => setCalibForm({ ...calibForm, d1: e.target.value })}
                />
              </label>
              <label className="flex-1 flex flex-col gap-1 font-heavy text-[10px] uppercase">
                True D2 (m):
                <input
                  type="number" step="0.001" min="0.05"
                  className="border-2 border-black p-2 font-mono text-xs bg-white"
                  value={calibForm.d2}
                  onChange={e => setCalibForm({ ...calibForm, d2: e.target.value })}
                />
              </label>
            </div>
            <div className="flex gap-2">
              <button
                type="submit"
                disabled={!calibTarget}
                className="flex-1 py-2 px-3 border-2 border-black bg-black text-white hover:bg-brand-yellow hover:text-black transition-colors text-[10px] font-heavy uppercase tracking-widest disabled:opacity-40"
              >
                Start capture
              </button>
              <button
                type="button"
                onClick={handleClearCalibration}
                disabled={!calibStatus}
                className="py-2 px-3 border-2 border-black bg-white text-black hover:bg-brand-red hover:text-white hover:border-brand-red transition-colors text-[10px] font-heavy uppercase tracking-widest disabled:opacity-40"
              >
                Clear
              </button>
            </div>
          </form>
          {calibStatus && (
            <div className="mt-4 border-2 border-black bg-white p-3 font-mono text-[10px] flex flex-col gap-1.5">
              <div className="flex justify-between">
                <span className="opacity-70">SAMPLES</span>
                <span className="font-heavy tabular-nums">{calibStatus.accepted_samples} / {calibStatus.required_samples}</span>
              </div>
              <div className="h-2 border border-black bg-gray-100">
                <div
                  className={`h-full ${calibStatus.ready ? 'bg-green-600' : 'bg-black'}`}
                  style={{ width: `${Math.min(100, (100 * calibStatus.accepted_samples) / calibStatus.required_samples)}%` }}
                ></div>
              </div>
              {['raw_d1', 'raw_d2'].map(key => calibStatus[key] && (
                <div key={key} className="flex justify-between">
                  <span className="opacity-70">{key.replace('raw_', '').toUpperCase()} RAW</span>
                  <span className="tabular-nums">med {calibStatus[key].median_m} m · mad {calibStatus[key].mad_m} m</span>
                </div>
              ))}
              {calibStatus.recommended_offsets_m && (
                <div className="flex justify-between font-heavy text-green-700">
                  <span>RECOMMENDED OFFSETS</span>
                  <span className="tabular-nums">
                    d1 {calibStatus.recommended_offsets_m.d1 >= 0 ? '+' : ''}{calibStatus.recommended_offsets_m.d1} · d2 {calibStatus.recommended_offsets_m.d2 >= 0 ? '+' : ''}{calibStatus.recommended_offsets_m.d2}
                  </span>
                </div>
              )}
              <div className={`uppercase font-heavy ${calibStatus.ready ? 'text-green-700' : 'text-orange-600'}`}>
                {calibStatus.ready ? 'READY — review the offsets above' : (calibStatus.reason || 'collecting').split('_').join(' ')}
              </div>
              {calibStatus.ready && (
                <button
                  type="button"
                  onClick={handleApplyCalibration}
                  className="mt-1 w-full py-2 border-2 border-green-700 bg-green-700 text-white hover:bg-white hover:text-green-700 transition-colors text-[10px] font-heavy uppercase tracking-widest"
                >
                  Apply offsets now
                </button>
              )}
              <div className="text-gray-500">
                rejected · moving {calibStatus.rejected_nonstationary} · bad range {calibStatus.rejected_bad_range} · stale {calibStatus.rejected_stale_range + calibStatus.rejected_stale_imu} · dup {calibStatus.rejected_duplicate_range} · steps {calibStatus.rejected_step_change}
              </div>
            </div>
          )}
        </div>

        {/* Manual node override */}
        <div className="p-6 border-b-4 border-black bg-gray-50">
          <h2 className="text-sm font-heavy uppercase mb-4 border-b-2 border-black pb-2">Manual Node Override</h2>
          <form onSubmit={handleAdminSubmit} className="flex flex-col gap-4">
            <label className="flex flex-col gap-1 font-heavy text-[10px] uppercase">
              Target Node:
              <select
                className="border-2 border-black p-2 font-mono text-xs cursor-pointer bg-white"
                value={selectedTarget}
                onChange={e => handleLoadTarget(e.target.value)}
              >
                <option value="" disabled>-- Select a Node --</option>
                <optgroup label="Workers">
                  {currentWorkers.map(w => <option key={w.worker_id} value={w.worker_id}>{w.worker_id}</option>)}
                </optgroup>
                <optgroup label="Anchors">
                  {currentAnchors.map(a => <option key={a.id} value={a.id}>{a.id}</option>)}
                </optgroup>
              </select>
            </label>

            {selectedTarget && !selectedTarget.startsWith('ANC_') && (
              <label className="flex flex-col gap-1 font-heavy text-[10px] uppercase">
                Force Alert Status:
                <select
                  className="border-2 border-black p-2 font-mono text-xs bg-white"
                  value={overrideForm.alert}
                  onChange={e => setOverrideForm({...overrideForm, alert: e.target.value})}
                >
                  <option value="NORMAL">NORMAL</option>
                  <option value="WARNING">WARNING</option>
                  <option value="DANGER">DANGER</option>
                  <option value="OFFLINE">OFFLINE</option>
                </select>
              </label>
            )}

            {selectedTarget && (
              <div className="flex gap-2">
                <label className="flex flex-col gap-1 font-heavy text-[10px] uppercase flex-1">
                  POS X:
                  <input type="number" step="1" className="border-2 border-black p-2 font-mono text-xs"
                    value={overrideForm.x} onChange={e => setOverrideForm({...overrideForm, x: e.target.value})} placeholder="0-100" />
                </label>
                <label className="flex flex-col gap-1 font-heavy text-[10px] uppercase flex-1">
                  POS Y:
                  <input type="number" step="1" className="border-2 border-black p-2 font-mono text-xs"
                    value={overrideForm.y} onChange={e => setOverrideForm({...overrideForm, y: e.target.value})} placeholder="0-100" />
                </label>
              </div>
            )}

            {selectedTarget && selectedTarget.startsWith('ANC_') && (
              <div className="flex gap-2">
                <label className="flex flex-col gap-1 font-heavy text-[10px] uppercase flex-1">
                  CH4 Leak (%):
                  <input type="number" step="0.1" className="border-2 border-black p-2 font-mono text-xs"
                    value={overrideForm.ch4} onChange={e => setOverrideForm({...overrideForm, ch4: e.target.value})} placeholder="CH4" />
                </label>
                <label className="flex flex-col gap-1 font-heavy text-[10px] uppercase flex-1">
                  CO Gas (PPM):
                  <input type="number" step="1" className="border-2 border-black p-2 font-mono text-xs"
                    value={overrideForm.co} onChange={e => setOverrideForm({...overrideForm, co: e.target.value})} placeholder="CO" />
                </label>
              </div>
            )}

            <div className="flex gap-2 mt-2">
              <button type="submit" className="flex-1 bg-brand-red text-white py-3 font-heavy uppercase tracking-wider hover:bg-red-800 transition-colors border-2 border-black disabled:opacity-50" disabled={!selectedTarget}>
                APPLY OVERRIDE
              </button>
              <button type="button" onClick={handleClearOverride} className="flex-1 bg-white text-black py-3 font-heavy uppercase tracking-wider hover:bg-gray-200 transition-colors border-2 border-black disabled:opacity-50" disabled={!selectedTarget}>
                CLEAR
              </button>
            </div>
          </form>
        </div>

        {/* Node visibility toggles */}
        <div className="p-6">
           <h2 className="text-sm font-heavy uppercase mb-4 border-b-2 border-black pb-2 flex justify-between items-center">
            Node Visibility Toggle
            <span className="text-[10px] bg-gray-200 px-2 py-1 rounded text-black bg-opacity-80">Click to Show/Hide</span>
           </h2>
           <div className="space-y-4">
              <div>
                 <h3 className="text-xs font-label uppercase opacity-60 mb-2 font-heavy">Worker Nodes</h3>
                 <div className="grid grid-cols-2 gap-2">
                    {currentWorkers.map(w => {
                      const isHidden = hiddenNodes[w.worker_id];
                      return (
                        <button
                          key={w.worker_id}
                          onClick={() => handleToggle(w.worker_id)}
                          className={`border-2 flex items-center justify-between p-2 cursor-pointer transition-all ${isHidden ? 'border-gray-300 bg-gray-100 grayscale opacity-60' : 'border-black bg-white hover:bg-green-50'}`}
                        >
                           <span className={`font-mono text-xs font-heavy ${isHidden ? 'line-through text-gray-500' : 'text-black'}`}>{w.worker_id}</span>
                           <span className={`material-symbols-outlined text-[16px] ${isHidden ? 'text-gray-400' : 'text-green-600'}`}>{isHidden ? 'visibility_off' : 'visibility'}</span>
                        </button>
                      )
                    })}
                    {currentWorkers.length === 0 && <div className="col-span-2 text-[10px] text-gray-400 font-heavy uppercase">No live workers yet</div>}
                 </div>
              </div>

              <div>
                 <h3 className="text-xs font-label uppercase opacity-60 mb-2 font-heavy mt-4">Anchor Nodes</h3>
                 <div className="grid grid-cols-2 gap-2">
                    {currentAnchors.map(a => {
                      const isHidden = hiddenNodes[a.id];
                      return (
                        <button
                          key={a.id}
                          onClick={() => handleToggle(a.id)}
                          className={`border-2 flex items-center justify-between p-2 cursor-pointer transition-all ${isHidden ? 'border-gray-300 bg-gray-100 grayscale opacity-60' : 'border-black bg-brand-yellow/10 hover:bg-brand-yellow/30'}`}
                        >
                           <span className={`font-mono text-xs font-heavy ${isHidden ? 'line-through text-gray-500' : 'text-black'}`}>{a.id}</span>
                           <span className={`material-symbols-outlined text-[16px] ${isHidden ? 'text-gray-400' : 'text-black'}`}>{isHidden ? 'visibility_off' : 'visibility'}</span>
                        </button>
                      )
                    })}
                    {currentAnchors.length === 0 && <div className="col-span-2 text-[10px] text-gray-400 font-heavy uppercase">No anchors reported</div>}
                 </div>
              </div>
           </div>
        </div>
      </aside>

      {/* Right column: interactive map */}
      <section className="flex-1 h-full relative border-l-4 border-gray-300 isolate">
         <div className="absolute top-4 left-4 z-50 bg-white border-2 border-black px-4 py-2 drop-shadow-md">
            <h3 className="font-heavy text-xs uppercase flex items-center gap-2">
               <span className="material-symbols-outlined text-brand-red animate-pulse">satellite_alt</span>
               Realtime Control Map
            </h3>
            <p className="text-[10px] font-label uppercase opacity-70">Drag workers to override their positions.</p>
         </div>
         <IsometricMap isAdminView={true} />
      </section>
    </div>
  );
}
