import React, { useState, useRef, useEffect } from 'react';
import { Play, Square, Globe, Terminal, Server } from 'lucide-react';

export default function App() {
  const [url, setUrl] = useState("https://github.com/NikhilD2003/ET-BERT-Encrypted-Traffic-Classification");

  const [logs, setLogs] = useState([]);
  const [isRunning, setIsRunning] = useState(false);
  const [ws, setWs] = useState(null);
  const logsEndRef = useRef(null);

  // Auto-scroll terminal to bottom when new logs arrive
  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs]);

  const startScraping = () => {
    if (!url) {
      alert("Please provide a Target URL.");
      return;
    }

    setIsRunning(true);
    setLogs(["🔌 Connecting to A2A Backend..."]);

    // Connect to your FastAPI WebSocket
    const websocket = new WebSocket("ws://127.0.0.1:8000/ws");
    setWs(websocket);

    websocket.onopen = () => {
      setLogs(prev => [...prev, "✅ Connected! Sending configuration..."]);
      // Send the config as a JSON string
      websocket.send(JSON.stringify({ url: url }));
    };

    websocket.onmessage = async (event) => {
      const msg = event.data;

      if (msg === "DONE") {
        setIsRunning(false);
        websocket.close();
        return;
      }

      // Check if the backend sent us a JSON file payload instead of a text log
      try {
        if (msg.startsWith("{")) {
          const data = JSON.parse(msg);
          if (data.type === "download") {
            setLogs(prev => [...prev, "💾 Opening 'Save As' dialogue..."]);

            try {
              // Trigger the native browser "Save As" popup!
              const handle = await window.showSaveFilePicker({
                suggestedName: data.filename,
                types: [{
                  description: 'Markdown Document',
                  accept: {'text/markdown': ['.md']},
                }],
              });

              const writable = await handle.createWritable();
              await writable.write(data.content);
              await writable.close();

              setLogs(prev => [...prev, `✅ SUCCESS! File securely saved to your chosen folder.`]);
            } catch (err) {
              if (err.name !== 'AbortError') {
                // Fallback for older browsers
                const blob = new Blob([data.content], { type: 'text/markdown' });
                const downloadUrl = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = downloadUrl;
                a.download = data.filename;
                a.click();
                URL.revokeObjectURL(downloadUrl);
                setLogs(prev => [...prev, "✅ File downloaded via browser fallback!"]);
              } else {
                setLogs(prev => [...prev, "⚠️ File save cancelled by user."]);
              }
            }
            return;
          }
        }
      } catch (e) {
        // Not a JSON payload, treat as a normal log message
      }

      setLogs(prev => [...prev, msg]);
    };

    websocket.onerror = (error) => {
      setLogs(prev => [...prev, "❌ WebSocket Error! Is the FastAPI server running on port 8000?"]);
      setIsRunning(false);
    };

    websocket.onclose = () => {
      setIsRunning(false);
      setWs(null);
    };
  };

  const stopScraping = () => {
    if (ws) {
      ws.close();
      setLogs(prev => [...prev, "🛑 Process manually stopped by user."]);
    }
  };

  return (
    <div className="min-h-screen bg-slate-900 text-slate-200 p-8 font-sans">
      <div className="max-w-5xl mx-auto space-y-6">

        {/* Header */}
        <div className="flex items-center space-x-3 mb-8">
          <Server className="w-8 h-8 text-blue-400" />
          <h1 className="text-3xl font-bold text-white">A2A Documentation Scraper</h1>
        </div>

        {/* Configuration Card */}
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
                className="w-full bg-slate-900 border border-slate-700 rounded-lg py-2.5 pl-10 pr-4 text-white focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 disabled:opacity-50 transition-colors"
                placeholder="https://github.com/YourName/Repo"
              />
            </div>
          </div>

          <div className="mt-8 flex justify-end">
            {!isRunning ? (
              <button
                onClick={startScraping}
                className="flex items-center bg-blue-600 hover:bg-blue-500 text-white px-6 py-2.5 rounded-lg font-medium transition-colors shadow-lg shadow-blue-900/20"
              >
                <Play className="w-5 h-5 mr-2" />
                Start Pipeline
              </button>
            ) : (
              <button
                onClick={stopScraping}
                className="flex items-center bg-red-500 hover:bg-red-400 text-white px-6 py-2.5 rounded-lg font-medium transition-colors shadow-lg shadow-red-900/20 animate-pulse"
              >
                <Square className="w-5 h-5 mr-2" />
                Stop Scraping
              </button>
            )}
          </div>
        </div>

        {/* Live Terminal Output */}
        <div className="bg-black rounded-xl border border-slate-800 shadow-2xl overflow-hidden flex flex-col h-[500px]">
          <div className="bg-slate-900 border-b border-slate-800 px-4 py-3 flex items-center justify-between">
            <div className="flex items-center text-slate-400 text-sm font-medium">
              <Terminal className="w-4 h-4 mr-2" />
              Live Output Console
            </div>
            <div className="flex space-x-2">
              <div className="w-3 h-3 rounded-full bg-red-500/20 border border-red-500/50"></div>
              <div className="w-3 h-3 rounded-full bg-yellow-500/20 border border-yellow-500/50"></div>
              <div className="w-3 h-3 rounded-full bg-green-500/20 border border-green-500/50"></div>
            </div>
          </div>

          <div className="flex-1 p-4 overflow-y-auto font-mono text-sm space-y-2">
            {logs.length === 0 ? (
              <div className="text-slate-600 italic">Waiting for pipeline to start...</div>
            ) : (
              logs.map((log, index) => (
                <div key={index} className={`${log.includes('❌') ? 'text-red-400' : log.includes('✅') || log.includes('SUCCESS') ? 'text-green-400' : log.includes('🔍') ? 'text-blue-300' : 'text-slate-300'}`}>
                  <span className="text-slate-600 mr-2">[{new Date().toLocaleTimeString()}]</span>
                  {log}
                </div>
              ))
            )}
            <div ref={logsEndRef} />
          </div>
        </div>

      </div>
    </div>
  );
}