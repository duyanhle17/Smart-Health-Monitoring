export function BorderCard({ children, className = '', title, icon }) {
  return (
    <div className={`border-4 border-black p-4 bg-white flex flex-col gap-2 ${className}`}>
      {(title || icon) && (
        <div className="flex justify-between items-start mb-2">
          {title && <span className="text-[10px] font-heavy uppercase tracking-widest">{title}</span>}
          {icon && <span className="material-symbols-outlined text-sm">{icon}</span>}
        </div>
      )}
      {children}
    </div>
  );
}
