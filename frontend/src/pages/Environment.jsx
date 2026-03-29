export default function Environment() {
  return (
    <div className="p-8 h-full bg-gray-100 flex flex-col">
      <h1 className="text-3xl font-heavy border-b-4 border-black pb-4 mb-8 uppercase tracking-tighter">ENVIRONMENTAL ANALYTICS</h1>
      <div className="grid grid-cols-2 gap-8">
        <div className="bg-white border-4 border-black p-6">
          <h2 className="text-xl font-heavy mb-4 uppercase tracking-tight">Toxic Gas Levels</h2>
          <div className="flex flex-col gap-4">
            <div>
              <div className="flex justify-between font-headline text-xs mb-1"><span>CO (CARBON MONOXIDE)</span><span className="font-heavy text-brand-red animate-pulse tracking-tighter">45 ppm (HIGH)</span></div>
              <div className="w-full h-6 border-2 border-black bg-gray-200"><div className="h-full bg-brand-red w-[80%] animate-pulse"></div></div>
            </div>
            <div>
              <div className="flex justify-between font-headline text-xs mb-1 mt-4"><span>CH4 (METHANE)</span><span>0.1% LEL</span></div>
              <div className="w-full h-6 border-2 border-black bg-gray-200"><div className="h-full bg-black w-[10%]"></div></div>
            </div>
          </div>
        </div>
        <div className="bg-white border-4 border-black p-6 flex flex-col justify-center items-center relative">
          <h2 className="text-xl font-heavy uppercase tracking-tight absolute top-6 left-6">Air Quality Index</h2>
          <div className="text-8xl font-heavy tracking-tighter text-center mt-8">
            152
            <span className="text-2xl text-brand-red block mt-2 animate-pulse tracking-widest border-t-4 border-brand-red pt-4">UNHEALTHY HAZARD</span>
          </div>
        </div>
      </div>
    </div>
  );
}
