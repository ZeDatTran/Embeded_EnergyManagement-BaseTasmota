import { io, type Socket } from "socket.io-client"
import type { QueryClient } from "@tanstack/react-query"

let socket: Socket | null = null

export function initSocket(queryClient: QueryClient): Socket {
  // Return existing socket if already initialized
  if (socket?.connected) return socket

  // Disconnect old socket if exists but not connected
  if (socket) {
    socket.disconnect()
  }

  const token = typeof window !== 'undefined' ? localStorage.getItem("smart_home_token") : null

  socket = io(process.env.NEXT_PUBLIC_SOCKET_URL || "http://localhost:5000", {
    reconnection: true,
    reconnectionDelay: 1000,
    reconnectionDelayMax: 5000,
    reconnectionAttempts: Infinity,
    transports: ['websocket', 'polling'],
    auth: {
      token: token
    }
  })

  // On connect: join dashboard room & subscribe to device updates
  socket.on('connect', () => {
    console.log('[Socket] Connected, joining dashboard room...')
    socket?.emit('join_dashboard')
    socket?.emit('join_logs')
    socket?.emit('join_schedules')
    socket?.emit('subscribe_devices')
  })

  // ── dashboard_update: CoreIoT → backend WS → Flask SocketIO → frontend ──
  // Payload A (single device push from CoreIoT WS):
  //   { device_id, data: { telemetry, attributes, metadata }, timestamp }
  // Payload B (initial snapshot on join_dashboard):
  //   { data: [ { id, type, name, location, attributes, telemetry }, ... ] }
  socket.on("dashboard_update", (payload: any) => {
    // Handle initial snapshot (array of devices)
    if (payload?.data && Array.isArray(payload.data)) {
      console.log('[Socket] dashboard_update snapshot:', payload.data.length, 'devices')
      queryClient.setQueryData(["devices"], (oldData: any) => {
        if (!oldData) return payload.data
        // Merge: replace matching devices, keep others
        const updatedMap = new Map(payload.data.map((d: any) => [d.id, d]))
        const merged = oldData.map((d: any) => updatedMap.get(d.id) ?? d)
        // Add new devices not in oldData
        payload.data.forEach((d: any) => {
          if (!oldData.find((o: any) => o.id === d.id)) merged.push(d)
        })
        return merged
      })
      return
    }

    // Handle single device real-time push
    const deviceId = payload?.device_id
    const deviceData = payload?.data
    if (!deviceId || !deviceData) return

    console.log('[Socket] dashboard_update for device:', deviceId)

    // Update ["devices"] list cache
    queryClient.setQueryData(["devices"], (oldData: any) => {
      if (!oldData) return oldData
      return oldData.map((device: any) =>
        device.id === deviceId
          ? {
              ...device,
              telemetry: { ...device.telemetry, ...deviceData.telemetry },
              attributes: { ...device.attributes, ...deviceData.attributes },
            }
          : device
      )
    })

    // Update individual device cache ["device", deviceId]
    queryClient.setQueryData(["device", deviceId], (oldData: any) => {
      if (!oldData) return oldData
      return {
        ...oldData,
        telemetry: { ...oldData.telemetry, ...deviceData.telemetry },
        attributes: { ...oldData.attributes, ...deviceData.attributes },
      }
    })
  })

  // Listen for schedule updates
  socket.on("schedule_updated", () => {
    console.log('[Socket] Schedule updated')
    queryClient.invalidateQueries({ queryKey: ["schedules"] })
  })

  socket.on("schedule_executed", () => {
    queryClient.invalidateQueries({ queryKey: ["schedules"] })
    queryClient.invalidateQueries({ queryKey: ["devices"] })
  })

  socket.on('disconnect', (reason) => {
    console.warn('[Socket] Disconnected:', reason)
  })

  socket.on('connect_error', (error) => {
    console.error('[Socket] Connection error:', error.message)
  })

  return socket
}

export function getSocket() {
  return socket
}

export function disconnectSocket() {
  if (socket) {
    socket.disconnect()
    socket = null
  }
}
