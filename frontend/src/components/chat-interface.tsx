"use client";

import React, { useState, useRef, useEffect } from "react";
import { Send, Sparkles, Loader2, Plane } from "lucide-react";

interface Message {
  role: "user" | "model";
  content: string;
}

interface ChatInterfaceProps {
  messages: Message[];
  onSendMessage: (text: string) => void;
  isSearching: boolean;
  searchStatus: string;
  lang: "pt" | "en";
}

export default function ChatInterface({
  messages,
  onSendMessage,
  isSearching,
  searchStatus,
  lang,
}: ChatInterfaceProps) {
  const [input, setInput] = useState("");
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const suggestions = {
    pt: [
      "Quero passagens de Lisboa para Paris na segunda semana de Outubro.",
      "Buscar voo mais barato de São Paulo (GRU) para Nova Iorque (JFK) de 15 a 25 de Novembro.",
      "Passagem de ida de Londres para Tóquio dia 12 de Dezembro.",
    ],
    en: [
      "I want flights from Lisbon to Paris in the second week of October.",
      "Find the cheapest flight from Sao Paulo (GRU) to New York (JFK) from Nov 15th to 25th.",
      "One way ticket from London to Tokyo on December 12th.",
    ],
  };

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isSearching, searchStatus]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isSearching) return;
    onSendMessage(input);
    setInput("");
  };

  const handleSuggestionClick = (text: string) => {
    if (isSearching) return;
    onSendMessage(text);
  };

  return (
    <div className="flex flex-col h-[600px] md:h-[calc(100vh-12rem)] glass-panel rounded-2xl overflow-hidden shadow-2xl border border-gray-800">
      {/* Header */}
      <div className="px-6 py-4 bg-gray-900/80 border-b border-gray-800 flex items-center justify-between">
        <div className="flex items-center space-x-3">
          <div className="p-2 bg-violet-600/20 text-violet-400 rounded-lg">
            <Sparkles className="h-5 w-5" />
          </div>
          <div>
            <h2 className="font-semibold text-white tracking-wide">
              {lang === "pt" ? "Agente AeroMilhas" : "AeroMilhas Agent"}
            </h2>
            <p className="text-xs text-gray-400">
              {lang === "pt" ? "Especialista em Voos e Preços" : "Flights & Pricing Expert"}
            </p>
          </div>
        </div>
        {isSearching && (
          <div className="flex items-center space-x-2 text-xs text-violet-400 animate-pulse bg-violet-950/30 px-3 py-1 rounded-full border border-violet-900/50">
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
            <span>{lang === "pt" ? "Agente pensando..." : "Agent thinking..."}</span>
          </div>
        )}
      </div>

      {/* Message History */}
      <div className="flex-1 overflow-y-auto p-6 space-y-4">
        {messages.length === 0 ? (
          <div className="h-full flex flex-col justify-center items-center text-center space-y-6 px-4">
            <div className="p-4 bg-gray-900/60 rounded-full border border-gray-800/80 max-w-sm flex items-center justify-center text-violet-400">
              <Plane className="h-10 w-10 rotate-45 animate-bounce" />
            </div>
            <div>
              <h3 className="text-lg font-medium text-white mb-2">
                {lang === "pt" ? "Como posso ajudar na sua viagem?" : "How can I help you find flights?"}
              </h3>
              <p className="text-sm text-gray-400 max-w-sm mx-auto">
                {lang === "pt"
                  ? "Indique as cidades de origem, destino e datas desejadas. Posso comparar dias flexíveis para poupar dinheiro."
                  : "State your origin, destination, and target dates. I can analyze flexible dates to find you the best savings."}
              </p>
            </div>
            
            {/* Suggestions list */}
            <div className="w-full max-w-md pt-4 space-y-2">
              {suggestions[lang].map((suggestion, idx) => (
                <button
                  key={idx}
                  onClick={() => handleSuggestionClick(suggestion)}
                  className="w-full text-left text-xs text-gray-300 bg-gray-900/40 hover:bg-gray-800/60 border border-gray-800/50 hover:border-gray-700/80 px-4 py-3 rounded-xl transition-all duration-200 cursor-pointer block"
                >
                  {suggestion}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <>
            {messages.map((msg, index) => (
              <div
                key={index}
                className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
              >
                <div
                  className={`max-w-[85%] rounded-2xl px-4 py-3 text-sm leading-relaxed ${
                    msg.role === "user"
                      ? "bg-violet-600 text-white rounded-br-none shadow-lg shadow-violet-900/10"
                      : "bg-gray-950/60 text-gray-100 border border-gray-800 rounded-bl-none shadow-md"
                  }`}
                >
                  {/* Handle Markdown blocks simply */}
                  <div className="whitespace-pre-line prose prose-invert max-w-none text-sm">
                    {msg.content}
                  </div>
                </div>
              </div>
            ))}
            
            {/* Agent Thinking Status */}
            {isSearching && searchStatus && (
              <div className="flex justify-start">
                <div className="bg-gray-900/30 text-gray-400 border border-dashed border-gray-800 rounded-2xl rounded-bl-none px-4 py-3 text-xs flex items-center space-x-2.5 max-w-[80%]">
                  <Loader2 className="h-4 w-4 animate-spin text-violet-400" />
                  <span>{searchStatus}</span>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </>
        )}
      </div>

      {/* Input panel */}
      <form onSubmit={handleSubmit} className="p-4 bg-gray-900/60 border-t border-gray-800 flex items-center space-x-3">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={
            lang === "pt"
              ? "Ex: Voos baratos de Lisboa para Roma em Julho..."
              : "Ex: Cheap flights from Lisbon to Rome in July..."
          }
          disabled={isSearching}
          className="flex-1 bg-gray-950/80 border border-gray-800 focus:border-violet-500 rounded-xl px-4 py-3 text-sm text-white placeholder-gray-500 outline-none transition-all duration-300 disabled:opacity-55"
        />
        <button
          type="submit"
          disabled={!input.trim() || isSearching}
          className="p-3 bg-violet-600 hover:bg-violet-700 disabled:bg-violet-900/40 text-white rounded-xl shadow-lg transition-all duration-300 disabled:text-gray-500 disabled:cursor-not-allowed cursor-pointer"
        >
          <Send className="h-4 w-4" />
        </button>
      </form>
    </div>
  );
}
