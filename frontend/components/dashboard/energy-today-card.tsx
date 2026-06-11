"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { fetchEnergySummary, type EnergySummaryData } from "@/lib/api";
import { Zap, Banknote, TrendingUp } from "lucide-react";

function formatCurrency(value: number): string {
  return new Intl.NumberFormat("vi-VN", {
    style: "currency",
    currency: "VND",
    maximumFractionDigits: 0,
  }).format(value);
}

// Simplified Vietnam electricity cost estimate (tier 1 rate)
function estimateCost(kwh: number): number {
  if (kwh <= 0) return 0;
  // Use average residential rate ~2,000 VND/kWh as a rough estimate for small daily values
  return kwh * 2000;
}

interface EnergyTodayCardProps {
  realtimeEnergyToday?: number;
}

export function EnergyTodayCard({ realtimeEnergyToday }: EnergyTodayCardProps) {
  const [summary, setSummary] = useState<EnergySummaryData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const loadSummary = async () => {
      try {
        const data = await fetchEnergySummary("day");
        setSummary(data);
      } catch (error) {
        console.error("Error loading energy summary:", error);
      } finally {
        setLoading(false);
      }
    };
    loadSummary();

    // Auto refresh every 5 minutes
    const interval = setInterval(loadSummary, 5 * 60 * 1000);
    return () => clearInterval(interval);
  }, []);

  if (loading) {
    return (
      <Card className="overflow-hidden h-full">
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-base">
            <Zap className="h-5 w-5 text-amber-500" />
            Năng lượng hôm nay
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-4 animate-pulse">
            <div className="h-16 rounded-xl bg-muted" />
            <div className="h-16 rounded-xl bg-muted" />
          </div>
        </CardContent>
      </Card>
    );
  }

  // Use API data first; if API returns 0 but realtime device data is available, use that
  const apiConsumption = summary?.totalConsumption ?? 0;
  const apiCost = summary?.totalCost ?? 0;

  // Realtime data from devices is often more accurate for "today" because it tracks exact device state
  const consumption = Math.max(apiConsumption, realtimeEnergyToday ?? 0);
  const cost = consumption === apiConsumption && apiCost > 0 ? apiCost : estimateCost(consumption);

  return (
    <Card className="overflow-hidden h-full">
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <Zap className="h-5 w-5 text-amber-500" />
          Năng lượng hôm nay
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {/* Consumption */}
        <div className="relative overflow-hidden rounded-xl bg-gradient-to-br from-blue-500/10 via-cyan-500/5 to-transparent p-4 border border-blue-500/10">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-xs font-medium text-muted-foreground mb-1">
                Tiêu thụ
              </p>
              <p className="text-2xl font-bold tracking-tight">
                {consumption.toFixed(2)}
                <span className="text-sm font-normal text-muted-foreground ml-1">
                  kWh
                </span>
              </p>
            </div>
            <div className="flex h-10 w-10 items-center justify-center rounded-full bg-blue-500/15">
              <TrendingUp className="h-5 w-5 text-blue-500" />
            </div>
          </div>
        </div>

        {/* Cost */}
        <div className="relative overflow-hidden rounded-xl bg-gradient-to-br from-emerald-500/10 via-green-500/5 to-transparent p-4 border border-emerald-500/10">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-xs font-medium text-muted-foreground mb-1">
                Chi phí ước tính
              </p>
              <p className="text-2xl font-bold tracking-tight">
                {formatCurrency(cost)}
              </p>
            </div>
            <div className="flex h-10 w-10 items-center justify-center rounded-full bg-emerald-500/15">
              <Banknote className="h-5 w-5 text-emerald-500" />
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
