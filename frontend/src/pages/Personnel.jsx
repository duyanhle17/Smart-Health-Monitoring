export default function Personnel() {
  return (
    <div className="p-8 h-full bg-gray-100 flex flex-col">
      <h1 className="text-3xl font-heavy border-b-4 border-black pb-4 mb-8 uppercase tracking-tighter">PERSONNEL MANAGEMENT</h1>
      <div className="flex-1 overflow-auto bg-white border-4 border-black p-4">
        <table className="w-full text-left font-headline">
          <thead className="border-b-4 border-black">
            <tr>
              <th className="pb-4 pt-2 px-4 uppercase font-heavy tracking-widest text-xs">Worker ID</th>
              <th className="pb-4 pt-2 px-4 uppercase font-heavy tracking-widest text-xs">Name</th>
              <th className="pb-4 pt-2 px-4 uppercase font-heavy tracking-widest text-xs">Zone</th>
              <th className="pb-4 pt-2 px-4 uppercase font-heavy tracking-widest text-xs">Status</th>
              <th className="pb-4 pt-2 px-4 uppercase font-heavy tracking-widest text-xs">Heart Rate</th>
            </tr>
          </thead>
          <tbody>
            {[
              { id: 'WK_102', name: 'John Doe', zone: 'Left Seat', status: 'CRITICAL', hr: '130 bpm' },
              { id: 'WK_04', name: 'Jane Smith', zone: 'Left Seat', status: 'STABLE', hr: '75 bpm' },
              { id: 'WK_89', name: 'Mike Johnson', zone: 'Right Seat', status: 'STABLE', hr: '82 bpm' },
              { id: 'WK_48', name: 'Emily Davis', zone: 'Right Seat', status: 'STABLE', hr: '71 bpm' },
            ].map(w => (
              <tr key={w.id} className="border-b-2 border-gray-200 hover:bg-gray-50 transition-colors">
                <td className="py-4 px-4 font-heavy">{w.id}</td>
                <td className="py-4 px-4">{w.name}</td>
                <td className="py-4 px-4">{w.zone}</td>
                <td className="py-4 px-4">
                  <span className={`px-2 py-1 text-[10px] uppercase font-heavy ${w.status === 'CRITICAL' ? 'bg-brand-red text-white animate-pulse' : 'bg-black text-white'}`}>{w.status}</span>
                </td>
                <td className="py-4 px-4 tracking-tighter">{w.hr}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
