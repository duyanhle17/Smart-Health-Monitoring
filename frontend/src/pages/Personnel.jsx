import { useState } from 'react';

export default function Personnel() {
  const [showAdd, setShowAdd] = useState(false);

  return (
    <div className="p-8 h-full bg-gray-100 flex flex-col relative">
      <div className="flex justify-between items-end border-b-4 border-black pb-4 mb-8">
        <h1 className="text-3xl font-heavy uppercase tracking-tighter">PERSONNEL MANAGEMENT</h1>
        <button onClick={() => setShowAdd(true)} className="border-2 border-black px-4 py-2 uppercase font-heavy text-xs bg-black text-white hover:bg-gray-800 transition-none">+ ADD PERSONNEL</button>
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
            {[
              { id: 'WK_102', name: 'A. Chen', zone: 'Left Seat', status: 'CRITICAL', hr: '130 bpm' },
              { id: 'WK_04', name: 'J. Vance', zone: 'Left Seat', status: 'STABLE', hr: '75 bpm' },
              { id: 'WK_89', name: 'M. Johnson', zone: 'Right Seat', status: 'STABLE', hr: '82 bpm' },
              { id: 'WK_48', name: 'E. Davis', zone: 'Right Seat', status: 'STABLE', hr: '71 bpm' },
            ].map(w => (
              <tr key={w.id} className="border-b-2 border-gray-200 hover:bg-gray-50 transition-colors">
                <td className="py-4 px-4 font-heavy">{w.id}</td>
                <td className="py-4 px-4">{w.name}</td>
                <td className="py-4 px-4">{w.zone}</td>
                <td className="py-4 px-4">
                  <span className={`px-2 py-1 text-[10px] uppercase font-heavy ${w.status === 'CRITICAL' ? 'bg-brand-red text-white animate-pulse' : 'bg-black text-white'}`}>{w.status}</span>
                </td>
                <td className="py-4 px-4 flex gap-2">
                  <button className="border-2 border-black px-3 py-1 text-[10px] font-heavy hover:bg-black hover:text-white uppercase">EDIT</button>
                  <button className="border-2 border-brand-red text-brand-red px-3 py-1 text-[10px] font-heavy hover:bg-brand-red hover:text-white uppercase">DEL</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {showAdd && (
        <div className="absolute inset-0 bg-black/50 z-50 flex items-center justify-center p-8 backdrop-blur-sm">
          <div className="bg-white border-4 border-black p-8 flex flex-col w-[400px] shadow-[8px_8px_0px_0px_rgba(0,0,0,1)]">
            <h2 className="font-heavy text-xl uppercase mb-6 border-b-2 border-black pb-2">REGISTER PERSONNEL</h2>
            <input placeholder="WORKER ID (E.g. WK_102)" className="border-2 border-black p-3 mb-4 font-headline uppercase bg-gray-100" />
            <input placeholder="FULL NAME" className="border-2 border-black p-3 mb-4 font-headline uppercase bg-gray-100" />
            <select className="border-2 border-black p-3 mb-8 font-headline uppercase bg-gray-100 cursor-pointer">
              <option>ASSIGN ZONE: LEFT SEAT</option>
              <option>ASSIGN ZONE: RIGHT SEAT</option>
              <option>ASSIGN ZONE: MAIN STAGE</option>
            </select>
            <div className="flex gap-4">
               <button onClick={() => setShowAdd(false)} className="border-2 border-black px-4 py-3 hover:bg-gray-100 font-heavy uppercase flex-1">CANCEL</button>
               <button onClick={() => setShowAdd(false)} className="border-2 border-black px-4 py-3 bg-black text-white hover:bg-gray-800 font-heavy flex-1 uppercase">SAVE ENTRY</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
