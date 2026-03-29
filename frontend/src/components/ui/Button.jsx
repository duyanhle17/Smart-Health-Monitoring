export function Button({ children, className = '', variant = 'primary', ...props }) {
  const baseClass = "btn font-heavy uppercase tracking-tight rounded-none border-2 border-black hover:bg-black hover:text-white min-h-12 h-12 transition-none";
  let variantClass = '';
  
  if (variant === 'primary') variantClass = "bg-black text-white";
  else if (variant === 'secondary') variantClass = "bg-brand-red text-white border-black hover:bg-black";
  else if (variant === 'outline') variantClass = "bg-transparent text-black hover:bg-black hover:text-white";
  else if (variant === 'ghost') variantClass = "btn-ghost border-transparent hover:border-black hover:bg-black hover:text-white";

  return (
    <button className={`${baseClass} ${variantClass} ${className}`} {...props}>
      {children}
    </button>
  );
}
