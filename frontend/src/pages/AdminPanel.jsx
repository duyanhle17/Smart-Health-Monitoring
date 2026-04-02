import { useState, useCallback } from 'react';
import useStore from '../store';
import IsometricMap from '../components/map/IsometricMap';
import { SCENARIO_WORKERS, MODE_WORKERS } from '../mockData';

export default function AdminPanel() {
  const workers = useStore(s => s.workers);
  const anchors = useStore(s => s.anchors);
  const scenario = useStore(s => s.scenario);
  const mapMode = useStore(s => s.mapMode);
  const isSimulation = useStore(s => s.isSimulation);
  const hiddenNodes = useStore(s => s.hiddenNodes);
  
  const handleToggle = async (id) => {
      try {
          await fetch(`/api/admin/toggle_node`, {
              method: 'POST',
              body: JSON.stringify({ node_id: id }),
              headers: { 'Content-Type': 'application/json' }
          });
      } catch (err) { console.error(err); }
  };
  
  // Custom states for the manual override form
  const [selectedTarget, setSelectedTarget] = useState('');
  const [overrideForm, setOverrideForm] = useState({ alert: 'NORMAL', x: '', y: '', ch4: '', co: '' });

  const setScenario = useCallback(async (newScenario) => {
    try {
      await fetch(`/api/scenario`, {
        method: 'POST',
        body: JSON.stringify({ scenario: newScenario }),
        headers: { 'Content-Type': 'application/json' }
      });
      useStore.getState().setScenario(newScenario);
    } catch (e) {
      console.error(e);
    }
  }, []);

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
      } else {
          payload.worker_id = selectedTarget;
      }
      
      await fetch(`/api/admin/node`, {
        method: 'POST',
        body: JSON.stringify(payload),
        headers: { 'Content-Type': 'application/json' }
      });
    } catch (err) {
      console.error(err);
    }
  };

  const handleLoadTarget = (id) => {
    setSelectedTarget(id);
    let newForm = { ...overrideForm, x: '', y: '' };
    if (id.startsWith('ANC_')) {
      const anchor = anchors.find(a => a.id === id);
      if (anchor) {
        newForm.x = parseFloat(anchor.x).toFixed(1);
        newForm.y = parseFloat(anchor.y).toFixed(1);
      }
    } else {
      const workerList = scenario !== 'NORMAL' ? SCENARIO_WORKERS[scenario] || Object.values(workers) 
        : mapMode !== 'NORMAL' ? MODE_WORKERS[mapMode] || Object.values(workers) : Object.values(workers);
      const worker = workerList.find(w => w.worker_id === id);
      if (worker) {
        newForm.x = worker.x !== undefined ? parseFloat(worker.x).toFixed(1) : '';
        newForm.y = worker.y !== undefined ? parseFloat(worker.y).toFixed(1) : '';
        newForm.alert = worker.alert || 'NORMAL';
      }
    }
    setOverrideForm(newForm);
  };

  const currentWorkers = isSimulation 
    ? (scenario !== 'NORMAL' ? SCENARIO_WORKERS[scenario] || [] : mapMode !== 'NORMAL' ? MODE_WORKERS[mapMode] || [] : Object.values(workers))
    : Object.values(workers).filter(w => w.worker_id === 'WK_102');

  return (
    <div className="w-full h-full flex bg-gray-100 overflow-hidden font-body text-black">
      {/* Cột trái: Điều khiển (Settings / Overrides) */}
      <aside className="w-[450px] shrink-0 h-full border-r-4 border-black bg-white flex flex-col z-20 shadow-2xl relative custom-scrollbar overflow-y-auto pb-20">
        <div className="p-6 bg-black text-white">
          <h1 className="text-2xl font-heavy uppercase tracking-widest flex items-center gap-3">
            <span className="material-symbols-outlined text-brand-yellow">admin_panel_settings</span>
            ADMIN CONSOLE
          </h1>
          <p className="text-xs uppercase mt-2 opacity-70 font-label tracking-wide">System overrides & Map manipulation</p>
        </div>

        {/* Cấu hình kịch bản */}
        <div className="p-6 border-b-4 border-black">
          <h2 className="text-sm font-heavy uppercase mb-4 border-b-2 border-black pb-2">Active Scenario</h2>
          <div className="flex gap-2">
            {['NORMAL', 'CAVE_IN', 'EVACUATION'].map(sc => (
              <button 
                key={sc}
                onClick={() => setScenario(sc)}
                className={`flex-1 font-heavy uppercase text-[10px] py-3 px-2 border-2 text-center transition-colors
                  ${scenario === sc ? 'bg-black text-brand-yellow border-black' : 'bg-white text-black border-gray-300 hover:border-black'}
                `}
              >
                {sc.replace('_', ' ')}
              </button>
            ))}
          </div>
        </div>

        {/* Cấu hình Map Mode */}
        <div className="p-6 border-b-4 border-black">
          <h2 className="text-sm font-heavy uppercase mb-4 border-b-2 border-black pb-2">Map View Mode</h2>
          <div className="flex gap-2">
            {[
              { id: 'NORMAL', label: 'NORMAL' },
              { id: 'LOBBY', label: 'LOBBY' },
              { id: 'ELEVATED', label: 'ELEVATED' },
            ].map(m => (
              <button 
                key={m.id}
                onClick={() => useStore.getState().setMapMode(m.id)}
                className={`flex-1 font-heavy uppercase text-[10px] py-3 px-2 border-2 text-center transition-colors
                  ${mapMode === m.id ? 'bg-black text-brand-yellow border-black' : 'bg-white text-black border-gray-300 hover:border-black'}
                `}
              >
                {m.label}
              </button>
            ))}
          </div>
        </div>

        {/* Tuỳ chỉnh Force Position API */}
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
                  {anchors.map(a => <option key={a.id} value={a.id}>{a.id}</option>)}
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

            <button type="submit" className="w-full bg-brand-red text-white py-3 font-heavy uppercase tracking-wider hover:bg-red-800 transition-colors border-2 border-black border-solid mt-2 drop-shadow-md cursor-pointer disabled:opacity-50" disabled={!selectedTarget}>
              APPLY OVERRIDE
            </button>
          </form>
        </div>

        {/* Danh sách các Node để Toggle Hiện/Ẩn */}
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
                 </div>
              </div>

              <div>
                 <h3 className="text-xs font-label uppercase opacity-60 mb-2 font-heavy mt-4">Anchor Nodes</h3>
                 <div className="grid grid-cols-2 gap-2">
                    {anchors.map(a => {
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
                 </div>
              </div>
           </div>
        </div>
      </aside>

      {/* Cột phải: Bản đồ Interactive */}
      <section className="flex-1 h-full relative border-l-4 border-gray-300 isolate">
         <div className="absolute top-4 left-4 z-50 bg-white border-2 border-black px-4 py-2 drop-shadow-md">
            <h3 className="font-heavy text-xs uppercase flex items-center gap-2">
               <span className="material-symbols-outlined text-brand-red animate-pulse">satellite_alt</span>
               Realtime Control Map
            </h3>
            <p className="text-[10px] font-label uppercase opacity-70">Drag nodes to override positions physically.</p>
         </div>
         {/* Nhúng màn hình map, render đè lên thông báo. isAdminView cho phép can thiệp trực tiếp */}
         <IsometricMap isAdminView={true} />
      </section>
    </div>
  );
}
