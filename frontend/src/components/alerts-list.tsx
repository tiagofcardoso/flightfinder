"use client";

import React, { useState } from "react";
import { Bell, Trash2, Plus, Calendar, DollarSign, Loader2, AlertCircle, Sparkles } from "lucide-react";

interface AlertItem {
  id: number;
  origin: str;
  destination: str;
  departure_date: str;
  return_date: str | null;
  target_price: number;
  last_price: number | null;
  created_at: string;
  last_checked: string | null;
}

interface AlertsListProps {
  alerts: AlertItem[];
  onRefreshAlerts: () => void;
  lang: "pt" | "en";
}

export default function AlertsList({ alerts, onRefreshAlerts, lang }: AlertsListProps) {
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  
  // Form State
  const [origin, setOrigin] = useState("");
  const [destination, setDestination] = useState("");
  const [depDate, setDepDate] = useState("");
  const [retDate, setRetDate] = useState("");
  const [targetPrice, setTargetPrice] = useState("");
  const [errorMsg, setErrorMsg] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMsg("");
    
    if (!origin || !destination || !depDate || !targetPrice) {
      setErrorMsg(
        lang === "pt"
          ? "Preencha todos os campos obrigatórios (*)."
          : "Please fill in all required fields (*)."
      );
      return;
    }
    
    setIsSubmitting(true);
    try {
      const res = await fetch("http://localhost:8000/api/alerts", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          origin: origin.toUpperCase().trim(),
          destination: destination.toUpperCase().trim(),
          departure_date: depDate,
          return_date: retDate || null,
          target_price: parseFloat(targetPrice),
        }),
      });
      
      if (res.ok) {
        setOrigin("");
        setDestination("");
        setDepDate("");
        setRetDate("");
        setTargetPrice("");
        onRefreshAlerts();
      } else {
        const errorData = await res.json();
        setErrorMsg(errorData.detail || "Error creating alert");
      }
    } catch (err) {
      console.error(err);
      setErrorMsg(lang === "pt" ? "Erro ao ligar ao backend." : "Error connecting to server.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleDelete = async (id: number) => {
    setDeletingId(id);
    try {
      const res = await fetch(`http://localhost:8000/api/alerts/${id}`, {
        method: "DELETE",
      });
      if (res.ok) {
        onRefreshAlerts();
      }
    } catch (err) {
      console.error(err);
    } finally {
      setDeletingId(null);
    }
  };

  // Helper to format dates simply: "2026-10-15" -> "15 Out"
  const formatDateSimple = (dateStr: string) => {
    try {
      const date = new Date(dateStr + "T00:00:00");
      const locale = lang === "pt" ? "pt-PT" : "en-US";
      const day = date.getDate();
      const month = date.toLocaleDateString(locale, { month: "short" }).replace(".", "");
      return `${day} ${month.toUpperCase()}`;
    } catch {
      return dateStr;
    }
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
      {/* Left side: Alert registration form */}
      <div className="lg:col-span-4 bg-gray-900/40 border border-gray-800 rounded-2xl p-5 shadow-xl">
        <div className="flex items-center space-x-2.5 pb-3 border-b border-gray-800 mb-4">
          <div className="p-2 bg-violet-600/10 text-violet-400 rounded-lg">
            <Plus className="h-4.5 w-4.5" />
          </div>
          <h3 className="font-semibold text-white">
            {lang === "pt" ? "Criar Alerta de Preço" : "Create Price Tracker"}
          </h3>
        </div>
        
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-xs font-semibold text-gray-400 mb-1.5 uppercase">
              {lang === "pt" ? "Origem (IATA) *" : "Origin (IATA) *"}
            </label>
            <input
              type="text"
              maxLength={3}
              value={origin}
              onChange={(e) => setOrigin(e.target.value)}
              placeholder="Ex: LIS"
              className="w-full bg-gray-950/80 border border-gray-800 focus:border-violet-500 rounded-xl px-3 py-2 text-sm text-white placeholder-gray-600 outline-none uppercase font-bold"
            />
          </div>
          
          <div>
            <label className="block text-xs font-semibold text-gray-400 mb-1.5 uppercase">
              {lang === "pt" ? "Destino (IATA) *" : "Destination (IATA) *"}
            </label>
            <input
              type="text"
              maxLength={3}
              value={destination}
              onChange={(e) => setDestination(e.target.value)}
              placeholder="Ex: GRU"
              className="w-full bg-gray-950/80 border border-gray-800 focus:border-violet-500 rounded-xl px-3 py-2 text-sm text-white placeholder-gray-600 outline-none uppercase font-bold"
            />
          </div>
          
          <div>
            <label className="block text-xs font-semibold text-gray-400 mb-1.5 uppercase">
              {lang === "pt" ? "Data de Ida *" : "Departure Date *"}
            </label>
            <input
              type="date"
              value={depDate}
              onChange={(e) => setDepDate(e.target.value)}
              className="w-full bg-gray-950/80 border border-gray-800 focus:border-violet-500 rounded-xl px-3 py-2 text-sm text-white outline-none"
            />
          </div>
          
          <div>
            <label className="block text-xs font-semibold text-gray-400 mb-1.5 uppercase">
              {lang === "pt" ? "Data de Volta (Opcional)" : "Return Date (Optional)"}
            </label>
            <input
              type="date"
              value={retDate}
              onChange={(e) => setRetDate(e.target.value)}
              className="w-full bg-gray-950/80 border border-gray-800 focus:border-violet-500 rounded-xl px-3 py-2 text-sm text-white outline-none"
            />
          </div>
          
          <div>
            <label className="block text-xs font-semibold text-gray-400 mb-1.5 uppercase">
              {lang === "pt" ? "Preço Alvo (USD) *" : "Target Price (USD) *"}
            </label>
            <div className="relative">
              <DollarSign className="absolute left-3 top-2.5 h-4 w-4 text-gray-500" />
              <input
                type="number"
                value={targetPrice}
                onChange={(e) => setTargetPrice(e.target.value)}
                placeholder="Ex: 500"
                className="w-full bg-gray-950/80 border border-gray-800 focus:border-violet-500 rounded-xl pl-9 pr-3 py-2 text-sm text-white placeholder-gray-600 outline-none font-bold"
              />
            </div>
          </div>
          
          {errorMsg && (
            <div className="p-2.5 bg-red-950/20 text-red-400 border border-red-900/40 rounded-xl text-xs flex items-center space-x-2">
              <AlertCircle className="h-4 w-4 shrink-0" />
              <span>{errorMsg}</span>
            </div>
          )}
          
          <button
            type="submit"
            disabled={isSubmitting}
            className="w-full py-2.5 bg-violet-600 hover:bg-violet-700 disabled:bg-violet-900/40 text-white rounded-xl text-xs font-semibold shadow-lg shadow-violet-950/20 transition-all duration-300 cursor-pointer flex items-center justify-center space-x-1.5"
          >
            {isSubmitting ? (
              <>
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                <span>{lang === "pt" ? "Criando Alerta..." : "Creating..."}</span>
              </>
            ) : (
              <>
                <Bell className="h-3.5 w-3.5" />
                <span>{lang === "pt" ? "Ativar Alerta 24/7" : "Activate 24/7 Tracker"}</span>
              </>
            )}
          </button>
        </form>
      </div>

      {/* Right side: List of active alerts */}
      <div className="lg:col-span-8 space-y-4">
        {alerts.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-80 border border-dashed border-gray-800 rounded-2xl bg-gray-950/20 text-gray-500 p-6 text-center">
            <Bell className="h-10 w-10 mb-3.5 opacity-30 animate-pulse text-violet-400" />
            <h4 className="text-sm font-medium text-white mb-1.5">
              {lang === "pt" ? "Sem Alertas Configurados" : "No Active Alerts"}
            </h4>
            <p className="text-xs text-gray-400 max-w-sm">
              {lang === "pt"
                ? "Ative alertas usando o formulário ao lado ou peça ao Agente no Chat: 'Alerta-me se o voo de LIS para JFK baixar de 400 dólares'."
                : "Register alert rules using the left form or command the agent via chat: 'Notify me when flights from GRU to LHR drop below $700'."}
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 max-h-[600px] overflow-y-auto pr-1">
            {alerts.map((alert) => {
              const isTargetMet = alert.last_price !== null && alert.last_price <= alert.target_price;
              
              return (
                <div
                  key={alert.id}
                  className={`glass-panel border rounded-2xl p-5 shadow-xl transition-all duration-300 relative overflow-hidden flex flex-col justify-between ${
                    isTargetMet
                      ? "border-emerald-500/40 bg-emerald-950/5 ring-1 ring-emerald-500/10 shadow-emerald-950/5"
                      : "border-gray-800/80"
                  }`}
                >
                  {isTargetMet && (
                    <div className="absolute top-0 right-0 bg-emerald-600 text-white text-[9px] font-bold px-3 py-1 rounded-bl-xl uppercase tracking-wider flex items-center space-x-1">
                      <Sparkles className="h-3 w-3 animate-pulse" />
                      <span>{lang === "pt" ? "Meta Atingida" : "Budget Met"}</span>
                    </div>
                  )}
                  
                  <div>
                    {/* Route */}
                    <div className="flex items-center space-x-3 mb-3">
                      <span className="text-lg font-extrabold text-white tracking-wider">
                        {alert.origin}
                      </span>
                      <span className="text-gray-600 font-bold">➡️</span>
                      <span className="text-lg font-extrabold text-white tracking-wider">
                        {alert.destination}
                      </span>
                    </div>
                    
                    {/* Dates */}
                    <div className="flex items-center space-x-1.5 text-xs text-gray-400 mb-4 bg-gray-950/40 p-2 rounded-xl border border-gray-800/40">
                      <Calendar className="h-3.5 w-3.5 text-gray-500" />
                      <span>
                        {formatDateSimple(alert.departure_date)}
                        {alert.return_date ? ` - ${formatDateSimple(alert.return_date)}` : " (Ida)"}
                      </span>
                    </div>
                    
                    {/* Pricing info */}
                    <div className="grid grid-cols-2 gap-4 border-t border-gray-800/50 pt-3.5 mb-3">
                      <div>
                        <p className="text-[10px] text-gray-500 uppercase tracking-wider">
                          {lang === "pt" ? "Preço Alvo" : "Target Price"}
                        </p>
                        <p className="text-lg font-bold text-violet-400 font-mono">
                          ${alert.target_price}
                        </p>
                      </div>
                      <div>
                        <p className="text-[10px] text-gray-500 uppercase tracking-wider">
                          {lang === "pt" ? "Preço Atual" : "Latest Price"}
                        </p>
                        <p
                          className={`text-lg font-bold font-mono ${
                            alert.last_price
                              ? isTargetMet
                                ? "text-emerald-400"
                                : "text-white"
                              : "text-gray-600 text-sm font-sans font-medium"
                          }`}
                        >
                          {alert.last_price ? `$${alert.last_price}` : (lang === "pt" ? "Consultando..." : "Pending...")}
                        </p>
                      </div>
                    </div>
                  </div>
                  
                  {/* Footer status / Action */}
                  <div className="flex items-center justify-between border-t border-gray-800/40 pt-3 mt-2">
                    <span className="text-[9px] text-gray-500">
                      {alert.last_checked
                        ? `${lang === "pt" ? "Verificado:" : "Checked:"} ${alert.last_checked.split("T")[-1]?.slice(0, 5) || alert.last_checked.slice(11, 16)}`
                        : (lang === "pt" ? "Pendente" : "Pending")}
                    </span>
                    
                    <button
                      onClick={() => handleDelete(alert.id)}
                      disabled={deletingId === alert.id}
                      className="p-2 text-gray-500 hover:text-red-400 bg-gray-950/40 border border-gray-800/60 hover:border-red-900/40 rounded-xl transition-all duration-300 cursor-pointer disabled:opacity-50"
                    >
                      {deletingId === alert.id ? (
                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      ) : (
                        <Trash2 className="h-3.5 w-3.5" />
                      )}
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
