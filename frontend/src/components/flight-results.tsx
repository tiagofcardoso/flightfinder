"use client";

import React, { useState } from "react";
import { Plane, Clock, ShieldCheck, Briefcase, ChevronRight, Award } from "lucide-react";

interface FlightSegment {
  airline: string;
  airline_code: string;
  flight_number: string;
  departure_time: string;
  arrival_time: string;
  stops: number;
  layovers: { airport: string; duration_minutes: number }[];
  duration_minutes: number;
  cabin: string;
  baggage_included: boolean;
}

interface FlightOffer {
  id: string;
  price: number;
  currency: string;
  passengers: number;
  outbound: FlightSegment;
  inbound: FlightSegment | null;
  total_duration_minutes: number;
  stops: number;
}

interface FlightResultsProps {
  flights: FlightOffer[];
  lang: "pt" | "en";
}

export default function FlightResults({ flights, lang }: FlightResultsProps) {
  const [filterStops, setFilterStops] = useState<number | "all">("all");
  const [sortBy, setSortBy] = useState<"price" | "duration">("price");
  const [bookedId, setBookedId] = useState<string | null>(null);

  if (!flights || flights.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-64 border border-dashed border-gray-800 rounded-2xl bg-gray-950/20 text-gray-500">
        <Plane className="h-8 w-8 mb-3 opacity-40 animate-pulse rotate-45" />
        <p className="text-sm">
          {lang === "pt"
            ? "Sem voos disponíveis. Pesquise no chat acima para carregar ofertas."
            : "No flights available. Ask the agent above to search and display deals."}
        </p>
      </div>
    );
  }

  // Formatting helper: 130 -> "2h 10m"
  const formatDuration = (minutes: number) => {
    const h = Math.floor(minutes / 60);
    const m = minutes % 60;
    return `${h}h ${m}m`;
  };

  // Filter flights
  const filteredFlights = flights.filter((flight) => {
    if (filterStops === "all") return true;
    return flight.stops === filterStops;
  });

  // Sort flights
  const sortedFlights = [...filteredFlights].sort((a, b) => {
    if (sortBy === "price") {
      return a.price - b.price;
    } else {
      return a.total_duration_minutes - b.total_duration_minutes;
    }
  });

  const handleBook = (id: string) => {
    setBookedId(id);
    setTimeout(() => {
      setBookedId(null);
      alert(
        lang === "pt"
          ? "Reserva simulada com sucesso! Conectando com a companhia aérea..."
          : "Booking successfully simulated! Connecting with the airline..."
      );
    }, 1500);
  };

  // Single Flight Segment Render
  const renderSegment = (segment: FlightSegment, title: string) => {
    return (
      <div className="flex flex-col space-y-3 p-4 bg-gray-950/40 rounded-xl border border-gray-800/60">
        <div className="flex items-center justify-between">
          <span className="text-[10px] uppercase tracking-wider font-bold text-violet-400">
            {title}
          </span>
          <span className="text-[10px] text-gray-500 font-mono">
            {segment.flight_number}
          </span>
        </div>
        
        <div className="flex items-center justify-between">
          {/* Logo & Airline */}
          <div className="flex items-center space-x-3.5">
            <div className="h-8 w-8 rounded-lg bg-gray-900 border border-gray-800 flex items-center justify-center font-bold text-xs text-white">
              {segment.airline_code}
            </div>
            <div>
              <p className="text-sm font-semibold text-white leading-tight">
                {segment.airline}
              </p>
              <p className="text-xs text-gray-400">
                {segment.cabin}
              </p>
            </div>
          </div>
          
          {/* Times */}
          <div className="flex items-center space-x-6">
            <div className="text-right">
              <p className="text-base font-bold text-white leading-tight">
                {segment.departure_time}
              </p>
              <p className="text-[10px] text-gray-500 uppercase">DEP</p>
            </div>
            <div className="flex flex-col items-center px-2">
              <span className="text-[10px] text-gray-400">
                {formatDuration(segment.duration_minutes)}
              </span>
              <div className="relative w-16 h-0.5 bg-gray-800 my-1 flex items-center justify-center">
                <Plane className="h-2.5 w-2.5 text-gray-600 absolute rotate-90" />
              </div>
              <span
                className={`text-[9px] font-bold ${
                  segment.stops === 0 ? "text-emerald-400" : "text-amber-500"
                }`}
              >
                {segment.stops === 0
                  ? lang === "pt" ? "Direto" : "Direct"
                  : lang === "pt" ? `${segment.stops} Escala` : `${segment.stops} Stop`}
              </span>
            </div>
            <div>
              <p className="text-base font-bold text-white leading-tight">
                {segment.arrival_time}
              </p>
              <p className="text-[10px] text-gray-500 uppercase">ARR</p>
            </div>
          </div>
        </div>

        {/* Layovers Info if stopovers */}
        {segment.layovers && segment.layovers.length > 0 && (
          <div className="bg-amber-950/10 border border-amber-900/20 text-amber-500/80 rounded-lg p-2 text-xs flex items-center justify-between">
            <div className="flex items-center space-x-1.5">
              <Clock className="h-3.5 w-3.5" />
              <span>
                {lang === "pt" ? "Conexão em:" : "Layover at:"}{" "}
                <strong className="text-amber-400">
                  {segment.layovers.map((l) => `${l.airport} (${formatDuration(l.duration_minutes)})`).join(", ")}
                </strong>
              </span>
            </div>
          </div>
        )}

        {/* Badges */}
        <div className="flex items-center space-x-3 text-[10px] text-gray-400 pt-1">
          <span className="flex items-center space-x-1">
            <Briefcase className="h-3 w-3 text-gray-500" />
            <span>
              {segment.baggage_included
                ? lang === "pt" ? "Bagagem Incluída" : "Bag included"
                : lang === "pt" ? "Mala de cabine apenas" : "Cabin bag only"}
            </span>
          </span>
          <span className="flex items-center space-x-1">
            <ShieldCheck className="h-3 w-3 text-emerald-500" />
            <span>{lang === "pt" ? "Remarcação Flexível" : "Flexible changes"}</span>
          </span>
        </div>
      </div>
    );
  };

  return (
    <div className="flex flex-col space-y-4">
      {/* Filtering and sorting header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-4 bg-gray-900/30 border border-gray-800 rounded-xl">
        <div className="flex items-center space-x-2 text-sm text-gray-400">
          <span>{lang === "pt" ? "Filtros:" : "Filters:"}</span>
          <div className="flex bg-gray-950 p-0.5 rounded-lg border border-gray-800">
            <button
              onClick={() => setFilterStops("all")}
              className={`px-3 py-1 text-xs rounded-md font-medium cursor-pointer ${
                filterStops === "all" ? "bg-gray-800 text-white" : "text-gray-400 hover:text-white"
              }`}
            >
              {lang === "pt" ? "Todos" : "All"}
            </button>
            <button
              onClick={() => setFilterStops(0)}
              className={`px-3 py-1 text-xs rounded-md font-medium cursor-pointer ${
                filterStops === 0 ? "bg-gray-800 text-white" : "text-gray-400 hover:text-white"
              }`}
            >
              {lang === "pt" ? "Diretos" : "Direct"}
            </button>
            <button
              onClick={() => setFilterStops(1)}
              className={`px-3 py-1 text-xs rounded-md font-medium cursor-pointer ${
                filterStops === 1 ? "bg-gray-800 text-white" : "text-gray-400 hover:text-white"
              }`}
            >
              1 {lang === "pt" ? "Escala" : "Stop"}
            </button>
          </div>
        </div>

        <div className="flex items-center space-x-2 text-sm text-gray-400">
          <span>{lang === "pt" ? "Ordenar por:" : "Sort by:"}</span>
          <div className="flex bg-gray-950 p-0.5 rounded-lg border border-gray-800">
            <button
              onClick={() => setSortBy("price")}
              className={`px-3 py-1 text-xs rounded-md font-medium cursor-pointer ${
                sortBy === "price" ? "bg-gray-800 text-white" : "text-gray-400 hover:text-white"
              }`}
            >
              {lang === "pt" ? "Preço" : "Price"}
            </button>
            <button
              onClick={() => setSortBy("duration")}
              className={`px-3 py-1 text-xs rounded-md font-medium cursor-pointer ${
                sortBy === "duration" ? "bg-gray-800 text-white" : "text-gray-400 hover:text-white"
              }`}
            >
              {lang === "pt" ? "Duração" : "Duration"}
            </button>
          </div>
        </div>
      </div>

      {/* Flight Card List */}
      <div className="space-y-4 max-h-[600px] overflow-y-auto pr-1">
        {sortedFlights.map((flight) => {
          const isCheapestOnPage = flight.id === flights[0].id;
          
          return (
            <div
              key={flight.id}
              className={`glass-panel border rounded-2xl p-5 shadow-xl transition-all duration-300 relative overflow-hidden ${
                isCheapestOnPage
                  ? "border-violet-500/40 shadow-violet-950/5 ring-1 ring-violet-500/10"
                  : "border-gray-800/80"
              }`}
            >
              {isCheapestOnPage && (
                <div className="absolute top-0 right-0 bg-violet-600 text-white text-[9px] font-bold px-3.5 py-1 rounded-bl-xl uppercase tracking-wider flex items-center space-x-1">
                  <Award className="h-3 w-3" />
                  <span>{lang === "pt" ? "Recomendado" : "Best Value"}</span>
                </div>
              )}
              
              <div className="grid grid-cols-1 lg:grid-cols-4 gap-5 items-center">
                {/* Outbound & Inbound details */}
                <div className="lg:col-span-3 flex flex-col space-y-4">
                  {renderSegment(flight.outbound, lang === "pt" ? "Voo de Ida" : "Outbound Flight")}
                  {flight.inbound &&
                    renderSegment(flight.inbound, lang === "pt" ? "Voo de Volta" : "Inbound Flight")}
                </div>

                {/* Booking & Pricing panel */}
                <div className="flex flex-row lg:flex-col lg:items-center justify-between lg:justify-center p-4 border-t lg:border-t-0 lg:border-l border-gray-800/80 gap-3">
                  <div className="text-left lg:text-center">
                    <p className="text-[10px] text-gray-500 uppercase tracking-wide">
                      {lang === "pt" ? "Total (Taxas incl.)" : "Total (taxes incl.)"}
                    </p>
                    <p className="text-2xl font-bold text-white font-mono leading-tight">
                      ${flight.price}
                    </p>
                    <p className="text-[10px] text-gray-400">
                      {lang === "pt"
                        ? `${flight.passengers} passageiro(s)`
                        : `${flight.passengers} passenger(s)`}
                    </p>
                  </div>
                  
                  <button
                    onClick={() => handleBook(flight.id)}
                    disabled={bookedId !== null}
                    className="px-6 py-3 bg-violet-600 hover:bg-violet-700 disabled:bg-violet-900/60 text-white rounded-xl text-xs font-semibold shadow-lg shadow-violet-950/20 transition-all duration-300 cursor-pointer flex items-center space-x-1.5 shrink-0"
                  >
                    {bookedId === flight.id ? (
                      <>
                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                        <span>{lang === "pt" ? "Reservando..." : "Booking..."}</span>
                      </>
                    ) : (
                      <>
                        <span>{lang === "pt" ? "Reservar Voo" : "Book Flight"}</span>
                        <ChevronRight className="h-3.5 w-3.5" />
                      </>
                    )}
                  </button>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
