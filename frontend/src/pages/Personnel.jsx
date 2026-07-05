import { useState, useEffect, useCallback } from 'react';
import useStore from '../store';

const ZONES = [
  { value: 'GAMMA_STAGE', label: 'Main Stage' },
  { value: 'ALPHA_LEFT', label: 'Left Seat' },
  { value: 'BETA_RIGHT', label: 'Right Seat' },
  { value: 'CENTER_PATH', label: 'Center Path' },
  { value: 'DELTA_CENTER', label: 'Delta Center' },
];
const zoneLabel = (z) => ZONES.find((o) => o.value === z)?.label || z || '—';

const EMPTY = { id: '', name: '', zone: 'ALPHA_LEFT' };

export default function Personnel() {
  const [people, setPeople] = useState([]);
  const [modal, setModal] = useState(null); // null | 'add' | 'edit'
  const [form, setForm] = useState(EMPTY);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const workers = useStore((s) => s.workers);

  const load = useCallback(() => {
    fetch('/api/personnel')
      .then((r) => r.json())
      .then((d) => setPeople(Array.isArray(d) ? d : []))
      .catch(() => {});
  }, []);

  useEffect(() => { load(); }, [load]);

  const openAdd = () => { setForm(EMPTY); setError(''); setModal('add'); };
  const openEdit = (p) => { setForm({ id: p.id, name: p.name, zone: p.zone || 'ALPHA_LEFT' }); setError(''); setModal('edit'); };
  const close = () => { setModal(null); setError(''); };

  const save = async () => {
    const id = form.id.trim();
    const name = form.name.trim();
    if (!id || !name) { setError('Worker ID và Name là bắt buộc'); return; }
    setBusy(true);
    setError('');
    try {
      const isEdit = modal === 'edit';
      const res = await fetch(
        isEdit ? `/api/personnel/${encodeURIComponent(id)}` : '/api/personnel',
        {
          method: isEdit ? 'PUT' : 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ id, name, zone: form.zone }),
        }
      );
      if (!res.ok) {
        const e = await res.json().catch(() => ({}));
        setError(e.error || `Lỗi ${res.status}`);
        setBusy(false);
        return;
      }
      close();
      load();
    } catch {
      setError('Không kết nối được server');
    }
    setBusy(false);
  };

  const remove = async (p) => {
    if (!window.confirm(`Xóa nhân sự ${p.name} (${p.id})?`)) return;
    await fetch(`/api/personnel/${encodeURIComponent(p.id)}`, { method: 'DELETE' }).catch(() => {});
    load();
  };

  const statusOf = (id) => {
    const w = workers[id];
    return w && w.alert ? w.alert : 'OFFLINE';
  };
  const statusClass = (s) =>
    s === 'CRITICAL' || s === 'DANGER'
      ? 'bg-brand-red text-white animate-pulse'
      : s === 'WARNING'
      ? 'bg-yellow-400 text-black'
      : s === 'OFFLINE'
      ? 'bg-gray-400 text-white'
      : 'bg-black text-white';

  return (
    <div className="p-8 h-full bg-gray-100 flex flex-col relative">
      <div className="flex justify-between items-end border-b-4 border-black pb-4 mb-8">
        <h1 className="text-3xl font-heavy uppercase tracking-tighter">PERSONNEL MANAGEMENT</h1>
        <button onClick={openAdd} className="border-2 border-black px-4 py-2 uppercase font-heavy text-xs bg-black text-white hover:bg-gray-800 transition-none">+ ADD PERSONNEL</button>
      </div>

      <div className="flex-1 overflow-auto bg-white border-4 border-black p-4">
        <table className="w-full text-left font-headline">
          <thead className="border-b-4 border-black">
            <tr>
              <th className="pb-4 pt-2 px-4 uppercase font-heavy tracking-widest text-xs">Worker ID</th>
              <th className="pb-4 pt-2 px-4 uppercase font-heavy tracking-widest text-xs">Name</th>
              <th className="pb-4 pt-2 px-4 uppercase font-heavy tracking-widest text-xs">Zone</th>
              <th className="pb-4 pt-2 px-4 uppercase font-heavy tracking-widest text-xs">Status</th>
              <th className="pb-4 pt-2 px-4 uppercase font-heavy tracking-widest text-xs">Actions</th>
            </tr>
          </thead>
          <tbody>
            {people.length === 0 && (
              <tr><td colSpan={5} className="py-8 px-4 text-center text-gray-400 font-heavy uppercase text-xs">Chưa có nhân sự</td></tr>
            )}
            {people.map((w) => {
              const st = statusOf(w.id);
              return (
                <tr key={w.id} className="border-b-2 border-gray-200 hover:bg-gray-50 transition-colors">
                  <td className="py-4 px-4 font-heavy">{w.id}</td>
                  <td className="py-4 px-4">{w.name}</td>
                  <td className="py-4 px-4">{zoneLabel(w.zone)}</td>
                  <td className="py-4 px-4">
                    <span className={`px-2 py-1 text-[10px] uppercase font-heavy ${statusClass(st)}`}>{st}</span>
                  </td>
                  <td className="py-4 px-4 flex gap-2">
                    <button onClick={() => openEdit(w)} className="border-2 border-black px-3 py-1 text-[10px] font-heavy hover:bg-black hover:text-white uppercase">EDIT</button>
                    <button onClick={() => remove(w)} className="border-2 border-brand-red text-brand-red px-3 py-1 text-[10px] font-heavy hover:bg-brand-red hover:text-white uppercase">DEL</button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {modal && (
        <div className="absolute inset-0 bg-black/50 z-50 flex items-center justify-center p-8 backdrop-blur-sm">
          <div className="bg-white border-4 border-black p-8 flex flex-col w-[400px] shadow-[8px_8px_0px_0px_rgba(0,0,0,1)]">
            <h2 className="font-heavy text-xl uppercase mb-6 border-b-2 border-black pb-2">
              {modal === 'edit' ? 'EDIT PERSONNEL' : 'REGISTER PERSONNEL'}
            </h2>

            <input
              value={form.id}
              onChange={(e) => setForm({ ...form, id: e.target.value })}
              disabled={modal === 'edit'}
              placeholder="WORKER ID (E.g. WK_102)"
              className="border-2 border-black p-3 mb-4 font-headline uppercase bg-gray-100 disabled:opacity-60 disabled:cursor-not-allowed"
            />
            <input
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              placeholder="FULL NAME"
              className="border-2 border-black p-3 mb-4 font-headline bg-gray-100"
            />
            <select
              value={form.zone}
              onChange={(e) => setForm({ ...form, zone: e.target.value })}
              className="border-2 border-black p-3 mb-4 font-headline uppercase bg-gray-100 cursor-pointer"
            >
              {ZONES.map((z) => (
                <option key={z.value} value={z.value}>ASSIGN ZONE: {z.label}</option>
              ))}
            </select>

            {error && <p className="text-brand-red font-heavy text-xs uppercase mb-4">{error}</p>}

            <div className="flex gap-4 mt-2">
              <button onClick={close} className="border-2 border-black px-4 py-3 hover:bg-gray-100 font-heavy uppercase flex-1">CANCEL</button>
              <button onClick={save} disabled={busy} className="border-2 border-black px-4 py-3 bg-black text-white hover:bg-gray-800 font-heavy flex-1 uppercase disabled:opacity-50">
                {busy ? 'SAVING…' : 'SAVE ENTRY'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
