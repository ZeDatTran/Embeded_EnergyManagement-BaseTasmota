// API configuration and helper functions
const API_BASE_URL = "http://localhost:5000";

import { aggregateEnergyDataByDay } from "./utils";

export function getAuthHeaders(): HeadersInit {
  if (typeof window === "undefined") return { "Content-Type": "application/json" };
  const token = localStorage.getItem("smart_home_token");
  if (token) {
    return {
      "Content-Type": "application/json",
      "Authorization": `Bearer ${token}`
    };
  }
  return { "Content-Type": "application/json" };
}

export interface Device {
  id: string;
  name: string;
  type: "light" | "fan" | "ac" | "sensor" | "camera" | "cb" | "circuit_breaker";
  status: "online" | "offline";
  isOn: boolean;
  location: string;
  lastUpdate: string;
  power?: number; // watts
  voltage?: number; // volts
  current?: number; // amperes
  energyToday?: number; // kWh
  energyTotal?: number; // kWh
  powerFactor?: number; // power factor
  // CB specific fields
  roomType?: string;
  roomName?: string;
  floor?: number;
  maxLoad?: number;
}

export interface CircuitBreakerInput {
  deviceId: string;
  name: string;
  roomType: string;
  roomName: string;
  floor?: number;
  maxLoad?: number;
}

export interface AvailableDevice {
  id: string;
  name: string;
  type: string;
  isConfigured: boolean;
  configuredAs?: string;
}

export interface Alert {
  id: string;
  type: "warning" | "error" | "info" | "success";
  message: string;
  timestamp: string;
  deviceId?: string;
  read: boolean;
}

export interface ActivityLog {
  id: string;
  action: string;
  deviceId?: string;
  deviceName?: string;
  user: string;
  timestamp: string;
  details?: string;
}

export interface EnergyData {
  timestamp: string;
  consumption: number; // kWh
  cost: number;
}

export interface EnergySummaryData {
  totalConsumption: number;
  totalCost: number;
}

