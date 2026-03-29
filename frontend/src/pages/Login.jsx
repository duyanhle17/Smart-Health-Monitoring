import { Button } from '../components/ui/Button';
import { useNavigate } from 'react-router-dom';

export default function Login() {
  const navigate = useNavigate();

  return (
    <div className="w-screen h-screen flex justify-center items-center bg-gray-100">
      <div className="border-4 border-black bg-white p-8 flex flex-col items-center w-96">
        <h1 className="text-3xl font-heavy mb-8 uppercase tracking-tighter">SAFE WORK</h1>
        <p className="font-label text-xs uppercase mb-8 border-b-2 border-black pb-2 w-full text-center">Auth Required</p>
        
        <input type="text" placeholder="ADMIN ID" className="border-2 border-black p-3 mb-4 w-full bg-gray-100 font-headline uppercase" />
        <input type="password" placeholder="PIN" className="border-2 border-black p-3 mb-8 w-full bg-gray-100 font-headline uppercase" />
        
        <Button className="w-full" onClick={() => navigate('/dashboard')}>ACCESS SYSTEM</Button>
      </div>
    </div>
  );
}
