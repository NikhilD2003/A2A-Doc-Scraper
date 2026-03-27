import React, { useState, useRef, useEffect, useCallback, useMemo } from 'react';
import { Play, Square, Globe, Terminal, Server, MessageSquare, Network, Send, X, ExternalLink } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

// NEW GRAPHING IMPORTS
import ReactFlow, {
  Controls,
  Background,
  useNodesState,
  useEdgesState,
  MarkerType
} from 'reactflow';
import 'reactflow/dist/style.css';
import dagre from 'dagre';

// --- HELPER FUNCTION: AUTO-LAYOUT THE TREE ---
const getLayoutedElements = (nodes, edges, direction = 'TB') => {
  const dagreGraph = new dagre.graphlib.Graph();
  dagreGraph.setDefaultEdgeLabel(() => ({}));

  const nodeWidth = 250;
  const nodeHeight = 50;

  dagreGraph.setGraph({ rankdir: direction });

  nodes.forEach((node) => {
    dagreGraph.setNode(node.id, { width: nodeWidth, height: nodeHeight });
  });

  edges.forEach((edge) => {
    dagreGraph.setEdge(edge.source, edge.target);
  });

  dagre.layout(dagreGraph);

  nodes.forEach((node) => {
    const nodeWithPosition = dagreGraph.node(node.id);
    node.targetPosition = 'top';
    node.sourcePosition = 'bottom';
    node.position = {
      x: nodeWithPosition.x - nodeWidth / 2,
      y: nodeWithPosition.y - nodeHeight / 2,
    };
    return node;
  });

  return { nodes, edges };
};


