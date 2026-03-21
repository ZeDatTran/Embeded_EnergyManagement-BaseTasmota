import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:5000"

export interface Schedule {
  id: string
  name: string
  targetId: string
  action: "on" | "off"
  time: string
  days: string[]
  enabled: boolean
  runOnce?: boolean
  createdAt: string
}

export function useSchedules() {
  return useQuery({
    queryKey: ["schedules"],
    queryFn: async () => {
      const response = await fetch(`${API_BASE_URL}/schedules`)
      if (!response.ok) {
        throw new Error("Failed to fetch schedules")
      }
      return response.json() as Promise<Schedule[]>
    },
  })
}

export function useCreateSchedule() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (data: Omit<Schedule, "id" | "createdAt">) => {
      const response = await fetch(`${API_BASE_URL}/schedules`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(data),
      })
      if (!response.ok) {
        const error = await response.json()
        throw new Error(error.message || "Failed to create schedule")
      }
      return response.json() as Promise<Schedule>
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["schedules"] })
    },
  })
}

export function useUpdateSchedule() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (data: Schedule) => {
      const response = await fetch(`${API_BASE_URL}/schedules/${data.id}`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(data),
      })
      if (!response.ok) {
        const error = await response.json()
        throw new Error(error.message || "Failed to update schedule")
      }
      return response.json() as Promise<Schedule>
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["schedules"] })
    },
  })
}

export function useDeleteSchedule() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (id: string) => {
      const response = await fetch(`${API_BASE_URL}/schedules/${id}`, {
        method: "DELETE",
      })
      if (!response.ok) {
        const error = await response.json()
        throw new Error(error.message || "Failed to delete schedule")
      }
      return id
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["schedules"] })
    },
  })
}

export function useToggleSchedule() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (id: string) => {
      const response = await fetch(`${API_BASE_URL}/schedules/${id}/toggle`, {
        method: "POST",
      })
      if (!response.ok) {
        const error = await response.json()
        throw new Error(error.message || "Failed to toggle schedule")
      }
      return response.json() as Promise<Schedule>
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["schedules"] })
    },
  })
}
