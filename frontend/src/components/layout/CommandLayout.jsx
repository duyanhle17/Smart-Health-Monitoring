import { Outlet, useLocation } from 'react-router-dom';
import Header from './Header';
import FooterTicker from './FooterTicker';
import LeftSidebar from './LeftSidebar';
import RightSidebar from './RightSidebar';
import VitalsAlarmBanner from './VitalsAlarmBanner';
import useWorkerData from '../../hooks/useWorkerData';
import useMobileMapMode from '../../hooks/useMobileMapMode';

export default function CommandLayout() {
  useWorkerData(); // Activate global polling
  const location = useLocation();
  const { view } = useMobileMapMode();
  const isDashboard = location.pathname === '/dashboard';

  // The phone admin view is the map and nothing else, so it gets the whole
  // viewport with no chrome around it. Every other route, and every desktop
  // viewport, renders the layout exactly as before.
  if (location.pathname === '/admin' && view === 'map') {
    return (
      <div className="font-body text-black overflow-hidden h-screen bg-gray-100">
        <Outlet />
      </div>
    );
  }

  return (
    <div className="font-body text-black overflow-hidden h-screen flex flex-col bg-gray-100">
      <Header />
      <VitalsAlarmBanner />

      <main className="flex flex-1 min-h-0 overflow-hidden relative">
        {/* Only show sidebars on the dashboard or if we want them globally */}
        {isDashboard && <LeftSidebar />}

        {/* Main Content Area */}
        <section className="flex-1 flex flex-col overflow-hidden border-r-4 border-black">
          <Outlet />
        </section>

        {isDashboard && <RightSidebar />}
      </main>

      <FooterTicker />
    </div>
  );
}
