"use client";

import React, { useState, useEffect } from 'react';

export default function Dashboard() {
  const [alerts, setAlerts] = useState<any[]>([]);
  const [activeAlertIndex, setActiveAlertIndex] = useState<number | null>(null);
  const [lastSync, setLastSync] = useState<string>('');

  useEffect(() => {
    const fetchAlerts = async () => {
      try {
        const res = await fetch('/api/alerts', { cache: 'no-store' });
        if (res.ok) {
          const data = await res.json();
          const list = Array.isArray(data) ? [...data].reverse() : [];
          setAlerts(list);
          setLastSync(new Date().toLocaleTimeString());

          if (activeAlertIndex === null && list.length > 0) {
            setActiveAlertIndex(0);
          }
        }
      } catch (error) {
        console.error("Failed to fetch alerts:", error);
      }
    };

    // Fetch immediately on mount
    fetchAlerts();

    // Poll every 3 seconds
    const interval = setInterval(fetchAlerts, 3000);
    return () => clearInterval(interval);
  }, [activeAlertIndex]);

  const activeAlert = activeAlertIndex !== null ? alerts[activeAlertIndex] : null;

  return (
    <div className="flex flex-col h-screen w-screen bg-[#0a0a0a] text-gray-300 font-sans overflow-hidden">
      
      {/* HEADER */}
      <header className="h-14 border-b border-gray-800 bg-[#111] flex items-center justify-between px-4 shrink-0">
        <div className="flex items-center gap-3">
          <div className="h-6 w-6 bg-red-600 flex items-center justify-center rounded-sm text-white font-bold text-xs">
            !
          </div>
          <div>
            <h1 className="text-white font-bold tracking-widest text-xs uppercase">PECUU Command Center</h1>
            <p className="text-gray-500 text-[10px] uppercase font-mono mt-0.5">Automated Traffic Analytics Module</p>
          </div>
        </div>
        <div className="font-mono text-xs text-green-500 flex items-center gap-2">
          <span className="relative flex h-2 w-2">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
            <span className="relative inline-flex rounded-full h-2 w-2 bg-green-500"></span>
          </span>
          LAST SYNC: {lastSync || 'AWAITING...'}
        </div>
      </header>

      {/* THREE-PANE LAYOUT */}
      <div className="flex flex-1 overflow-hidden">
        
        {}
        {/* LEFT PANEL - ALERT LIST */}
        <aside className="w-80 border-r border-gray-800 bg-[#0f0f0f] flex flex-col flex-shrink-0">
          <div className="p-3 border-b border-gray-800 flex justify-between items-center">
            <h2 className="text-xs font-bold text-gray-400 uppercase tracking-wider">Active Anomalies</h2>
            <span className="bg-red-500/20 text-red-500 text-[10px] px-2 py-0.5 rounded font-mono border border-red-500/30">
              {alerts.length} ALERTS
            </span>
          </div>
          
          <div className="flex-1 overflow-y-auto p-2 space-y-2">
            {alerts.length === 0 ? (
              <div className="text-center text-gray-600 font-mono text-xs py-8">
                NO ACTIVE ALERTS
              </div>
            ) : (
              alerts.map((alert, index) => (
                <div 
                  key={index}
                  onClick={() => setActiveAlertIndex(index)}
                  className={`p-3 border rounded cursor-pointer transition-all ${
                    activeAlertIndex === index 
                      ? 'border-red-500/70 bg-red-950/20 shadow-[0_0_10px_rgba(239,68,68,0.1)]' 
                      : 'border-gray-800 bg-[#141414] hover:border-gray-700'
                  }`}
                >
                  <div className="flex justify-between items-start mb-2">
                    <div className="text-[10px] font-mono px-1.5 py-0.5 rounded border uppercase border-red-500/50 bg-red-500/10 text-red-400">
                      CRITICAL
                    </div>
                    <div className="text-[10px] text-gray-500 font-mono">
                      {new Date(alert.timestamp).toLocaleTimeString()}
                    </div>
                  </div>
                  <h3 className="text-sm font-semibold text-gray-200 truncate">{alert.camera_id}</h3>
                  <div className="mt-2 text-xs font-mono text-gray-400">
                    <span className="text-gray-600">COUNT:</span> <span className="text-red-400">{alert.vehicle_count} VEH</span>
                    {alert.stationary_count != null && (
                      <>
                        {' · '}
                        <span className="text-gray-600">STOP:</span>{' '}
                        <span className="text-red-400">{alert.stationary_count}</span>
                      </>
                    )}
                  </div>
                </div>
              ))
            )}
          </div>
        </aside>

        {}
        {/* CENTER PANEL - TACTICAL MAP PLACEHOLDER */}
        <main className="flex-1 relative bg-[#050505] overflow-hidden flex items-center justify-center">
          {/* Tactical Grid Pattern */}
          <div 
            className="absolute inset-0 opacity-10 pointer-events-none"
            style={{
              backgroundImage: 'linear-gradient(rgba(255, 255, 255, 0.5) 1px, transparent 1px), linear-gradient(90deg, rgba(255, 255, 255, 0.5) 1px, transparent 1px)',
              backgroundSize: '40px 40px'
            }}
          />
          
          <div className="z-10 flex flex-col items-center opacity-30">
            <svg xmlns="http://www.w3.org/2000/svg" className="w-16 h-16 mb-4 text-gray-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1" strokeLinecap="round" strokeLinejoin="round">
              <polygon points="3 6 9 3 15 6 21 3 21 18 15 21 9 18 3 21"></polygon>
              <line x1="9" y1="3" x2="9" y2="21"></line>
              <line x1="15" y1="3" x2="15" y2="21"></line>
            </svg>
            <p className="font-mono text-sm uppercase tracking-[0.2em] text-gray-500">GIS Map Layer Offline</p>
            <p className="font-mono text-[10px] text-gray-600 mt-2">Mapbox integration pending...</p>
          </div>

          {/* Dummy radar sweep */}
          <div className="absolute inset-0 border-cyan-500/10 border-[1px] rounded-full w-[200vw] h-[200vw] -translate-x-1/2 -translate-y-1/2 animate-[spin_10s_linear_infinite]" style={{ top: '50%', left: '50%' }}>
            <div className="w-1/2 h-full bg-gradient-to-r from-transparent to-cyan-500/5 origin-right"></div>
          </div>
        </main>

        {}
        {/* RIGHT PANEL - DETAILS & DISPATCH */}
        <aside className="w-[22rem] border-l border-gray-800 bg-[#0f0f0f] flex flex-col flex-shrink-0 z-10 shadow-[-5px_0_15px_rgba(0,0,0,0.5)]">
          <div className="p-3 border-b border-gray-800">
            <h2 className="text-xs font-bold text-gray-400 uppercase tracking-wider">Intervention Protocol</h2>
          </div>

          {activeAlert ? (
            <div className="flex-1 p-5 flex flex-col">
              <div className="mb-6">
                <div className="text-[10px] text-gray-500 font-mono mb-1">INCIDENT LOCATION</div>
                <h3 className="text-lg font-bold text-white leading-tight">{activeAlert.camera_id}</h3>
              </div>

              <div className="space-y-4 mb-8">
                <div className="bg-[#1a1a1a] p-3 rounded border border-gray-800">
                  <div className="text-[10px] text-gray-500 font-mono mb-1">DETECTION THRESHOLD</div>
                  <div className="text-sm text-gray-300 font-mono">{activeAlert.severity || 'N/A'}</div>
                </div>

                <div className="flex gap-4">
                  <div className="flex-1 bg-[#1a1a1a] p-3 rounded border border-gray-800 border-l-2 border-l-red-500">
                    <div className="text-[10px] text-gray-500 font-mono mb-1">VEHICLES</div>
                    <div className="text-xl text-red-400 font-mono font-bold">{activeAlert.vehicle_count}</div>
                  </div>
                  <div className="flex-1 bg-[#1a1a1a] p-3 rounded border border-gray-800">
                    <div className="text-[10px] text-gray-500 font-mono mb-1">STATIONARY</div>
                    <div className="text-xl text-gray-200 font-mono font-bold">
                      {activeAlert.stationary_count ?? '—'}
                    </div>
                  </div>
                </div>
                <div className="bg-[#1a1a1a] p-3 rounded border border-gray-800">
                  <div className="text-[10px] text-gray-500 font-mono mb-1">TIMESTAMP</div>
                  <div className="text-sm text-gray-300 font-mono mt-1">
                    {new Date(activeAlert.timestamp).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}
                  </div>
                </div>
              </div>

              <div className="mt-auto">
                <p className="text-[10px] text-gray-500 font-mono text-center mb-3">
                  WARNING: Dispatching unit overrides automated signal cycles in sector.
                </p>
                <button 
                  onClick={() => {
                    alert("UNIT DISPATCHED. API endpoint for clearing alert would be called here.");
                  }}
                  className="w-full py-4 rounded font-bold uppercase tracking-widest text-sm bg-red-600 hover:bg-red-500 text-white shadow-[0_0_20px_rgba(220,38,38,0.3)] transition-all flex items-center justify-center gap-2"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" className="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"></path>
                    <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"></path>
                  </svg>
                  Dispatch Unit
                </button>
              </div>
            </div>
          ) : (
             <div className="flex-1 flex items-center justify-center text-gray-600 text-xs font-mono uppercase">
               Select an alert to view details
             </div>
          )}
        </aside>

      </div>
    </div>
  );
}
