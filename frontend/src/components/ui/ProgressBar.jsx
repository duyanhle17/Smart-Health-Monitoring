export function ProgressBar({ value, max = 100, colorClass = "bg-black", className = "" }) {
  const percentage = Math.min(100, Math.max(0, (value / max) * 100));
  
  return (
    <div className={`h-6 border-2 border-black bg-gray-200 relative overflow-hidden ${className}`}>
      <div 
        className={`absolute top-0 left-0 h-full ${colorClass}`} 
        style={{ width: `${percentage}%` }}
      ></div>
    </div>
  );
}
