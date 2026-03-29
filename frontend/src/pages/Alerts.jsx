export default function Alerts() {
  return (
    <div className="p-8 h-full bg-gray-100 flex flex-col">
      <h1 className="text-3xl font-heavy border-b-4 border-brand-red pb-4 mb-8 uppercase tracking-tighter text-brand-red flex items-center gap-4">
        <span className="material-symbols-outlined text-4xl animate-ping" data-icon="warning">warning</span> 
        INCIDENT & ALERTS LOGS
      </h1>
      <div className="flex flex-col gap-4 overflow-auto">
        {[1,2,3].map(i => (
          <div key={i} className="bg-white border-4 border-brand-red p-4 border-l-8 flex justify-between items-center transition-all hover:bg-gray-50 cursor-pointer">
            <div>
              <div className="flex items-center gap-3 mb-2">
                <span className="bg-brand-red text-white text-[10px] uppercase font-heavy px-2 py-0.5 animate-pulse">CRITICAL WARNING</span>
                <span className="font-headline text-xs text-black">TODAY, 14:0{i}:00</span>
              </div>
              <p className="font-heavy uppercase text-xl">Toxic Gas Surge detected near WK_102 (Left Box Seating)</p>
            </div>
            <button className="border-2 border-black px-6 py-3 uppercase font-heavy text-xs hover:bg-black hover:text-white transition-none">Acknowledge</button>
          </div>
        ))}
      </div>
    </div>
  );
}
