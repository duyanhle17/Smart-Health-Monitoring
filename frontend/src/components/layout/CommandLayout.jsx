import { Outlet, useLocation } from 'react-router-dom';
import Header from './Header';
import FooterTicker from './FooterTicker';
import LeftSidebar from './LeftSidebar';
import RightSidebar from './RightSidebar';
import VitalsAlarmBanner from './VitalsAlarmBanner';
import useWorkerData from '../../hooks/useWorkerData';

export default function CommandLayout() {
  useWorkerData(); // Activate global polling
  const location = useLocation();
  const isDashboard = location.pathname === '/dashboard';

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
