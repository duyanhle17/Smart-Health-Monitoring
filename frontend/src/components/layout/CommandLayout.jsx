import { Outlet, useLocation } from 'react-router-dom';
import Header from './Header';
import FooterTicker from './FooterTicker';
import LeftSidebar from './LeftSidebar';
import RightSidebar from './RightSidebar';
import useWorkerData from '../../hooks/useWorkerData';
import useStore from '../../store';
import { ScenarioControl } from '../ui/ScenarioControl';

export default function CommandLayout() {
  useWorkerData(); // Activate global polling
  const location = useLocation();
  const isDashboard = location.pathname === '/dashboard';
  const scenario = useStore(state => state.scenario);
  const isEvacuation = scenario === 'EVACUATION';

  return (
    <div className={`font-body text-black overflow-hidden h-screen flex flex-col transition-colors duration-1000 ${isEvacuation ? 'bg-red-950' : 'bg-gray-100'}`}>
      {isEvacuation && <div className="animate-siren pointer-events-none" />}
      
      <Header />
      
      <main className="flex flex-1 mt-20 mb-8 overflow-hidden relative">
        {/* Only show sidebars on the dashboard or if we want them globally */}
        {isDashboard && <LeftSidebar />}
        
        {/* Main Content Area */}
        <section className={`flex-1 flex flex-col overflow-hidden border-r-4 border-black transition-all ${isDashboard ? 'ml-80 mr-80' : 'mx-0'}`}>
          <Outlet />
        </section>

        {isDashboard && <RightSidebar />}
      </main>

      <FooterTicker />
      <ScenarioControl />
    </div>
  );
}
