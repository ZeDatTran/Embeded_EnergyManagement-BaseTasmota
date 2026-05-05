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
    reconnectionAttempts: 5,
    transports: ['websocket', 'polling'],
    auth: {
      token: token
    }
  })

  // Listen for connection
  socket.on('connect', () => {
    console.log('Socket.IO connected')
    socket?.emit('subscribe_devices')
  })

  // Listen for device updates
  socket.on("device_update", (data) => {
    console.log('Device update:', data.device_id)
    queryClient.setQueryData(["devices"], (oldData: any) => {
      if (!oldData) return oldData
      return oldData.map((device: any) => 
        device.id === data.device_id 
          ? { ...device, telemetry: data.telemetry, attributes: data.attributes } 
          : device
      )
    })
  })

  // Listen for schedule updates
  socket.on("schedule_updated", () => {
    console.log('Schedule updated')
    queryClient.invalidateQueries({ queryKey: ["schedules"] })
  })

  socket.on('disconnect', () => {
    console.log('Socket.IO disconnected')
  })

  socket.on('error', (error) => {
    console.error('Socket.IO error:', error)
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
