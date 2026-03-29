export default function Settings() {
  return (
    <div className="p-8 h-full bg-gray-100 flex flex-col">
      <h1 className="text-3xl font-heavy border-b-4 border-black pb-4 mb-8 uppercase tracking-tighter">SYSTEM SETTINGS</h1>
      <div className="max-w-2xl">
        <div className="bg-white border-4 border-black p-6 mb-8 flex flex-col gap-6">
          <div>
            <label className="block font-heavy uppercase text-xs mb-2">Gas Alert Threshold (PPM)</label>
            <input type="number" defaultValue={25} className="border-2 border-black p-3 w-full bg-gray-100 font-headline uppercase" />
          </div>
          <div>
            <label className="block font-heavy uppercase text-xs mb-2">Heart Rate Critical Threshold (BPM)</label>
            <input type="number" defaultValue={120} className="border-2 border-black p-3 w-full bg-gray-100 font-headline uppercase" />
          </div>
          <div>
            <label className="block font-heavy uppercase text-xs mb-2">Fall Detection Sensitivity</label>
            <select className="border-2 border-black p-3 w-full bg-gray-100 font-headline uppercase cursor-pointer">
              <option>HIGH</option>
              <option>MEDIUM</option>
              <option>LOW</option>
            </select>
          </div>
        </div>
        <button className="border-2 border-black px-6 py-3 uppercase font-heavy text-xs bg-black text-white hover:bg-gray-800 transition-none w-full">SAVE CONFIGURATION</button>
      </div>
    </div>
  );
}
