"use client";

import React, { useState, useEffect, useRef, useCallback } from "react";
import { Plane, Globe, Sparkles, CalendarRange, List, Shield, Bell } from "lucide-react";
import ChatInterface from "@/components/chat-interface";
import PriceMatrix from "@/components/price-matrix";
import FlightResults from "@/components/flight-results";
import AlertsList from "@/components/alerts-list";

interface Message {
  role: "user" | "model";
  content: string;
}

export default function Home() {
  const [lang, setLang] = useState<"pt" | "en">("pt");
  const [activeTab, setActiveTab] = useState<"matrix" | "results" | "alerts">("results");
  const [backendHealth, setBackendHealth] = useState<{ status: string; provider: string } | null>(null);
  
  // Chat state
  const [messages, setMessages] = useState<Message[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [searchStatus, setSearchStatus] = useState("");
  
  // Flight data states
  const [flights, setFlights] = useState<any[]>([]);
  const [matrixData, setMatrixData] = useState<any>(null);
  const [selectedDepDate, setSelectedDepDate] = useState("");
  const [selectedRetDate, setSelectedRetDate] = useState<string | null>(null);
  
  // Alerts state
  const [alerts, setAlerts] = useState<any[]>([]);

  const socketRef = useRef<WebSocket | null>(null);

  // Fetch alerts from backend REST API
  const fetchAlerts = useCallback(async () => {
    try {
      const res = await fetch("http://localhost:8000/api/alerts");
      if (res.ok) {
        const data = await res.json();
        setAlerts(data.alerts || []);
      }
    } catch (err) {
      console.error("Failed to fetch price alerts:", err);
    }
  }, []);

  // Perform backend check on mount
  useEffect(() => {
    const checkHealth = async () => {
      try {
        const res = await fetch("http://localhost:8000/api/health");
        if (res.ok) {
          const data = await res.json();
          setBackendHealth(data);
        } else {
          setBackendHealth({ status: "error", provider: "none" });
        }
      } catch (err) {
        console.error("Backend health check failed:", err);
        setBackendHealth({ status: "error", provider: "none" });
      }
    };
    checkHealth();
    fetchAlerts();
  }, [fetchAlerts]);

  // Set up WebSocket connection
  const connectWebSocket = useCallback(() => {
    if (socketRef.current) return;

    const ws = new WebSocket("ws://localhost:8000/api/chat");
    socketRef.current = ws;

    ws.onopen = () => {
      console.log("WebSocket connected");
    };

    ws.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data);
        const { type, data } = payload;

        switch (type) {
          case "agent_thinking":
            setIsSearching(true);
            setSearchStatus(data.status || "");
            break;
            
          case "flight_results":
            setFlights(data);
            setActiveTab("results"); // auto switch to see results
            break;
            
          case "price_matrix":
            setMatrixData(data);
            // Default select the cheapest cell from matrix
            const cheapest = data.matrix?.find((c: any) => c.is_cheapest);
            if (cheapest) {
              setSelectedDepDate(cheapest.departure_date);
              setSelectedRetDate(cheapest.return_date);
            }
            setActiveTab("matrix"); // auto switch to matrix to see flexible options
            break;
            
          case "alert_registered":
            // Refresh DB list of alerts
            fetchAlerts();
            setActiveTab("alerts"); // Auto-switch to show configured alerts
            break;
            
          case "agent_message":
            setMessages((prev) => [...prev, { role: "model", content: data.content }]);
            setIsSearching(false);
            setSearchStatus("");
            break;
            
          case "agent_done":
            setIsSearching(false);
            setSearchStatus("");
            break;
            
          default:
            console.log("Unhandled WebSocket event:", payload);
        }
      } catch (err) {
        console.error("Error parsing WebSocket message:", err);
      }
    };

    ws.onerror = (err) => {
      console.error("WebSocket error:", err);
      setIsSearching(false);
    };

    ws.onclose = () => {
      console.log("WebSocket disconnected. Retrying in 3s...");
      socketRef.current = null;
      setTimeout(connectWebSocket, 3000);
    };
  }, [fetchAlerts]);

  useEffect(() => {
    connectWebSocket();
    return () => {
      if (socketRef.current) {
        socketRef.current.close();
      }
    };
  }, [connectWebSocket]);

  // Sending message function
  const handleSendMessage = (text: string) => {
    if (!socketRef.current || socketRef.current.readyState !== WebSocket.OPEN) {
      alert("A conexão com o backend está inativa. Tentando restabelecer...");
      return;
    }

    // Add user message to local state history
    const updatedMessages: Message[] = [...messages, { role: "user", content: text }];
    setMessages(updatedMessages);
    setIsSearching(true);
    setSearchStatus("Pensando...");

    // Send payload over WebSocket
    socketRef.current.send(
      JSON.stringify({
        message: text,
        history: messages, // Send history (without the new message, matching FastAPI loop)
      })
    );
  };

  // Callback when clicking a specific matrix price cell
  const handleSelectCell = (dep: string, ret: string | null) => {
    setSelectedDepDate(dep);
    setSelectedRetDate(ret);
    
    // Construct search details to notify the agent of user selection
    const formattedDep = dep;
    const formattedRet = ret ? ` e regresso a ${ret}` : " (só ida)";
    
    const requestText = lang === "pt"
      ? `Pesquise detalhes do voo para ida em ${formattedDep}${formattedRet}`
      : `Search flight details for departure on ${formattedDep}${ret ? ` returning on ${ret}` : " (one-way)"}`;
      
    handleSendMessage(requestText);
  };

  return (
    <div className="flex flex-col min-h-screen">
      {/* Top Navbar */}
      <header className="px-6 py-4 bg-gray-950/80 border-b border-gray-900 sticky top-0 z-50 backdrop-blur-md">
        <div className="max-w-7xl mx-auto flex items-center justify-between">
          <div className="flex items-center space-x-3.5">
            <div className="h-10 w-10 bg-violet-600 rounded-xl flex items-center justify-center shadow-lg shadow-violet-950/50">
              <Plane className="h-5 w-5 text-white rotate-45" />
            </div>
            <div>
              <div className="flex items-center space-x-1.5">
                <span className="font-extrabold text-lg text-white tracking-wider">AeroMilhas</span>
                <span className="text-[10px] bg-violet-500/20 text-violet-400 font-bold px-2 py-0.5 rounded-full border border-violet-500/30">
                  AI Agent
                </span>
              </div>
              <p className="text-xs text-gray-400 font-medium">
                {lang === "pt" ? "Buscador de Voos Inteligente" : "Smart Flight Finder Assistant"}
              </p>
            </div>
          </div>

          <div className="flex items-center space-x-4">
            {/* Status indicator */}
            {backendHealth && (
              <div className="hidden sm:flex items-center space-x-2 bg-gray-900 border border-gray-800 rounded-full px-3.5 py-1 text-xs">
                <Shield className="h-3.5 w-3.5 text-emerald-400" />
                <span className="text-gray-400">{lang === "pt" ? "Motor:" : "Engine:"}</span>
                <span className="text-white font-bold capitalize">
                  {backendHealth.provider === "serpapi" ? "Google Flights" : (backendHealth.provider === "amadeus" ? "Amadeus API" : (backendHealth.provider === "kiwi" ? "Kiwi Tequila" : "Mock Sandbox"))}
                </span>
              </div>
            )}

            {/* Language Switcher */}
            <button
              onClick={() => setLang((l) => (l === "pt" ? "en" : "pt"))}
              className="flex items-center space-x-1.5 px-3 py-1.5 rounded-xl border border-gray-800 bg-gray-900 hover:bg-gray-800 transition-all duration-300 text-xs font-semibold text-gray-300 cursor-pointer"
            >
              <Globe className="h-3.5 w-3.5" />
              <span>{lang === "pt" ? "EN" : "PT"}</span>
            </button>
          </div>
        </div>
      </header>

      {/* Main Layout Area */}
      <main className="flex-1 max-w-7xl w-full mx-auto p-4 md:p-6 grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        {/* Left Side: Agent Conversational Chat */}
        <section className="lg:col-span-5 h-full">
          <ChatInterface
            messages={messages}
            onSendMessage={handleSendMessage}
            isSearching={isSearching}
            searchStatus={searchStatus}
            lang={lang}
          />
        </section>

        {/* Right Side: Interactive Data View */}
        <section className="lg:col-span-7 space-y-6">
          {/* Main Dashboard Control Tabs */}
          <div className="flex items-center justify-between border-b border-gray-800 pb-3">
            <div className="flex bg-gray-950 p-1 rounded-xl border border-gray-900">
              <button
                onClick={() => setActiveTab("results")}
                className={`flex items-center space-x-2 px-3 py-1.5 text-xs font-semibold rounded-lg transition-all duration-300 cursor-pointer ${
                  activeTab === "results"
                    ? "bg-violet-600 text-white shadow-lg"
                    : "text-gray-400 hover:text-white"
                }`}
              >
                <List className="h-3.5 w-3.5" />
                <span>{lang === "pt" ? "Voos Encontrados" : "Flight Offers"}</span>
              </button>
              
              <button
                onClick={() => setActiveTab("matrix")}
                className={`flex items-center space-x-2 px-3 py-1.5 text-xs font-semibold rounded-lg transition-all duration-300 cursor-pointer ${
                  activeTab === "matrix"
                    ? "bg-violet-600 text-white shadow-lg"
                    : "text-gray-400 hover:text-white"
                }`}
              >
                <CalendarRange className="h-3.5 w-3.5" />
                <span>{lang === "pt" ? "Datas Flexíveis" : "Flexible Dates"}</span>
              </button>

              <button
                onClick={() => setActiveTab("alerts")}
                className={`flex items-center space-x-2 px-3 py-1.5 text-xs font-semibold rounded-lg transition-all duration-300 cursor-pointer ${
                  activeTab === "alerts"
                    ? "bg-violet-600 text-white shadow-lg"
                    : "text-gray-400 hover:text-white"
                }`}
              >
                <Bell className="h-3.5 w-3.5" />
                <span>{lang === "pt" ? "Alertas 24h" : "24/7 Alerts"}</span>
              </button>
            </div>
            
            {activeTab === "results" && flights.length > 0 && (
              <span className="text-xs text-gray-500 font-medium">
                {lang === "pt" ? `${flights.length} voos carregados` : `${flights.length} flights loaded`}
              </span>
            )}

            {activeTab === "alerts" && alerts.length > 0 && (
              <span className="text-xs text-gray-500 font-medium">
                {lang === "pt" ? `${alerts.length} alertas ativos` : `${alerts.length} active alerts`}
              </span>
            )}
          </div>

          {/* Active Tab Panel */}
          <div className="min-h-[450px]">
            {activeTab === "results" && (
              <FlightResults flights={flights} lang={lang} />
            )}
            {activeTab === "matrix" && (
              <PriceMatrix
                matrixData={matrixData}
                onSelectCell={handleSelectCell}
                selectedDepDate={selectedDepDate}
                selectedRetDate={selectedRetDate}
                lang={lang}
              />
            )}
            {activeTab === "alerts" && (
              <AlertsList
                alerts={alerts}
                onRefreshAlerts={fetchAlerts}
                lang={lang}
              />
            )}
          </div>
          
          {/* Information Notice Panel */}
          {flights.length === 0 && (
            <div className="p-5 rounded-2xl bg-violet-950/15 border border-violet-900/30 flex items-start space-x-4">
              <div className="p-2.5 bg-violet-950/50 text-violet-400 rounded-xl shrink-0 mt-0.5 border border-violet-900/30">
                <Sparkles className="h-4.5 w-4.5 animate-pulse" />
              </div>
              <div className="space-y-1">
                <h4 className="text-sm font-semibold text-white">
                  {lang === "pt" ? "Busca Integrada por IA" : "AI Assisted Search"}
                </h4>
                <p className="text-xs text-gray-400 leading-relaxed">
                  {lang === "pt"
                    ? "Nosso agente não apenas busca as datas inseridas, mas também analisa as flutuações de tarifas na vizinhança. Se encontrar datas mais baratas, elas serão destacadas na matriz de datas flexíveis."
                    : "Our agent queries and maps out fare variations. If better deals exist on adjacent days, they will be highlighted on the Flexible Dates matrix."}
                </p>
              </div>
            </div>
          )}
        </section>
      </main>

      {/* Footer copyright */}
      <footer className="mt-auto py-6 border-t border-gray-900/60 bg-gray-950/20 text-center text-xs text-gray-600">
        <p>© 2026 AeroMilhas. {lang === "pt" ? "Desenvolvido com IA e Next.js." : "Built with AI and Next.js."}</p>
      </footer>
    </div>
  );
}
