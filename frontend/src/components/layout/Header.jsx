import { Link, useLocation } from 'react-router-dom';
import { Button } from '../ui/Button';
import { useState, useEffect } from 'react';

export default function Header() {
  const [time, setTime] = useState(new Date().toLocaleTimeString('en-GB', { hour12: false }));
  const location = useLocation();

  useEffect(() => {
    const timer = setInterval(() => {
      setTime(new Date().toLocaleTimeString('en-GB', { hour12: false }));
    }, 1000);
    return () => clearInterval(timer);
  }, []);

  const getNavClass = (path) => {
    return location.pathname === path 
      ? "font-heavy text-xs uppercase tracking-widest border-b-2 border-black pb-1" 
      : "font-heavy text-xs uppercase tracking-widest text-black/40 hover:text-black transition-colors";
  };

  return (
    <header className="fixed top-0 left-0 w-full z-50 flex justify-between items-center px-6 h-20 bg-white border-b-4 border-black shadow-[4px_4px_0px_0px_rgba(0,0,0,1)]">
      <div className="flex items-center gap-8">
        <Link to="/" className="text-3xl font-heavy">SafeWork</Link>
        <div className="hidden md:flex flex-col border-l-2 border-black px-4 leading-none">
          <span className="font-label text-[8px] font-heavy uppercase tracking-widest opacity-60">SYSTEM TIME</span>
          <span className="font-headline text-xl font-heavy tracking-tighter tabular-nums">{time}</span>
        </div>
      </div>

      <nav className="flex-1 hidden lg:flex justify-center items-center gap-12">
        <Link to="/dashboard" className={getNavClass('/dashboard')}>MAPS</Link>
        <Link to="/personnel" className={getNavClass('/personnel')}>PERSONNEL</Link>
        <Link to="/environment" className={getNavClass('/environment')}>ANALYTICS</Link>
        <Link to="/settings" className={getNavClass('/settings')}>SETTINGS</Link>
      </nav>

      <div className="flex items-center gap-4">
        <div className="flex flex-col items-end mr-4">
          <span className="font-label text-[8px] font-heavy uppercase tracking-widest text-brand-red">CRITICAL OVERRIDE</span>
          <span className="font-headline text-[10px] font-heavy">AUTH: ADMIN-01</span>
        </div>
        <Button variant="secondary">GLOBAL EVACUATION</Button>
        <span className="material-symbols-outlined text-black text-3xl cursor-pointer hover:bg-gray-100 p-2 border-2 border-transparent hover:border-black transition-none">schedule</span>
      </div>
    </header>
  );
}
