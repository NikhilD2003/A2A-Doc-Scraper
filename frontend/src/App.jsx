import React, { useState, useRef, useEffect } from 'react';
import { Play, Square, Globe, Terminal, Server } from 'lucide-react';

export default function App() {
  const [url, setUrl] = useState("https://github.com/NikhilD2003/ET-BERT-Encrypted-Traffic-Classification");

  const [logs, setLogs] = useState([]);
  const [isRunning, setIsRunning] = useState(false);
  const [ws, setWs] = useState(null);
  const logsEndRef = useRef(null);

  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs]);

  const startScraping = () => {
    if (!url) return;

    setIsRunning(true);
    setLogs(["🔌 Connecting to A2A Backend..."]);

    // Ensure we use wss:// for the live Vercel deployment
    const liveBackendUrl = "wss://a2a-doc-scraper.onrender.com/ws";

    const websocket = new WebSocket(liveBackendUrl);
    setWs(websocket);

    websocket.onopen = () => {
      setLogs(prev => [...prev, "✅ Connected to Cloud Agent! Planning workflow..."]);
      websocket.send(JSON.stringify({ url: url }));
    };

    websocket.onmessage = async (event) => {
      const msg = event.data;
      if (msg === "DONE") {
        setIsRunning(false);
        websocket.close();
        return;
      }

      try {
        if (msg.startsWith("{")) {
          const data = JSON.parse(msg);
          if (data.type === "download") {
            const blob = new Blob([data.content], { type: 'text/markdown' });
            const downloadUrl = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = downloadUrl;
            a.download = data.filename;
            a.click();
            URL.revokeObjectURL(downloadUrl);
            setLogs(prev => [...prev, "✅ SUCCESS! File downloaded."]);
            return;
          }
        }
      } catch (e) {}
      setLogs(prev => [...prev, msg]);
    };

    websocket.onerror = (error) => {
      setLogs(prev => [
        ...prev,
        "❌ Connection Failed!",
        "💡 Hint: If your Render server is on the Free Tier, it may take 60 seconds to wake up. Please wait and try again."
      ]);
      setIsRunning(false);
    };

    websocket.onclose = () => {
      setIsRunning(false);
      setWs(null);
    };
  };

  const stopScraping = () => {
    if (ws) ws.close();
  };

  return (
    <div className="min-h-screen bg-slate-900 text-slate-200 p-8 font-sans">
      <div className="max-w-5xl mx-auto space-y-6">
        <div className="flex items-center space-x-3 mb-8">
          <Server className="w-8 h-8 text-blue-400" />
          <h1 className="text-3xl font-bold text-white">A2A Documentation Scraper</h1>
        </div>

        <div className="bg-slate-800 rounded-xl border border-slate-700 p-6 shadow-xl">
          <h2 className="text-xl font-semibold text-white mb-6 flex items-center">
            <Globe className="w-5 h-5 mr-2 text-slate-400" />
            Configuration
          </h2>
          <div className="space-y-2">
            <label className="text-sm font-medium text-slate-400">Target URL</label>
            <div className="relative">
              <Globe className="absolute left-3 top-3 w-5 h-5 text-slate-500" />
              <input
                type="text"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                disabled={isRunning}
                className="w-full bg-slate-900 border border-slate-700 rounded-lg py-2.5 pl-10 pr-4 text-white focus:outline-none focus:border-blue-500 disabled:opacity-50"
              />
            </div>
          </div>
          <div className="mt-8 flex justify-end">
            {!isRunning ? (
              <button onClick={startScraping} className="flex items-center bg-blue-600 hover:bg-blue-500 text-white px-6 py-2.5 rounded-lg font-medium shadow-lg transition-all">
                <Play className="w-5 h-5 mr-2" /> Start Pipeline
              </button>
            ) : (
              <button onClick={stopScraping} className="flex items-center bg-red-500 hover:bg-red-400 text-white px-6 py-2.5 rounded-lg font-medium animate-pulse">
                <Square className="w-5 h-5 mr-2" /> Stop Scraping
              </button>
            )}
          </div>
        </div>

        <div className="bg-black rounded-xl border border-slate-800 shadow-2xl overflow-hidden flex flex-col h-[500px]">
          <div className="bg-slate-900 border-b border-slate-800 px-4 py-3 flex items-center justify-between text-slate-400 text-sm">
            <div className="flex items-center"><Terminal className="w-4 h-4 mr-2" /> Live Output Console</div>
          </div>
          <div className="flex-1 p-4 overflow-y-auto font-mono text-sm space-y-2">
            {logs.map((log, index) => (
              <div key={index} className={`${log.includes('❌') ? 'text-red-400' : log.includes('✅') ? 'text-green-400' : 'text-slate-300'}`}>
                <span className="text-slate-600 mr-2">[{new Date().toLocaleTimeString()}]</span> {log}
              </div>
            ))}
            <div ref={logsEndRef} />
          </div>
        </div>
      </div>
    </div>
  );
}