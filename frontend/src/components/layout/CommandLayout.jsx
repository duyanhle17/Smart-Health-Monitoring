import { Outlet, useLocation } from 'react-router-dom';
import Header from './Header';
import FooterTicker from './FooterTicker';
import LeftSidebar from './LeftSidebar';
import RightSidebar from './RightSidebar';

export default function CommandLayout() {
  const location = useLocation();
  const isDashboard = location.pathname === '/dashboard';

  return (
    <div className="bg-gray-100 font-body text-black overflow-hidden h-screen flex flex-col">
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
    </div>
  );
}
