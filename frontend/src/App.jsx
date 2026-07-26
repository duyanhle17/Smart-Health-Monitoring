import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import CommandLayout from './components/layout/CommandLayout';
import Dashboard from './pages/Dashboard';
import Personnel from './pages/Personnel';
import Environment from './pages/Environment';
import Alerts from './pages/Alerts';
import AdminPanel from './pages/AdminPanel';

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<CommandLayout />}>
          <Route index element={<Navigate to="/dashboard" replace />} />
          <Route path="dashboard" element={<Dashboard />} />
          <Route path="personnel" element={<Personnel />} />
          <Route path="environment" element={<Environment />} />
          <Route path="alerts" element={<Alerts />} />
          <Route path="admin" element={<AdminPanel />} />
          <Route path="*" element={<Navigate to="/dashboard" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}

export default App;
