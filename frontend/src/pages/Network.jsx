export default function Network() {
  return (
    <div className="p-8 h-full bg-gray-100 flex flex-col">
      <h1 className="text-3xl font-heavy border-b-4 border-black pb-4 mb-8 uppercase tracking-tighter">MESH NETWORK TOPOLOGY</h1>
      <div className="flex-1 border-4 border-black bg-white flex items-center justify-center flex-col text-center p-8">
        <span className="material-symbols-outlined text-8xl mb-4 text-brand-yellow font-light animate-pulse" data-icon="hub">hub</span>
        <h2 className="text-2xl font-heavy mb-2">MESH NETWORK STABLE</h2>
        <p className="font-headline text-sm uppercase max-w-lg mx-auto">All TOF Anchors are reporting correctly. Network latency is under 15ms. 8 Mesh nodes connected.</p>
      </div>
    </div>
  );
}
