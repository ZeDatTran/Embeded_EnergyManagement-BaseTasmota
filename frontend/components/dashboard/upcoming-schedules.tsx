"use client";

import { useMemo } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { useSchedules, type Schedule } from "@/hooks/use-schedules";
import { CalendarClock, Power, PowerOff, ArrowRight, Clock } from "lucide-react";
import Link from "next/link";

const DAY_MAP: Record<string, string> = {
  mon: "T2",
  tue: "T3",
  wed: "T4",
  thu: "T5",
  fri: "T6",
  sat: "T7",
  sun: "CN",
};

const DAY_ORDER = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"];

function getNextOccurrence(schedule: Schedule): Date | null {
  if (!schedule.enabled) return null;

  const now = new Date();
  const currentDay = now.getDay(); // 0=Sun, 1=Mon...
  const dayMapping: Record<string, number> = {
    sun: 0, mon: 1, tue: 2, wed: 3, thu: 4, fri: 5, sat: 6,
  };

  const [hours, minutes] = schedule.time.split(":").map(Number);
  const scheduleDays = schedule.days.map((d) => dayMapping[d.toLowerCase()]);

  if (scheduleDays.length === 0) return null;

  // Find the next occurrence
  for (let offset = 0; offset <= 7; offset++) {
    const targetDay = (currentDay + offset) % 7;
    if (scheduleDays.includes(targetDay)) {
      const candidate = new Date(now);
      candidate.setDate(now.getDate() + offset);
      candidate.setHours(hours, minutes, 0, 0);

      if (candidate > now) {
        return candidate;
      }
    }
  }

  return null;
}

function formatRelativeTime(date: Date): string {
  const now = new Date();
  const diffMs = date.getTime() - now.getTime();
  const diffMins = Math.floor(diffMs / (1000 * 60));
  const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

  if (diffMins < 60) return `${diffMins} phút nữa`;
  if (diffHours < 24) return `${diffHours} giờ nữa`;
  if (diffDays === 1) return "Ngày mai";
  return `${diffDays} ngày nữa`;
}

function formatTime(time: string): string {
  return time; // Already in HH:mm format
}

export function UpcomingSchedules() {
  const { data: schedules, isLoading, isError } = useSchedules();

  const upcomingSchedules = useMemo(() => {
    if (!schedules) return [];

    const withNextOccurrence = schedules
      .filter((s) => s.enabled)
      .map((s) => ({
        ...s,
        nextOccurrence: getNextOccurrence(s),
      }))
      .filter((s) => s.nextOccurrence !== null)
      .sort((a, b) => a.nextOccurrence!.getTime() - b.nextOccurrence!.getTime())
      .slice(0, 5);

    return withNextOccurrence;
  }, [schedules]);

  if (isLoading) {
    return (
      <Card className="overflow-hidden">
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-base">
            <CalendarClock className="h-5 w-5 text-primary" />
            Lịch trình sắp tới
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            {[1, 2, 3].map((i) => (
              <div key={i} className="flex items-center gap-3 animate-pulse">
                <div className="h-10 w-10 rounded-lg bg-muted" />
                <div className="flex-1 space-y-2">
                  <div className="h-4 w-3/4 rounded bg-muted" />
                  <div className="h-3 w-1/2 rounded bg-muted" />
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    );
  }

  if (isError) {
    return (
      <Card className="overflow-hidden">
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-base">
            <CalendarClock className="h-5 w-5 text-primary" />
            Lịch trình sắp tới
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground text-center py-4">
            Không thể tải lịch trình
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="overflow-hidden h-full">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2 text-base">
            <CalendarClock className="h-5 w-5 text-primary" />
            Lịch trình sắp tới
          </CardTitle>
          <Link
            href="/schedules"
            className="flex items-center gap-1 text-xs text-primary hover:text-primary/80 transition-colors font-medium"
          >
            Xem tất cả
            <ArrowRight className="h-3 w-3" />
          </Link>
        </div>
      </CardHeader>
      <CardContent>
        {upcomingSchedules.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-8 text-center">
            <CalendarClock className="h-10 w-10 text-muted-foreground/40 mb-3" />
            <p className="text-sm text-muted-foreground">
              Không có lịch trình nào sắp tới
            </p>
            <Link
              href="/schedules"
              className="mt-2 text-xs text-primary hover:underline"
            >
              Tạo lịch trình mới
            </Link>
          </div>
        ) : (
          <div className="space-y-3">
            {upcomingSchedules.map((schedule) => (
              <div
                key={schedule.id}
                className="group flex items-center gap-3 p-3 rounded-xl bg-muted/30 hover:bg-muted/50 transition-all duration-200 border border-transparent hover:border-border/50"
              >
                {/* Action Icon */}
                <div
                  className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-lg transition-colors ${
                    schedule.action === "on"
                      ? "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400"
                      : "bg-orange-500/15 text-orange-600 dark:text-orange-400"
                  }`}
                >
                  {schedule.action === "on" ? (
                    <Power className="h-4 w-4" />
                  ) : (
                    <PowerOff className="h-4 w-4" />
                  )}
                </div>

                {/* Schedule Info */}
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium truncate">
                    {schedule.name}
                  </p>
                  <div className="flex items-center gap-2 mt-0.5">
                    <div className="flex items-center gap-1 text-xs text-muted-foreground">
                      <Clock className="h-3 w-3" />
                      {formatTime(schedule.time)}
                    </div>
                    <span className="text-muted-foreground/40">·</span>
                    <div className="flex gap-0.5">
                      {schedule.days
                        .sort((a, b) => DAY_ORDER.indexOf(a) - DAY_ORDER.indexOf(b))
                        .map((day) => (
                          <span
                            key={day}
                            className="text-[10px] px-1 py-0.5 rounded bg-primary/10 text-primary font-medium"
                          >
                            {DAY_MAP[day] || day}
                          </span>
                        ))}
                    </div>
                  </div>
                </div>

                {/* Relative Time */}
                <Badge
                  variant="secondary"
                  className="shrink-0 text-[10px] font-normal"
                >
                  {schedule.nextOccurrence
                    ? formatRelativeTime(schedule.nextOccurrence)
                    : ""}
                </Badge>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