export default function App() {
  // 🚀 DEPLOYMENT CONFIG: Use Cloud URL if deployed, otherwise fallback to localhost
  const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";
  const WS_BASE = API_BASE.replace(/^http/, 'ws');

  const [url, setUrl] = useState("");
  const [limit, setLimit] = useState(500);
  const [logs, setLogs] = useState([]);
  const [isRunning, setIsRunning] = useState(false);
  const [ws, setWs] = useState(null);
  const [activeTab, setActiveTab] = useState('console');
  const [chatInput, setChatInput] = useState("");
  const [chatHistory, setChatHistory] = useState([{ role: "system", text: "Documentation ready! Ask me anything about it." }]);
  const [isTyping, setIsTyping] = useState(false);
  const [selectedNodeData, setSelectedNodeData] = useState(null);

  const logsEndRef = useRef(null);
  const chatEndRef = useRef(null);

  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);

  useEffect(() => { logsEndRef.current?.scrollIntoView({ behavior: "smooth" }); }, [logs, activeTab]);
  useEffect(() => { chatEndRef.current?.scrollIntoView({ behavior: "smooth" }); }, [chatHistory, isTyping, activeTab]);

  const startScraping = () => {
    if (!url) return;
    setIsRunning(true);
    setActiveTab('console');
    setLogs(["🔌 Connecting to A2A Backend..."]);

    // 🚀 USING DYNAMIC WEBSOCKET URL
    const liveBackendUrl = `${WS_BASE}/ws`;
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
      setLogs(prev => [...prev, "❌ Connection Failed! Check if server is awake."]);
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
      // 🚀 USING DYNAMIC API URL
      const res = await fetch(`${API_BASE}/api/graph?url=${encodeURIComponent(url)}`);
      const data = await res.json();

      const initialNodes = data.nodes.map((n) => {
        const isFolder = n.isVirtual;

        return {
          id: n.id,
          data: {
              label: isFolder
                ? `📁 ${n.id.split('/').filter(Boolean).pop().toUpperCase()}`
                : n.id.split('/').filter(Boolean).pop().replace('.html', '') || 'Home',
              fullContent: n.content,
              url: n.id,
              isVirtual: isFolder
          },
          position: { x: 0, y: 0 },
          style: {
              background: isFolder ? '#334155' : '#1e293b',
              color: isFolder ? '#fbbf24' : '#e2e8f0',
              border: isFolder ? '2px solid #fbbf24' : '1px solid #475569',
              borderRadius: '8px',
              padding: '10px',
              fontSize: isFolder ? '14px' : '12px',
              fontWeight: isFolder ? 'bold' : 'normal',
              width: 250,
              textAlign: 'center',
              boxShadow: isFolder ? '0 0 15px rgba(251, 191, 36, 0.3)' : 'none'
          }
        };
      });

      const initialEdges = data.links.map((l, index) => ({
        id: `e${index}-${l.source}-${l.target}`,
        source: l.source,
        target: l.target,
        type: 'smoothstep',
        animated: false,
        markerEnd: { type: MarkerType.ArrowClosed, width: 20, height: 20, color: '#64748b' },
        style: { stroke: '#64748b', strokeWidth: 1.5 },
      }));

      const { nodes: layoutedNodes, edges: layoutedEdges } = getLayoutedElements(
        initialNodes,
        initialEdges,
        'TB'
      );

      setNodes(layoutedNodes);
      setEdges(layoutedEdges);

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
      // 🚀 USING DYNAMIC API URL
      const res = await fetch(`${API_BASE}/api/chat`, {
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

  const formatChatMessage = (text) => {
    return text.split(/(\*\*.*?\*\*)/g).map((part, i) => {
      if (part.startsWith('**') && part.endsWith('**')) {
        return <strong key={i} className="font-bold text-white">{part.slice(2, -2)}</strong>;
      }
      return <span key={i}>{part}</span>;
    });
  };

  const onNodeClick = useCallback((event, node) => {
    setSelectedNodeData(node.data);
  }, []);

  return (
    <div className="min-h-screen bg-slate-900 text-slate-200 p-8 font-sans">
      <div className="max-w-6xl mx-auto space-y-6">
        <div className="flex items-center space-x-3 mb-8">
          <Server className="w-8 h-8 text-blue-400" />
          <h1 className="text-3xl font-bold text-white tracking-tight">A2A Documentation Scraper</h1>
        </div>

        <div className="bg-slate-800 rounded-xl border border-slate-700 p-6 shadow-xl">
          <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
            <div className="md:col-span-3 space-y-2">
              <label className="text-sm font-medium text-slate-400">Target URL</label>
              <div className="relative">
                <Globe className="absolute left-3 top-3 w-5 h-5 text-slate-500" />
                <input
                  type="text" value={url} onChange={(e) => setUrl(e.target.value)} disabled={isRunning}
                  placeholder="https://example.com"
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
              <button onClick={startScraping} className="flex items-center bg-blue-600 hover:bg-blue-500 text-white px-6 py-2.5 rounded-lg font-medium shadow-lg transition-all disabled:opacity-50 disabled:cursor-not-allowed" disabled={!url}>
                <Play className="w-5 h-5 mr-2" /> Start Pipeline
              </button>
            ) : (
              <button onClick={stopScraping} className="flex items-center bg-red-500 hover:bg-red-400 text-white px-6 py-2.5 rounded-lg font-medium animate-pulse">
                <Square className="w-5 h-5 mr-2" /> Stop Scraping
              </button>
            )}
          </div>
        </div>

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

        <div className="bg-black rounded-b-xl rounded-tr-xl border border-slate-800 shadow-2xl overflow-hidden flex flex-col h-[600px] relative">

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
            <div className="flex-1 w-full h-full bg-[#0f172a]">
              {nodes.length > 0 ? (
                <ReactFlow
                  nodes={nodes}
                  edges={edges}
                  onNodesChange={onNodesChange}
                  onEdgesChange={onEdgesChange}
                  onNodeClick={onNodeClick}
                  fitView
                  minZoom={0.1}
                >
                  <Background color="#334155" gap={20} />
                  <Controls className="bg-slate-800 fill-slate-400 border-slate-700" />
                </ReactFlow>
              ) : (
                <div className="h-full flex flex-col items-center justify-center text-slate-500">
                  <Network className="w-12 h-12 mb-4 opacity-50" />
                  <p>No graph data found for this URL.</p>
                  <p className="text-sm mt-2">Make sure you have scraped it first!</p>
                </div>
              )}
            </div>
          )}

          {activeTab === 'chat' && (
            <div className="flex-1 flex flex-col bg-slate-900 min-h-0">
              <div className="flex-1 p-6 overflow-y-auto space-y-6 min-h-0">
                {chatHistory.map((msg, idx) => (
                  <div key={idx} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
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

          {selectedNodeData && activeTab === 'graph' && (
            <div className="absolute top-0 right-0 w-96 h-full bg-slate-900 border-l border-slate-700 shadow-2xl z-50 flex flex-col animate-in slide-in-from-right duration-300">
               <div className="p-4 border-b border-slate-800 flex justify-between items-center bg-slate-800/50">
                 <h3 className="font-bold text-blue-400 truncate pr-2">{selectedNodeData.label}</h3>
                 <button onClick={() => setSelectedNodeData(null)} className="text-slate-400 hover:text-white transition-colors">
                   <X size={20} />
                 </button>
               </div>

               <div className="flex-1 overflow-y-auto p-5 space-y-4 custom-scrollbar">
                 <div>
                   <label className="text-[10px] uppercase tracking-wider text-slate-500 font-bold">Source URL</label>
                   <a href={selectedNodeData.url} target="_blank" rel="noreferrer" className="text-xs text-blue-500 hover:underline flex items-center mt-1 break-all">
                     {selectedNodeData.url} <ExternalLink size={10} className="ml-1 shrink-0" />
                   </a>
                 </div>

                 <hr className="border-slate-800" />

                 <div>
                   <label className="text-[10px] uppercase tracking-wider text-slate-500 font-bold mb-3 block">Scraped Content</label>
                   <div className="text-sm text-slate-300 leading-relaxed prose prose-invert prose-sm max-w-none prose-pre:bg-slate-800 prose-pre:border prose-pre:border-slate-700 prose-a:text-blue-400">
                     {selectedNodeData.fullContent ? (
                       <ReactMarkdown remarkPlugins={[remarkGfm]}>
                         {selectedNodeData.fullContent}
                       </ReactMarkdown>
                     ) : (
                       <span className="italic text-slate-500">No content extracted for this node.</span>
                     )}
                   </div>
                 </div>
               </div>
            </div>
          )}

        </div>
      </div>
    </div>
  );
}