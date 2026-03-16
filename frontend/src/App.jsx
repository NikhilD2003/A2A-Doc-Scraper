import React, { useState, useRef, useEffect } from 'react';
import { Play, Square, Globe, Terminal, Server, MessageSquare, Network, Send, ZoomIn, ZoomOut, Maximize } from 'lucide-react';

export default function App() {
  const [url, setUrl] = useState("https://a2a-protocol.org/latest/");
  const [limit, setLimit] = useState(500);

  const [logs, setLogs] = useState([]);
  const [isRunning, setIsRunning] = useState(false);
  const [ws, setWs] = useState(null);

  const [activeTab, setActiveTab] = useState('console');

  const [chatInput, setChatInput] = useState("");
  const [chatHistory, setChatHistory] = useState([{ role: "system", text: "Documentation ready! Ask me anything about it." }]);
  const [isTyping, setIsTyping] = useState(false);

  const [graphData, setGraphData] = useState({ nodes: [], links: [] });

  const [graphZoom, setGraphZoom] = useState(1);
  const [graphPan, setGraphPan] = useState({ x: 0, y: 0 });
  const [isDraggingGraph, setIsDraggingGraph] = useState(false);
  const [dragStartPos, setDragStartPos] = useState({ x: 0, y: 0 });

  const logsEndRef = useRef(null);
  const chatEndRef = useRef(null);

  useEffect(() => { logsEndRef.current?.scrollIntoView({ behavior: "smooth" }); }, [logs, activeTab]);
  useEffect(() => { chatEndRef.current?.scrollIntoView({ behavior: "smooth" }); }, [chatHistory, isTyping, activeTab]);

  const startScraping = () => {
    if (!url) return;
    setIsRunning(true);
    setActiveTab('console');
    setLogs(["🔌 Connecting to A2A Backend..."]);

    const liveBackendUrl = "wss://a2a-doc-scraper-api.onrender.com/ws";
    const websocket = new WebSocket(liveBackendUrl);
    setWs(websocket);

    websocket.onopen = () => {
      setLogs(prev => [...prev, "✅ Connected to Cloud Agent! Planning workflow..."]);
      websocket.send(JSON.stringify({ url: url, limit: parseInt(limit) }));
    };

    websocket.onmessage = async (event) => {
      const msg = event.data;
      if (msg === "DONE") {
        setIsRunning(false);
        websocket.close();
        fetchGraphData();
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

    websocket.onerror = () => {
      setLogs(prev => [...prev, "❌ Connection Failed! Check if Render server is awake."]);
      setIsRunning(false);
    };

    websocket.onclose = () => {
      setIsRunning(false);
      setWs(null);
    };
  };

  const stopScraping = () => { if (ws) ws.close(); };

  const fetchGraphData = async () => {
    try {
      const res = await fetch(`https://a2a-doc-scraper-api.onrender.com/api/graph?url=${encodeURIComponent(url)}`);
      const data = await res.json();
      setGraphData(data);
      if (data.nodes.length > 20) setGraphZoom(0.6);
      else setGraphZoom(1);
      setGraphPan({ x: 0, y: 0 });
    } catch (err) {
      console.error("Failed to load graph", err);
    }
  };

  const sendChatMessage = async () => {
    if (!chatInput.trim()) return;

    const userMsg = chatInput;
    setChatHistory(prev => [...prev, { role: "user", text: userMsg }]);
    setChatInput("");
    setIsTyping(true);

    try {
      const res = await fetch(`https://a2a-doc-scraper-api.onrender.com/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: url, question: userMsg })
      });
      const data = await res.json();
      setChatHistory(prev => [...prev, { role: "system", text: data.answer }]);
    } catch (err) {
      setChatHistory(prev => [...prev, { role: "system", text: "❌ Failed to reach AI backend." }]);
    }
    setIsTyping(false);
  };

  const formatLog = (log) => {
    if (log.includes('SCRAPING:')) return <><span className="text-blue-400">🔍 SCRAPING:</span> <span className="text-slate-300">{log.split('SCRAPING:')[1]}</span></>;
    if (log.includes('✅') || log.includes('SUCCESS')) return <span className="text-green-400">{log}</span>;
    if (log.includes('❌') || log.includes('Failed')) return <span className="text-red-400">{log}</span>;
    if (log.includes('✨') || log.includes('🚀')) return <span className="text-purple-400 font-bold">{log}</span>;
    return <span className="text-slate-400">{log}</span>;
  };

  // Helper to make the AI's markdown bolding look nice
  const formatChatMessage = (text) => {
    return text.split(/(\*\*.*?\*\*)/g).map((part, i) => {
      if (part.startsWith('**') && part.endsWith('**')) {
        return <strong key={i} className="font-bold text-white">{part.slice(2, -2)}</strong>;
      }
      return <span key={i}>{part}</span>;
    });
  };

  const renderGraph = () => {
    if (!graphData.nodes.length) return null;

    const width = 800;
    const height = 500;
    const centerX = width / 2;
    const centerY = height / 2;

    const dynamicRadius = Math.max(200, graphData.nodes.length * 15);

    const positionedNodes = graphData.nodes.map((node, i) => {
      const angle = (i / graphData.nodes.length) * 2 * Math.PI;
      return {
        ...node,
        x: centerX + dynamicRadius * Math.cos(angle),
        y: centerY + dynamicRadius * Math.sin(angle)
      };
    });

    const getNodeCoords = (id) => positionedNodes.find(n => n.id === id) || { x: centerX, y: centerY };

    return (
      <div className="relative w-full h-full overflow-hidden">
        <div className="absolute top-4 right-4 flex flex-col space-y-2 bg-slate-800 p-2 rounded-lg border border-slate-700 z-10 shadow-lg">
          <button onClick={() => setGraphZoom(z => Math.min(z + 0.2, 5))} className="p-2 hover:bg-slate-700 hover:text-white rounded text-slate-400 transition-colors" title="Zoom In"><ZoomIn size={18}/></button>
          <button onClick={() => setGraphZoom(z => Math.max(z - 0.2, 0.1))} className="p-2 hover:bg-slate-700 hover:text-white rounded text-slate-400 transition-colors" title="Zoom Out"><ZoomOut size={18}/></button>
          <button onClick={() => { setGraphZoom(graphData.nodes.length > 20 ? 0.6 : 1); setGraphPan({x:0, y:0}); }} className="p-2 hover:bg-slate-700 hover:text-white rounded text-slate-400 transition-colors" title="Reset View"><Maximize size={18}/></button>
        </div>

        <svg
          width="100%" height="100%" viewBox={`0 0 ${width} ${height}`} className="w-full h-full"
          onWheel={(e) => {
            const scaleAmount = -e.deltaY * 0.001;
            setGraphZoom(z => Math.max(0.1, Math.min(z + scaleAmount, 5)));
          }}
          onMouseDown={(e) => {
            setIsDraggingGraph(true);
            setDragStartPos({ x: e.clientX - graphPan.x, y: e.clientY - graphPan.y });
          }}
          onMouseMove={(e) => {
            if (!isDraggingGraph) return;
            setGraphPan({ x: e.clientX - dragStartPos.x, y: e.clientY - dragStartPos.y });
          }}
          onMouseUp={() => setIsDraggingGraph(false)}
          onMouseLeave={() => setIsDraggingGraph(false)}
          style={{ cursor: isDraggingGraph ? 'grabbing' : 'grab', touchAction: 'none' }}
        >
          <g transform={`translate(${graphPan.x}, ${graphPan.y}) translate(${centerX}, ${centerY}) scale(${graphZoom}) translate(-${centerX}, -${centerY})`}>
            {graphData.links.map((link, i) => {
              const source = getNodeCoords(link.source);
              const target = getNodeCoords(link.target);
              return (
                <line key={i} x1={source.x} y1={source.y} x2={target.x} y2={target.y} stroke="rgba(148, 163, 184, 0.2)" strokeWidth="1" />
              );
            })}
            {positionedNodes.map((node, i) => (
              <g key={i} transform={`translate(${node.x}, ${node.y})`}>
                <circle r="6" fill="#8b5cf6" className="shadow-lg drop-shadow-[0_0_8px_rgba(139,92,246,0.6)]" />
                <text y="20" fill="#cbd5e1" fontSize="11" fontWeight="500" textAnchor="middle" className="pointer-events-none select-none drop-shadow-md">
                  {node.id.split('/').filter(Boolean).pop() || node.id}
                </text>
              </g>
            ))}
          </g>
        </svg>
      </div>
    );
  };

  return (
    <div className="min-h-screen bg-slate-900 text-slate-200 p-8 font-sans">
      <div className="max-w-6xl mx-auto space-y-6">

        {/* HEADER */}
        <div className="flex items-center space-x-3 mb-8">
          <Server className="w-8 h-8 text-blue-400" />
          <h1 className="text-3xl font-bold text-white tracking-tight">A2A Documentation Scraper</h1>
        </div>

        {/* CONFIGURATION PANEL */}
        <div className="bg-slate-800 rounded-xl border border-slate-700 p-6 shadow-xl">
          <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
            <div className="md:col-span-3 space-y-2">
              <label className="text-sm font-medium text-slate-400">Target URL</label>
              <div className="relative">
                <Globe className="absolute left-3 top-3 w-5 h-5 text-slate-500" />
                <input
                  type="text" value={url} onChange={(e) => setUrl(e.target.value)} disabled={isRunning}
                  className="w-full bg-slate-900 border border-slate-700 rounded-lg py-2.5 pl-10 pr-4 text-white focus:outline-none focus:border-blue-500 disabled:opacity-50"
                />
              </div>
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium text-slate-400 flex justify-between">
                <span>Page Limit</span>
                <span className="text-blue-400">{limit} Pages</span>
              </label>
              <div className="flex items-center h-10">
                <input
                  type="range" min="10" max="1000" step="10" value={limit} onChange={(e) => setLimit(e.target.value)} disabled={isRunning}
                  className="w-full h-2 bg-slate-700 rounded-lg appearance-none cursor-pointer accent-blue-500"
                />
              </div>
            </div>
          </div>
          <div className="mt-6 flex justify-end">
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

        {/* TABS NAVIGATION */}
        <div className="flex space-x-2 border-b border-slate-700 pb-2">
          <button onClick={() => setActiveTab('console')} className={`flex items-center px-4 py-2 rounded-t-lg transition-colors ${activeTab === 'console' ? 'bg-slate-800 text-blue-400 border-t border-l border-r border-slate-700' : 'text-slate-500 hover:text-slate-300'}`}>
            <Terminal className="w-4 h-4 mr-2" /> Console Logs
          </button>
          <button onClick={() => { setActiveTab('graph'); fetchGraphData(); }} className={`flex items-center px-4 py-2 rounded-t-lg transition-colors ${activeTab === 'graph' ? 'bg-slate-800 text-green-400 border-t border-l border-r border-slate-700' : 'text-slate-500 hover:text-slate-300'}`}>
            <Network className="w-4 h-4 mr-2" /> Knowledge Graph
          </button>
          <button onClick={() => setActiveTab('chat')} className={`flex items-center px-4 py-2 rounded-t-lg transition-colors ${activeTab === 'chat' ? 'bg-slate-800 text-purple-400 border-t border-l border-r border-slate-700' : 'text-slate-500 hover:text-slate-300'}`}>
            <MessageSquare className="w-4 h-4 mr-2" /> Chat with Docs
          </button>
        </div>

        {/* TAB CONTENT AREAS (Increased height to 600px for better reading) */}
        <div className="bg-black rounded-b-xl rounded-tr-xl border border-slate-800 shadow-2xl overflow-hidden flex flex-col h-[600px]">

          {activeTab === 'console' && (
            <div className="flex-1 p-4 overflow-y-auto font-mono text-sm space-y-2 min-h-0">
              {logs.length === 0 && <div className="text-slate-600 italic">Ready to start scraping...</div>}
              {logs.map((log, index) => (
                <div key={index} className="flex items-start">
                  <span className="text-slate-600 mr-3 mt-0.5 shrink-0">[{new Date().toLocaleTimeString()}]</span>
                  <span className="break-all">{formatLog(log)}</span>
                </div>
              ))}
              <div ref={logsEndRef} />
            </div>
          )}

          {activeTab === 'graph' && (
            <div className="flex-1 relative bg-slate-900 flex items-center justify-center min-h-0">
              {graphData.nodes.length > 0 ? (
                renderGraph()
              ) : (
                <div className="text-slate-500 flex flex-col items-center">
                  <Network className="w-12 h-12 mb-4 opacity-50" />
                  <p>No graph data found for this URL.</p>
                  <p className="text-sm mt-2">Make sure you have scraped it first!</p>
                </div>
              )}
            </div>
          )}

          {/* CHAT TAB - FIXED SCROLLING AND PINNED INPUT */}
          {activeTab === 'chat' && (
            <div className="flex-1 flex flex-col bg-slate-900 min-h-0">
              {/* Message Container: overflow-y-auto enables scrolling, min-h-0 prevents box from stretching */}
              <div className="flex-1 p-6 overflow-y-auto space-y-6 min-h-0">
                {chatHistory.map((msg, idx) => (
                  <div key={idx} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                    {/* Added whitespace-pre-wrap to respect paragraph breaks in Markdown */}
                    <div className={`max-w-[85%] rounded-2xl p-4 whitespace-pre-wrap leading-relaxed shadow-md ${msg.role === 'user' ? 'bg-blue-600 text-white' : 'bg-slate-800 border border-slate-700 text-slate-300'}`}>
                      {formatChatMessage(msg.text)}
                    </div>
                  </div>
                ))}
                {isTyping && (
                  <div className="flex justify-start"><div className="bg-slate-800 border border-slate-700 rounded-2xl p-4 text-slate-400 animate-pulse">AI is thinking...</div></div>
                )}
                <div ref={chatEndRef} />
              </div>

              {/* Input Area: shrink-0 keeps it permanently pinned to the bottom */}
              <div className="shrink-0 p-4 border-t border-slate-800 bg-slate-950">
                <div className="flex space-x-4">
                  <input
                    type="text" value={chatInput} onChange={(e) => setChatInput(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && sendChatMessage()}
                    placeholder="Ask a question about the scraped docs..."
                    className="flex-1 bg-slate-900 border border-slate-700 rounded-lg px-4 py-3 text-white focus:outline-none focus:border-purple-500"
                  />
                  <button onClick={sendChatMessage} disabled={isTyping || !chatInput} className="bg-purple-600 hover:bg-purple-500 text-white px-6 rounded-lg transition-colors disabled:opacity-50">
                    <Send className="w-5 h-5" />
                  </button>
                </div>
              </div>
            </div>
          )}

        </div>
      </div>
    </div>
  );
}