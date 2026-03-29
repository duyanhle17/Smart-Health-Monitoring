import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import CommandLayout from './components/layout/CommandLayout';
import Dashboard from './pages/Dashboard';
import Login from './pages/Login';
import Personnel from './pages/Personnel';
import Environment from './pages/Environment';
import Alerts from './pages/Alerts';
import Network from './pages/Network';
import Settings from './pages/Settings';

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/" element={<CommandLayout />}>
          <Route index element={<Navigate to="/dashboard" replace />} />
          <Route path="dashboard" element={<Dashboard />} />
          <Route path="personnel" element={<Personnel />} />
          <Route path="environment" element={<Environment />} />
          <Route path="alerts" element={<Alerts />} />
          <Route path="network" element={<Network />} />
          <Route path="settings" element={<Settings />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}

export default App;
