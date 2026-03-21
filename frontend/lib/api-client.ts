// API Client for FE-Son - Communicates with Flask Backend
// Base URL for the backend API
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:5000';

/**
 * Types for device data from backend
 */
export interface DeviceAttributes {
  POWER?: string;
  [key: string]: any;
}

export interface DeviceTelemetry {
  'ENERGY-Voltage'?: number | string;
  'ENERGY-Current'?: number | string;
  'ENERGY-Power'?: number | string;
  'ENERGY-Today'?: number | string;
  'ENERGY-Total'?: number | string;
  'ENERGY-Factor'?: number | string;
  [key: string]: any;
}

export interface Device {
  type: string;
  name?: string;
  location: string;
  id: string;
  attributes: DeviceAttributes;
  telemetry: DeviceTelemetry;
  metadata?: {
    type?: string;
    name?: string;
    location?: string;
    room_type?: string;
    room_name?: string;
    max_load?: number;
    floor?: number;
  };
}

export interface DeviceCheckDataResponse {
  status: 'success' | 'error';
  message?: string;
  data?: Device[];
}

export interface ControlResponse {
  status: 'success' | 'error' | 'partial_failure';
  message?: string;
  device_id?: string;
  command_sent?: string;
  total_devices?: number;
  results?: ControlResponse[];
}

/**
 * Fetch all devices from the backend
 * GET /check-data
 */
export async function fetchDevices(): Promise<Device[]> {
  try {
    const response = await fetch(`${API_BASE_URL}/check-data`, {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
      },
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(
        errorData.message || `Failed to fetch devices: ${response.statusText}`
      );
    }

    const data: DeviceCheckDataResponse = await response.json();

    if (data.status === 'error') {
      throw new Error(data.message || 'Failed to fetch devices');
    }

    return data.data || [];
  } catch (error) {
    console.error('Error fetching devices:', error);
    throw error;
  }
}

/**
 * Control a specific device
 * POST /control/<device_id>/<command>
 * @param deviceId - The ID of the device to control
 * @param command - The command to send ('on' or 'off')
 */
export async function controlDevice(
  deviceId: string,
  command: 'on' | 'off'
): Promise<ControlResponse> {
  try {
    const commandLower = command.toLowerCase();
    
    if (!['on', 'off'].includes(commandLower)) {
      throw new Error('Invalid command. Only "on" or "off" are allowed.');
    }

    // Create an AbortController with 30 second timeout
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 30000);

    try {
      const response = await fetch(
        `${API_BASE_URL}/control/${deviceId}/${commandLower}`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          signal: controller.signal,
        }
      );

      const data: ControlResponse = await response.json().catch(() => ({
        status: 'error' as const,
        message: 'Failed to parse server response'
      }));

      if (!response.ok) {
        throw new Error(
          data.message || `Failed to control device: ${response.statusText}`
        );
      }

      return data;
    } finally {
      clearTimeout(timeoutId);
    }
  } catch (error) {
    if (error instanceof Error && error.name === 'AbortError') {
      console.error(`Device control request timed out after 30 seconds for device ${deviceId}`);
      throw new Error('Request timed out. The device may be unresponsive. Please try again.');
    }
    console.error(`Error controlling device ${deviceId}:`, error);
    throw error;
  }
}

/**
 * Control all devices in a group
 * POST /control/group/<command>
 * @param command - The command to send ('on' or 'off')
 */
export async function controlGroupDevices(
  command: 'on' | 'off'
): Promise<ControlResponse> {
  try {
    const commandLower = command.toLowerCase();
    
    if (!['on', 'off'].includes(commandLower)) {
      throw new Error('Invalid command. Only "on" or "off" are allowed.');
    }

    // Create an AbortController with 30 second timeout
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 30000);

    try {
      const response = await fetch(
        `${API_BASE_URL}/control/group/${commandLower}`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          signal: controller.signal,
        }
      );

      const data: ControlResponse = await response.json().catch(() => ({
        status: 'error' as const,
        message: 'Failed to parse server response'
      }));

      if (!response.ok) {
        throw new Error(
          data.message || `Failed to control group: ${response.statusText}`
        );
      }

      return data;
    } finally {
      clearTimeout(timeoutId);
    }
  } catch (error) {
    if (error instanceof Error && error.name === 'AbortError') {
      console.error(`Group control request timed out after 30 seconds`);
      throw new Error('Request timed out. Devices may be unresponsive. Please try again.');
    }
    console.error('Error controlling group devices:', error);
    throw error;
  }
}

