import { useEffect } from 'react';
import useStore from '../../store';

export function ScenarioControl() {
  const { scenario: activeScenario, setScenario: setActiveScenario } = useStore();

  // Fetch initial scenario
  useEffect(() => {
    fetch('/api/scenario')
      .then(res => res.json())
      .then(data => setActiveScenario(data.scenario))
      .catch(err => console.error("Error fetching scenario:", err));
  }, [setActiveScenario]);

  const changeScenario = async (scenario) => {
    try {
      const res = await fetch('/api/scenario', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ scenario })
      });
      const data = await res.json();
      if (data.status === 'ACK') {
        setActiveScenario(data.scenario);
      }
    } catch (e) {
      console.error("Error setting scenario", e);
    }
  };

  return (
    <div className="fixed bottom-12 right-[340px] z-[100] flex items-center gap-2 pointer-events-auto">
      <div className="bg-black text-white p-2 flex gap-2 border-2 border-black">
        <div className="font-headline font-heavy text-[10px] leading-none pr-3 border-r-2 border-gray-700 uppercase flex items-center">
          Simulation<br/>Control
        </div>
        <button 
          onClick={() => changeScenario('NORMAL')}
          className={`px-3 py-1 font-heavy text-xs uppercase transition-colors ${activeScenario === 'NORMAL' ? 'bg-white text-black' : 'bg-gray-800 text-gray-400 hover:bg-gray-700'}`}
        >
          Normal
        </button>
        <button 
          onClick={() => changeScenario('CAVE_IN')}
          className={`px-3 py-1 font-heavy text-xs uppercase transition-colors ${activeScenario === 'CAVE_IN' ? 'bg-brand-yellow text-black' : 'bg-gray-800 text-gray-400 hover:bg-brand-yellow hover:text-black'}`}
        >
          CAVE-IN
        </button>
        <button 
          onClick={() => changeScenario('EVACUATION')}
          className={`px-3 py-1 font-heavy text-xs uppercase transition-colors ${activeScenario === 'EVACUATION' ? 'bg-brand-red text-white animate-pulse-fast' : 'bg-gray-800 text-gray-400 hover:bg-brand-red hover:text-white'}`}
        >
          EVACUATION
        </button>
      </div>
    </div>
  );
}
