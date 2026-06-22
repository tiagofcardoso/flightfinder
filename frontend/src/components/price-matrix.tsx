"use client";

import React from "react";
import { Calendar, TrendingDown, DollarSign } from "lucide-react";

interface MatrixCell {
  departure_date: string;
  return_date: string | null;
  price: number;
  is_cheapest: boolean;
}

interface PriceMatrixProps {
  matrixData: {
    departure_dates: string[];
    return_dates: string[];
    matrix: MatrixCell[];
  } | null;
  onSelectCell: (dep: string, ret: string | null) => void;
  selectedDepDate: string;
  selectedRetDate: string | null;
  lang: "pt" | "en";
}

export default function PriceMatrix({
  matrixData,
  onSelectCell,
  selectedDepDate,
  selectedRetDate,
  lang,
}: PriceMatrixProps) {
  if (!matrixData || !matrixData.matrix || matrixData.matrix.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-64 border border-dashed border-gray-800 rounded-2xl bg-gray-950/20 text-gray-500">
        <Calendar className="h-8 w-8 mb-3 opacity-40 animate-pulse" />
        <p className="text-sm">
          {lang === "pt"
            ? "Aguardando resultados de datas flexíveis do agente..."
            : "Waiting for flexible dates data from agent..."}
        </p>
      </div>
    );
  }

  const { departure_dates, return_dates, matrix } = matrixData;
  const isRoundTrip = return_dates && return_dates.length > 0;

  // Format date helper: "2026-10-15" -> "Qui, 15 Out" or "Thu, Oct 15"
  const formatDateLabel = (dateStr: string) => {
    try {
      const date = new Date(dateStr + "T00:00:00");
      const locale = lang === "pt" ? "pt-PT" : "en-US";
      
      const weekday = date.toLocaleDateString(locale, { weekday: "short" });
      const day = date.getDate();
      const month = date.toLocaleDateString(locale, { month: "short" });
      
      // Clean string
      const formattedWeekday = weekday.replace(".", "").toUpperCase();
      const formattedMonth = month.replace(".", "");
      
      if (lang === "pt") {
        return `${formattedWeekday}, ${day} ${formattedMonth}`;
      } else {
        return `${formattedWeekday}, ${formattedMonth} ${day}`;
      }
    } catch {
      return dateStr;
    }
  };

  // Find price cell in matrix list
  const getCell = (dep: string, ret: string | null) => {
    return matrix.find(
      (cell) =>
        cell.departure_date === dep &&
        (ret ? cell.return_date === ret : cell.return_date === null)
    );
  };

  // Find cheapest price in the matrix to display in insights header
  const cheapestCell = matrix.find((c) => c.is_cheapest);

  return (
    <div className="bg-gray-900/40 border border-gray-800 rounded-2xl p-6 shadow-xl flex flex-col space-y-4">
      {/* Header Info */}
      <div className="flex flex-col md:flex-row md:items-center justify-between pb-3 border-b border-gray-800 gap-3">
        <div className="flex items-center space-x-3">
          <div className="p-2 bg-emerald-500/10 text-emerald-400 rounded-lg">
            <TrendingDown className="h-5 w-5" />
          </div>
          <div>
            <h3 className="font-semibold text-white">
              {lang === "pt" ? "Matriz Calendário de Preços" : "Price Calendar Grid"}
            </h3>
            <p className="text-xs text-gray-400">
              {lang === "pt"
                ? "Compare as datas de ida e volta para encontrar o melhor preço"
                : "Compare departure & return dates to catch the absolute best deal"}
            </p>
          </div>
        </div>
        
        {cheapestCell && (
          <div className="bg-emerald-950/30 text-emerald-400 border border-emerald-900/50 px-3 py-1.5 rounded-xl text-xs flex items-center space-x-1.5">
            <DollarSign className="h-3.5 w-3.5" />
            <span>
              {lang === "pt"
                ? `Melhor preço: $${cheapestCell.price} (Ida: ${formatDateLabel(cheapestCell.departure_date)})`
                : `Best price: $${cheapestCell.price} (Out: ${formatDateLabel(cheapestCell.departure_date)})`}
            </span>
          </div>
        )}
      </div>

      {isRoundTrip ? (
        /* Round Trip Grid */
        <div className="overflow-x-auto">
          <table className="w-full border-collapse">
            <thead>
              <tr>
                {/* Empty corner cell */}
                <th className="p-2 text-center text-xs font-semibold text-gray-500 border border-gray-800/40 bg-gray-950/20">
                  {lang === "pt" ? "IDA \\ VOLTA" : "OUT \\ IN"}
                </th>
                {return_dates.map((retDate) => (
                  <th
                    key={retDate}
                    className="p-3 text-center text-xs font-medium text-gray-300 border border-gray-800/40 bg-gray-950/40 min-w-[100px]"
                  >
                    {formatDateLabel(retDate)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {departure_dates.map((depDate) => (
                <tr key={depDate}>
                  <td className="p-3 text-left text-xs font-medium text-gray-300 border border-gray-800/40 bg-gray-950/40 font-semibold whitespace-nowrap">
                    {formatDateLabel(depDate)}
                  </td>
                  {return_dates.map((retDate) => {
                    const cell = getCell(depDate, retDate);
                    if (!cell) {
                      return (
                        <td
                          key={`${depDate}-${retDate}`}
                          className="p-3 text-center text-xs text-gray-700 bg-gray-950/10 border border-gray-800/40 font-mono"
                        >
                          -
                        </td>
                      );
                    }

                    const isCurrentSelection =
                      cell.departure_date === selectedDepDate &&
                      cell.return_date === selectedRetDate;

                    return (
                      <td
                        key={`${depDate}-${retDate}`}
                        onClick={() => onSelectCell(cell.departure_date, cell.return_date)}
                        className={`p-3 text-center text-sm font-semibold border border-gray-800/60 font-mono cursor-pointer transition-all duration-300 rounded-md ${
                          cell.is_cheapest
                            ? "bg-emerald-500/15 text-emerald-400 border-emerald-500/30 hover:bg-emerald-500/25"
                            : "bg-gray-950/30 text-gray-300 hover:bg-gray-800/50"
                        } ${
                          isCurrentSelection
                            ? "ring-2 ring-violet-500 ring-offset-2 ring-offset-gray-900 scale-102"
                            : ""
                        }`}
                      >
                        ${cell.price}
                        {cell.is_cheapest && (
                          <span className="block text-[8px] tracking-wider text-emerald-400 uppercase font-sans mt-0.5 font-bold">
                            {lang === "pt" ? "Barato" : "Cheapest"}
                          </span>
                        )}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        /* One Way List */
        <div className="grid grid-cols-2 sm:grid-cols-4 md:grid-cols-7 gap-3">
          {departure_dates.map((depDate) => {
            const cell = getCell(depDate, null);
            if (!cell) return null;

            const isCurrentSelection =
              cell.departure_date === selectedDepDate &&
              selectedRetDate === null;

            return (
              <div
                key={depDate}
                onClick={() => onSelectCell(depDate, null)}
                className={`p-3 border rounded-xl flex flex-col justify-center items-center text-center cursor-pointer transition-all duration-300 ${
                  cell.is_cheapest
                    ? "bg-emerald-500/15 text-emerald-400 border-emerald-500/30 hover:bg-emerald-500/25"
                    : "bg-gray-950/30 text-gray-300 border-gray-800 hover:bg-gray-800/50"
                } ${
                  isCurrentSelection
                    ? "ring-2 ring-violet-500 ring-offset-2 ring-offset-gray-900"
                    : ""
                }`}
              >
                <span className="text-[10px] text-gray-400 block mb-1">
                  {formatDateLabel(depDate)}
                </span>
                <span className="text-base font-bold font-mono">
                  ${cell.price}
                </span>
                {cell.is_cheapest && (
                  <span className="text-[9px] text-emerald-400 uppercase tracking-wider font-bold mt-1">
                    {lang === "pt" ? "Cheapest" : "Cheapest"}
                  </span>
                )}
              </div>
            );
          })}
        </div>
      )}
      
      <div className="text-[10px] text-gray-500 text-right flex items-center justify-end space-x-3 pt-2">
        <span className="flex items-center space-x-1">
          <span className="inline-block w-2.5 h-2.5 bg-emerald-500/15 border border-emerald-500/30 rounded"></span>
          <span>{lang === "pt" ? "Melhor Oferta" : "Best Price"}</span>
        </span>
        <span className="flex items-center space-x-1">
          <span className="inline-block w-2.5 h-2.5 border border-violet-500 rounded"></span>
          <span>{lang === "pt" ? "Seleção Ativa" : "Active Selection"}</span>
        </span>
      </div>
    </div>
  );
}
