import {
  Lightbulb,
  Fan,
  AirVent,
  Thermometer,
  Camera,
  Power,
  PowerOff,
  Wifi,
  WifiOff,
  Bell,
  Clock,
  Zap,
  Settings,
  Home,
  Calendar,
  Activity,
  AlertTriangle,
  Info,
  CheckCircle,
  XCircle,
  Menu,
  X,
  Plus,
  Edit,
  Trash2,
  ChevronDown,
  ChevronRight,
  BarChart3,
  TrendingUp,
  TrendingDown,
  CircuitBoard,
  DoorOpen,
  Bed,
  Sofa,
  UtensilsCrossed,
  Bath,
  Building2,
  ShieldOff,
  CalendarClock,
  Banknote,
} from "lucide-react"

export const Icons = {
  // Device types
  light: Lightbulb,
  fan: Fan,
  ac: AirVent,
  sensor: Thermometer,
  camera: Camera,
  
  // Circuit Breaker / Room types
  cb: CircuitBoard,
  circuit_breaker: CircuitBoard,
  living_room: Sofa,
  bedroom: Bed,
  office: Building2,
  kitchen: UtensilsCrossed,
  bathroom: Bath,
  balcony: DoorOpen,

  // Status
  power: Power,
  powerOff: PowerOff,
  online: Wifi,
  offline: WifiOff,

  // Navigation
  home: Home,
  devices: Settings,
  schedule: Calendar,
  energy: Zap,
  activity: Activity,

  // Actions
  bell: Bell,
  clock: Clock,
  menu: Menu,
  close: X,
  plus: Plus,
  edit: Edit,
  trash: Trash2,
  chevronDown: ChevronDown,
  chevronRight: ChevronRight,

  // Alerts
  warning: AlertTriangle,
  error: XCircle,
  info: Info,
  success: CheckCircle,

  // Charts
  chart: BarChart3,
  trendingUp: TrendingUp,
  trendingDown: TrendingDown,

  // Dashboard
  shieldOff: ShieldOff,
  calendarClock: CalendarClock,
  banknote: Banknote,
}
