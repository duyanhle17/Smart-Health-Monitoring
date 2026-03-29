export default function FooterTicker() {
  return (
    <footer className="fixed bottom-0 left-0 w-full z-50 h-8 flex items-center bg-gray-100 border-t-4 border-black overflow-hidden truncate">
      <div className="flex-shrink-0 bg-black text-white h-full px-4 flex items-center font-headline font-heavy text-[8px] uppercase tracking-widest z-20">
        SYSTEM_LOGS
      </div>
      <div className="flex-1 overflow-hidden h-full flex items-center justify-start relative whitespace-nowrap">
        <div className="animate-ticker flex justify-start items-center gap-12 ml-12 absolute left-0 text-[8px] font-label font-heavy text-black uppercase tracking-widest">
          <span className="flex items-center gap-2">[14:28:02] INFO: Node B2 - Monitoring Started</span>
          <span className="flex items-center gap-2">[14:27:55] INFO: Worker 04 - Heart rate normal (72 BPM)</span>
          <span className="flex items-center gap-2 text-brand-red">[14:27:40] ALERT: Fall Detection triggered for Worker 102</span>
          <span className="flex items-center gap-2">[14:27:12] INFO: Air Scrubber 04 activated automatically</span>
          <span className="flex items-center gap-2">[14:26:55] INFO: System status: Operational - MESH-NET V2.4 Connected</span>
          {/* Duplicates to create the infinite scroll effect */}
          <span className="flex items-center gap-2">[14:28:02] INFO: Node B2 - Monitoring Started</span>
          <span className="flex items-center gap-2">[14:27:55] INFO: Worker 04 - Heart rate normal (72 BPM)</span>
          <span className="flex items-center gap-2 text-brand-red">[14:27:40] ALERT: Fall Detection triggered for Worker 102</span>
          <span className="flex items-center gap-2">[14:27:12] INFO: Air Scrubber 04 activated automatically</span>
          <span className="flex items-center gap-2">[14:26:55] INFO: System status: Operational - MESH-NET V2.4 Connected</span>
        </div>
      </div>
      <div className="flex-shrink-0 bg-black text-white h-full px-4 flex items-center font-headline font-heavy text-[8px] uppercase tracking-widest z-20">
        SYSTEM STATUS: OPERATIONAL
      </div>
    </footer>
  );
}