export interface EnergyBudgetProfile {
  id: string;
  month_key: string;
  target_bill_vnd: number;
  warning_threshold_percent: number;
  optimization_mode: "manual" | "assisted" | "automatic";
  auto_apply_recommendations: number;
  target_kwh_month?: number;
  current_spent_vnd?: number;
  current_consumed_kwh?: number;
  latest_forecast_bill_vnd?: number;
  latest_forecast_kwh_month?: number;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface BudgetAnalysisDevice {
  deviceId: string;
  deviceName: string;
  totalKwh?: number;
  avgPowerW?: number;
  energyKwh?: number;
  priority?: string;
  autoControllable?: boolean;
}

export interface BudgetAnalysis {
  monthKey: string;
  actualConsumedKwhMonth: number;
  actualSpentVndMonth: number;
  forecastKwhMonth: number;
  forecastBillVnd: number;
  targetBillVnd: number;
  targetKwhMonth: number;
  overrunVnd: number;
  requiredReductionKwh: number;
  daysInMonth: number;
  elapsedDays: number;
  remainingDaysInMonth: number;
  avgDailyKwh: number;
  recentAvgDailyKwh: number;
  budgetConfigured: boolean;
  topConsumers: BudgetAnalysisDevice[];
  topFlexibleConsumers: BudgetAnalysisDevice[];
}

export interface RecommendationAction {
  id: string;
  run_id: string;
  device_id: string;
  action_type: string;
  proposed_action: "on" | "off";
  proposed_start: string;
  proposed_end?: string | null;
  proposed_duration_minutes: number;
  estimated_energy_saved_kwh: number;
  estimated_cost_saved_vnd: number;
  comfort_impact_score: number;
  saving_score: number;
  confidence_score: number;
  priority_score: number;
  reason_code: string;
  reason_text?: string;
  approval_status: string;
  mapped_schedule_id?: string | null;
  deviceName?: string;
}

export interface RecommendationRun {
  id: string;
  budget_profile_id: string;
  month_key: string;
  generated_at: string;
  generated_by: string;
  run_type: string;
  planning_horizon_days: number;
  strategy: string;
  baseline_forecast_bill_vnd: number;
  optimized_forecast_bill_vnd?: number;
  baseline_forecast_kwh: number;
  optimized_forecast_kwh?: number;
  required_bill_reduction_vnd: number;
  required_kwh_reduction: number;
  achieved_kwh_reduction_estimate: number;
  status: string;
}

export interface GeneratedEnergyPlan {
  run: RecommendationRun;
  analysis: BudgetAnalysis;
  actions: RecommendationAction[];
  summary: {
    horizonTargetReductionKwh: number;
    estimatedReductionKwh: number;
    estimatedReductionVnd: number;
    message: string;
  };
}

// API functions
export async function fetchDevices(): Promise<Device[]> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/check-data`, {
      headers: getAuthHeaders(),
    });
    if (!response.ok) throw new Error("Failed to fetch devices");
    const result = await response.json();

    // Transform API response to Device format
    if (result.status === "success" && result.data) {
      return (result.data as any[]).map((deviceData: any, index: number) => {
        const attributes = deviceData?.attributes || {};
        const telemetry = deviceData?.telemetry || {};
        const metadata = deviceData?.metadata || {};
        const deviceId = deviceData?.id || `device-${index}`;

        const voltage = parseFloat(telemetry["ENERGY-Voltage"] || "0");
        const status = attributes.POWER === "ON" ? "online" : "offline";
        const isOn = attributes.POWER === "ON";

        return {
          id: deviceId,
          name: metadata.name || deviceData.name || `CB ${index + 1}`,
          type: metadata.type || deviceData.type || "cb",
          status: status as "online" | "offline",
          isOn,
          location: metadata.location || deviceData.location || "",
          lastUpdate: new Date().toISOString(),
          power: parseFloat(telemetry["ENERGY-Power"] || "0"),
          voltage: voltage,
          current: parseFloat(telemetry["ENERGY-Current"] || "0"),
          energyToday: parseFloat(telemetry["ENERGY-Today"] || "0"),
          energyTotal: parseFloat(telemetry["ENERGY-Total"] || "0"),
          powerFactor: parseFloat(telemetry["ENERGY-Factor"] || "0"),
          // CB specific fields
          roomType: metadata.room_type || deviceData.roomType,
          roomName: metadata.room_name || deviceData.roomName,
          floor: metadata.floor || deviceData.floor,
          maxLoad: metadata.max_load || deviceData.maxLoad || 32,
        };
      });
    }

    return [];
  } catch (error) {
    console.error("Error fetching devices:", error);
    return [];
  }
}

// Fetch available devices from CoreIoT for adding new CB
export async function fetchAvailableDevices(): Promise<AvailableDevice[]> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/devices/available`, {
      headers: getAuthHeaders(),
    });
    if (!response.ok) throw new Error("Failed to fetch available devices");
    const result = await response.json();

    if (result.status === "success" && result.data) {
      return result.data as AvailableDevice[];
    }

    return [];
  } catch (error) {
    console.error("Error fetching available devices:", error);
    return [];
  }
}

