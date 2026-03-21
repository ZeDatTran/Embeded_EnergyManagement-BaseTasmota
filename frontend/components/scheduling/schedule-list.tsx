"use client"

import { useSchedules, useDeleteSchedule, useToggleSchedule } from "@/hooks/use-schedules"
import { useUIStore } from "@/lib/store"
import { Trash2, Edit2 } from "lucide-react"

export function ScheduleList() {
  const { data: schedules, isLoading, error } = useSchedules()
  const { mutate: deleteSchedule } = useDeleteSchedule()
  const { mutate: toggleSchedule } = useToggleSchedule()
  const { setScheduleEditorOpen } = useUIStore()

  const handleEdit = (schedule: any) => {
    setScheduleEditorOpen(true, schedule.id)
  }

  const handleDelete = (id: string) => {
    if (confirm("Are you sure you want to delete this schedule?")) {
      deleteSchedule(id)
    }
  }

  const handleToggleEnabled = (scheduleId: string) => {
    toggleSchedule(scheduleId)
  }

  return (
    <div className="overflow-hidden rounded-lg border border-border bg-card text-card-foreground">
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead className="border-b border-border bg-muted/50">
            <tr>
              <th className="px-6 py-3 text-left text-sm font-semibold text-foreground">Name</th>
              <th className="px-6 py-3 text-left text-sm font-semibold text-foreground">Target</th>
              <th className="px-6 py-3 text-left text-sm font-semibold text-foreground">Type</th>
              <th className="px-6 py-3 text-left text-sm font-semibold text-foreground">Action</th>
              <th className="px-6 py-3 text-left text-sm font-semibold text-foreground">Time</th>
              <th className="px-6 py-3 text-left text-sm font-semibold text-foreground">Days</th>
              <th className="px-6 py-3 text-left text-sm font-semibold text-foreground">Enabled</th>
              <th className="px-6 py-3 text-left text-sm font-semibold text-foreground">Actions</th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              <tr>
                <td colSpan={8} className="px-6 py-8 text-center text-muted-foreground">
                  Loading schedules...
                </td>
              </tr>
            ) : error ? (
              <tr>
                <td colSpan={8} className="px-6 py-8 text-center text-red-500">
                  Error loading schedules. Please check if the server is running.
                </td>
              </tr>
            ) : !schedules || schedules.length === 0 ? (
              <tr>
                <td colSpan={8} className="px-6 py-8 text-center text-muted-foreground">
                  No schedules created yet
                </td>
              </tr>
            ) : (
              schedules.map((schedule) => (
                <tr key={schedule.id} className="border-b border-border transition-colors hover:bg-muted/40">
                  <td className="px-6 py-4 text-sm font-medium text-foreground">{schedule.name}</td>
                  <td className="px-6 py-4 text-sm text-muted-foreground">{schedule.targetId}</td>
                  <td className="px-6 py-4 text-sm">
                    <span className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium ${
                      schedule.runOnce
                        ? "bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-100"
                        : "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-100"
                    }`}>
                      {schedule.runOnce ? "One-time" : "Recurring"}
                    </span>
                  </td>
                  <td className="px-6 py-4 text-sm">
                    <span
                      className={`inline-flex px-2.5 py-0.5 rounded-full text-xs font-medium ${
                        schedule.action === "on" ? "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200" : "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200"
                      }`}
                    >
                      Turn {schedule.action.toUpperCase()}
                    </span>
                  </td>
                  <td className="px-6 py-4 text-sm text-foreground">{schedule.time}</td>
                  <td className="px-6 py-4 text-sm text-muted-foreground">{schedule.days.join(", ")}</td>
                  <td className="px-6 py-4 text-sm">
                    <input
                      type="checkbox"
                      checked={schedule.enabled}
                      onChange={() => handleToggleEnabled(schedule.id)}
                      className="h-4 w-4 rounded border-border"
                    />
                  </td>
                  <td className="px-6 py-4 text-sm flex gap-2">
                    <button
                      onClick={() => handleEdit(schedule)}
                      className="rounded p-1.5 text-blue-600 transition-colors hover:bg-blue-50 dark:hover:bg-blue-900"
                    >
                      <Edit2 size={16} />
                    </button>
                    <button
                      onClick={() => handleDelete(schedule.id)}
                      className="rounded p-1.5 text-red-600 transition-colors hover:bg-red-50 dark:hover:bg-red-900"
                    >
                      <Trash2 size={16} />
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
