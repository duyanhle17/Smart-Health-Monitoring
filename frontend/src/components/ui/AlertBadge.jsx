export function AlertBadge({ text, status = 'neutral', className = '' }) {
  let baseClass = "px-2 py-0.5 text-[8px] font-heavy font-headline inline-block uppercase";
  
  if (status === 'stable') {
    baseClass += " bg-black text-white";
  } else if (status === 'warning') {
    baseClass += " bg-orange-600 text-white";
  } else if (status === 'alert') {
    baseClass += " bg-brand-red text-white border-2 border-black animate-pulse";
  } else {
    baseClass += " bg-black text-white";
  }

  return (
    <span className={`${baseClass} ${className}`}>
      {text}
    </span>
  );
}