export async function controlAllDevices(command: "ON" | "OFF"): Promise<Device[]> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/control/group/${command}`, {
      method: "POST",
      headers: getAuthHeaders(),
    })
    if (!response.ok) throw new Error("Failed to control devices")
    const data = await response.json()
    // Return updated devices based on results
    return (
      data.results?.map((result: any) => ({
        id: result.device_id,
        isOn: command === "ON",
      })) || []
    )
  } catch (error) {
    console.error("Error controlling devices:", error)
    return []
  }
}


export async function fetchEnergyData(
  period: "day" | "week" | "month",
  deviceId?: string
): Promise<EnergyData[]> {
  try {
    const query = new URLSearchParams({ period });
    if (deviceId) {
      query.set("deviceId", deviceId);
    }
    const response = await fetch(`${API_BASE_URL}/api/energy?${query.toString()}`, {
      headers: getAuthHeaders(),
    });
    if (!response.ok) throw new Error("Failed to fetch energy data");
    
    const data: EnergyData[] = await response.json();
    
    // Backend now handles aggregation (hourly for day, daily for week/month)
    // No need for frontend aggregation
    
    return data;
  } catch (error) {
    console.error("Error fetching energy data:", error);
    return [];
  }
}

export async function fetchEnergySummary(
  period: "day" | "week" | "month" = "month",
  deviceId?: string
): Promise<EnergySummaryData | null> {
  try {
    const query = new URLSearchParams({ period });
    if (deviceId) {
      query.set("deviceId", deviceId);
    }
    const response = await fetch(`${API_BASE_URL}/api/energy/summary?${query.toString()}`, {
      headers: getAuthHeaders(),
    });
    if (!response.ok) throw new Error("Failed to fetch energy summary");

    const result = await response.json();
    if (result?.status === "success" && result?.data) {
      return result.data as EnergySummaryData;
    }
    return null;
  } catch (error) {
    console.error("Error fetching energy summary:", error);
    return null;
  }
}

// Add new Circuit Breaker
export async function addCircuitBreaker(
  cbData: CircuitBreakerInput
): Promise<{ success: boolean; message?: string; device?: Device }> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/devices/cb`, {
      method: "POST",
      headers: getAuthHeaders(),
      body: JSON.stringify(cbData),
    });

    const result = await response.json();

    if (!response.ok) {
      return {
        success: false,
        message: result.message || "Không thể thêm CB",
      };
    }

    return {
      success: true,
      message: "Thêm CB thành công",
      device: result.device,
    };
  } catch (error) {
    console.error("Error adding circuit breaker:", error);
    return {
      success: false,
      message: "Lỗi kết nối server",
    };
  }
}

// Update Circuit Breaker
export async function updateCircuitBreaker(
  deviceId: string,
  cbData: CircuitBreakerInput
): Promise<{ success: boolean; message?: string; device?: Device }> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/devices/cb/${deviceId}`, {
      method: "PUT",
      headers: getAuthHeaders(),
      body: JSON.stringify(cbData),
    });

    const result = await response.json();

    if (!response.ok) {
      return {
        success: false,
        message: result.message || "Không thể cập nhật CB",
      };
    }

    return {
      success: true,
      message: "Cập nhật CB thành công",
      device: result.device,
    };
  } catch (error) {
    console.error("Error updating circuit breaker:", error);
    return {
      success: false,
      message: "Lỗi kết nối server",
    };
  }
}

export async function deleteCircuitBreaker(
  deviceId: string
): Promise<{ success: boolean; message?: string }> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/devices/cb/${deviceId}`, {
      method: "DELETE",
      headers: getAuthHeaders(),
    });

    const result = await response.json();

    if (!response.ok) {
      return {
        success: false,
        message: result.message || "Không thể xóa CB",
      };
    }

    return {
      success: true,
      message: "Xóa CB thành công",
    };
  } catch (error) {
    console.error("Error deleting circuit breaker:", error);
    return {
      success: false,
      message: "Lỗi kết nối server",
    };
  }
}

function getMockLogs(): ActivityLog[] {
  return [
    {
      id: "1",
      action: "Bật thiết bị",
      deviceId: "1",
      deviceName: "Đèn phòng khách",
      user: "Người dùng",
      timestamp: new Date(Date.now() - 600000).toISOString(),
    },
    {
      id: "2",
      action: "Tắt thiết bị",
      deviceId: "2",
      deviceName: "Quạt phòng ngủ",
      user: "Người dùng",
      timestamp: new Date(Date.now() - 1800000).toISOString(),
    },
    {
      id: "3",
      action: "Tạo quy tắc tự động",
      user: "Người dùng",
      timestamp: new Date(Date.now() - 3600000).toISOString(),
      details: "Bật đèn lúc 18:00",
    },
  ];
}

export async function fetchCurrentBudget(monthKey?: string): Promise<{ budget: EnergyBudgetProfile | null; analysis: BudgetAnalysis }> {
  const query = monthKey ? `?monthKey=${monthKey}` : "";
  const response = await fetch(`${API_BASE_URL}/api/energy-budget/current${query}`, {
    headers: getAuthHeaders(),
  });
  if (!response.ok) throw new Error("Failed to fetch current budget");
  const result = await response.json();
  return result.data;
}