/**
 * Check if the backend API is accessible
 * GET /check-token
 */
export async function checkApiHealth(): Promise<boolean> {
  try {
    const response = await fetch(`${API_BASE_URL}/check-token`, {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
      },
    });

    return response.ok;
  } catch (error) {
    console.error('Error checking API health:', error);
    return false;
  }
}

/**
 * Fetch a single device by ID
 * GET /device/<device_id>
 */
export async function fetchDeviceById(deviceId: string): Promise<Device | null> {
  try {
    const response = await fetch(`${API_BASE_URL}/device/${deviceId}`, {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
      },
    });

    if (!response.ok) {
      // Fallback: Get all devices and find by ID
      const devices = await fetchDevices();
      return devices.find(d => d.id === deviceId) || null;
    }

    const data = await response.json();
    return data.device || data;
  } catch (error) {
    console.error(`Error fetching device ${deviceId}:`, error);
    // Fallback: Get all devices and find by ID
    try {
      const devices = await fetchDevices();
      return devices.find(d => d.id === deviceId) || null;
    } catch {
      return null;
    }
  }
}

/**
 * Device history data point
 */
export interface DeviceHistoryPoint {
  timestamp: string;
  power: number;
  voltage: number;
  current: number;
  energy: number;
}

export interface DeviceHistoryFetchOptions {
  pageSize?: number;
  chunkDays?: number;
  startTs?: number;
  maxPages?: number;
}

/**
 * Fetch device history data for charts.
 * - day/week/month -> GET /device/<device_id>/history?period=<period>
 * - all -> GET /device/<device_id>/history/full with cursor pagination
 */
export async function fetchDeviceHistory(
  deviceId: string,
  period: string = 'day',
  options: DeviceHistoryFetchOptions = {}
): Promise<DeviceHistoryPoint[]> {
  const normalizedPeriod = (period || 'day').toLowerCase();

  try {
    if (normalizedPeriod === 'all') {
      const pageSize = Math.max(1, Math.min(options.pageSize ?? 5000, 20000));
      const chunkDays = Math.max(1, options.chunkDays ?? 3);
      const maxPages = Math.max(1, options.maxPages ?? 50);

      let cursor: number | undefined = options.startTs;
      let hasMore = true;
      let pageCount = 0;
      const allPoints: DeviceHistoryPoint[] = [];

      while (hasMore && pageCount < maxPages) {
        const params = new URLSearchParams();
        params.set('pageSize', String(pageSize));
        params.set('chunkDays', String(chunkDays));
        if (cursor !== undefined) {
          params.set('cursor', String(cursor));
        }

        const response = await fetch(
          `${API_BASE_URL}/device/${deviceId}/history/full?${params.toString()}`,
          {
            method: 'GET',
            headers: {
              'Content-Type': 'application/json',
            },
          }
        );

        if (!response.ok) {
          throw new Error(`Failed to fetch full history: ${response.status}`);
        }

        const data = await response.json();
        const pagePoints = (data?.history || []) as DeviceHistoryPoint[];
        allPoints.push(...pagePoints);

        hasMore = Boolean(data?.hasMore);
        cursor = typeof data?.nextCursor === 'number' ? data.nextCursor : undefined;
        pageCount += 1;

        if (hasMore && cursor === undefined) {
          break;
        }
      }

      return allPoints;
    }

    const response = await fetch(`${API_BASE_URL}/device/${deviceId}/history?period=${normalizedPeriod}`, {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
      },
    });

    if (!response.ok) {
      throw new Error(`Failed to fetch history: ${response.status}`);
    }

    const data = await response.json();
    return (data?.history || []) as DeviceHistoryPoint[];
  } catch (error) {
    console.error(`Error fetching device history for ${deviceId}:`, error);
    return [];
  }
}

/**
 * Get the API base URL
 */
export function getApiBaseUrl(): string {
  return API_BASE_URL;
}