export async function saveCurrentBudget(input: {
  monthKey?: string;
  targetBillVnd: number;
  warningThresholdPercent: number;
  optimizationMode: "manual" | "assisted" | "automatic";
  autoApplyRecommendations: boolean;
}): Promise<{ budget: EnergyBudgetProfile; analysis: BudgetAnalysis }> {
  const response = await fetch(`${API_BASE_URL}/api/energy-budget/current`, {
    method: "PUT",
    headers: getAuthHeaders(),
    body: JSON.stringify(input),
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.message || "Failed to save budget");
  return result.data;
}

export async function fetchBudgetHistory(): Promise<EnergyBudgetProfile[]> {
  const response = await fetch(`${API_BASE_URL}/api/energy-budget/history`, {
    headers: getAuthHeaders(),
  });
  if (!response.ok) throw new Error("Failed to fetch budget history");
  const result = await response.json();
  return result.data || [];
}

export async function fetchEnergyPlanAnalysis(monthKey?: string): Promise<BudgetAnalysis> {
  const query = monthKey ? `?monthKey=${monthKey}` : "";
  const response = await fetch(`${API_BASE_URL}/api/energy-plan/analysis/current${query}`, {
    headers: getAuthHeaders(),
  });
  if (!response.ok) throw new Error("Failed to fetch energy plan analysis");
  const result = await response.json();
  return result.data;
}

export async function fetchEnergyPlanDevices(): Promise<BudgetAnalysisDevice[]> {
  const response = await fetch(`${API_BASE_URL}/api/energy-plan/analysis/devices`, {
    headers: getAuthHeaders(),
  });
  if (!response.ok) throw new Error("Failed to fetch device analysis");
  const result = await response.json();
  return result.data || [];
}

export async function generateEnergyPlan(input: {
  monthKey?: string;
  planningHorizonDays: number;
  strategy: "conservative" | "balanced" | "aggressive";
}): Promise<GeneratedEnergyPlan> {
  const response = await fetch(`${API_BASE_URL}/api/energy-plan/generate`, {
    method: "POST",
    headers: getAuthHeaders(),
    body: JSON.stringify(input),
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.message || "Failed to generate energy plan");
  return result.data;
}

export async function fetchRecommendationRuns(limit = 20): Promise<RecommendationRun[]> {
  const response = await fetch(`${API_BASE_URL}/api/energy-plan/runs?limit=${limit}`, {
    headers: getAuthHeaders(),
  });
  if (!response.ok) throw new Error("Failed to fetch recommendation runs");
  const result = await response.json();
  return result.data || [];
}

export async function fetchRecommendationActions(runId: string): Promise<RecommendationAction[]> {
  const response = await fetch(`${API_BASE_URL}/api/energy-plan/runs/${runId}/actions`, {
    headers: getAuthHeaders(),
  });
  if (!response.ok) throw new Error("Failed to fetch recommendation actions");
  const result = await response.json();
  return result.data || [];
}

export async function approveRecommendationAction(actionId: string): Promise<RecommendationAction> {
  const response = await fetch(`${API_BASE_URL}/api/energy-plan/actions/${actionId}/approve`, {
    method: "POST",
    headers: getAuthHeaders(),
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.message || "Failed to approve action");
  return result.data;
}

export async function rejectRecommendationAction(actionId: string): Promise<RecommendationAction> {
  const response = await fetch(`${API_BASE_URL}/api/energy-plan/actions/${actionId}/reject`, {
    method: "POST",
    headers: getAuthHeaders(),
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.message || "Failed to reject action");
  return result.data;
}

export async function applyRecommendationRun(runId: string): Promise<{ runId: string; createdSchedulesCount: number; createdScheduleIds: string[] }> {
  const response = await fetch(`${API_BASE_URL}/api/energy-plan/runs/${runId}/apply`, {
    method: "POST",
    headers: getAuthHeaders(),
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.message || "Failed to apply recommendation run");
  return result.data;
}