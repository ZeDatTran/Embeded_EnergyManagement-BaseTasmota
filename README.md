# Smart Home Energy Monitoring and Optimization System

A full-stack IoT application for real-time monitoring, control, and AI-driven energy optimization of smart home devices. The system integrates SmartPlugs running Tasmota firmware with a cloud IoT platform (CoreIoT), a Python backend, and a Next.js dashboard.

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Features](#features)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Getting Started](#getting-started)
  - [Prerequisites](#prerequisites)
  - [Backend Setup](#backend-setup)
  - [Frontend Setup](#frontend-setup)
- [Configuration](#configuration)
- [API Reference](#api-reference)
- [Device Control via SmartPlug and Tasmota](#device-control-via-smartplug-and-tasmota)
- [Energy Forecast and Budget Optimization](#energy-forecast-and-budget-optimization)
- [AI Chatbot](#ai-chatbot)
- [Contributing](#contributing)

---

## Overview

This project is a graduation thesis system that enables homeowners to:

- Monitor electricity consumption per device in real time
- Remotely control smart plugs (ON/OFF) from a web dashboard
- Set monthly energy budgets and receive AI-generated optimization schedules
- Get alerts when devices exceed current thresholds or when bills are projected to overspend
- Interact with an AI chatbot to control devices and understand energy recommendations

---

## Architecture

```
SmartPlug (Tasmota firmware)
        |  MQTT
CoreIoT Cloud Platform (app.coreiot.io)
        |  REST API / WebSocket
Backend (Flask + Python)
        |  Socket.IO / HTTP
Frontend (Next.js)
        |
User Browser
```

The backend continuously polls CoreIoT for telemetry data (voltage, current, power, energy) from each registered SmartPlug. Control commands are forwarded as RPC calls through CoreIoT down to the Tasmota firmware via MQTT.

---

## Features

### Real-Time Device Monitoring
- Live telemetry: voltage (V), current (A), active power (W), accumulated energy (kWh)
- Per-device POWER state tracking (ON / OFF)
- Overcurrent protection with configurable thresholds and automatic alerts

### Device Control via SmartPlug and Tasmota
- Toggle individual devices ON or OFF from the dashboard
- Batch control all devices for a user simultaneously
- RPC commands are forwarded through CoreIoT to Tasmota-flashed plugs over MQTT
- Control history and execution logs are persisted in the database

### Automated Scheduling
- Manual schedules: define ON/OFF times per device per day of week
- Optimizer-generated schedules: derived from ML recommendations to meet energy budgets
- Background schedule executor runs every minute to trigger scheduled actions

### Energy Budget and AI Optimization
- Set a monthly electricity budget in VND
- ML ensemble model (Random Forest, XGBoost, MLP, Linear Regression) forecasts expected consumption
- When forecast exceeds budget, the system generates optimization recommendations
- Recommendations include: turn-off windows, off-peak shifting, runtime capping, and delay-start actions
- Users can review, approve, or reject recommendations before they are applied as schedules

### AI Chatbot Assistant
- Powered by Google Gemini (google-genai SDK)
- Understands natural language commands to control devices and query energy data
- Explains optimization recommendations in plain language
- Broadcasts device state changes to all connected clients via Socket.IO

### Alerts and Notifications
- Email alerts when a device draws current above the configured threshold
- Rate-limited to one alert per device per 10 minutes to avoid spam
- Budget warning notifications when projected monthly spend crosses the warning threshold

### User Authentication
- JWT-based authentication with OTP email verification
- Each user has isolated device groups on CoreIoT; they can only see and control their own devices

---

## Tech Stack

### Backend

| Layer | Technology |
|---|---|
| Web framework | Flask 3.0 |
| Real-time communication | Flask-SocketIO 5.3 |
| Database (devices, users) | MongoDB (pymongo 4.7) |
| Database (energy, schedules) | SQLite |
| HTTP client | requests |
| ML models | scikit-learn, XGBoost, CatBoost |
| AI chatbot | Google Gemini (google-genai >= 1.0) |
| Authentication | PyJWT, python-dotenv |

### Frontend

| Layer | Technology |
|---|---|
| Framework | Next.js 14 |
| Language | TypeScript |
| Styling | Tailwind CSS 4 |
| UI components | Radix UI + shadcn/ui pattern |
| Charts | Recharts |
| Real-time | Socket.IO client |
| State management | Zustand, TanStack Query |
| Forms | React Hook Form + Zod |

### IoT Layer

| Component | Technology |
|---|---|
| Smart plug firmware | Tasmota (open-source) |
| IoT cloud platform | CoreIoT (app.coreiot.io) |
| Communication protocol | MQTT over TCP (port 1883) |
| Telemetry keys | ENERGY-Voltage, ENERGY-Current, ENERGY-Power, ENERGY-Today, ENERGY-Total, ENERGY-Factor |

---

## Project Structure

```
Doan1/
├── backend/
│   ├── app.py                        # Flask application entry point
│   ├── database.py                   # Unified DB access layer (SQLite + MongoDB)
│   ├── db_connection.py              # MongoDB connection helper
│   ├── db_devices.py                 # Device CRUD (MongoDB)
│   ├── db_users.py                   # User CRUD (MongoDB)
│   ├── db_core.py                    # Core energy data (SQLite)
│   ├── db_budget.py                  # Budget profiles and recommendation runs
│   ├── db_recommendations.py         # Recommendation actions CRUD
│   ├── db_schedules.py               # Schedule CRUD
│   ├── db_forecast.py                # Forecast result storage
│   ├── energy_optimization_schema.sql# SQLite schema definition
│   ├── requirements.txt
│   ├── .env                          # Environment variables (see Configuration)
│   ├── app_core/
│   │   ├── shared.py                 # Shared state, CoreIoT API calls, RPC control
│   │   ├── workers.py                # Background threads: polling, scheduler, WebSocket
│   │   ├── socket_events.py          # Socket.IO event handlers
│   │   ├── chatbot_api.py            # Gemini-powered AI chatbot blueprint
│   │   ├── auth_routes.py            # Authentication and OTP endpoints
│   │   ├── email_utils.py            # Email alerts (SMTP)
│   │   ├── analysis_routes.py        # Energy analysis endpoints
│   │   └── routes/
│   │       ├── control_routes.py     # POST /api/control/<device_id>/<command>
│   │       ├── device_routes.py      # Device CRUD and telemetry endpoints
│   │       ├── energy_routes.py      # Hourly kWh and plug energy endpoints
│   │       ├── forecast_routes.py    # Budget and forecast endpoints
│   │       ├── schedule_routes.py    # Schedule management endpoints
│   │       └── general_routes.py     # Health check and misc endpoints
│   └── ml/
│       ├── ensemble_model_improved.py# Ensemble forecasting model definition
│       ├── train_improved_models.py  # Model training pipeline
│       ├── forecast_server.py        # Forecast WebSocket server
│       ├── websocket_forecast.py     # Forecast client used by workers
│       ├── evaluate_visualize.py     # Evaluation and visualization utilities
│       └── run_ensemble.py           # Entry point for standalone forecast runs
└── frontend/
    ├── app/
    │   ├── (auth)/                   # Login, register, OTP verification pages
    │   └── (dashboard)/              # Main dashboard pages
    ├── components/                   # Reusable UI components
    ├── context/                      # React context providers
    ├── hooks/                        # Custom React hooks
    ├── lib/                          # API client utilities
    └── styles/                       # Global styles
```

---

## Getting Started

### Prerequisites

- Python 3.11 or higher
- Node.js 18 or higher
- MongoDB instance (local or Atlas)
- A CoreIoT account with at least one device group configured
- SmartPlugs flashed with Tasmota firmware, connected to CoreIoT via MQTT

### Backend Setup

1. Navigate to the backend directory:

   ```bash
   cd backend
   ```

2. Create and activate a virtual environment:

   ```bash
   python -m venv venv
   # Windows
   venv\Scripts\activate
   # Linux / macOS
   source venv/bin/activate
   ```

3. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

4. Copy `.env.example` to `.env` and fill in your credentials (see [Configuration](#configuration)).

5. Initialize the SQLite database schema:

   ```bash
   sqlite3 energy.db < energy_optimization_schema.sql
   ```

6. Start the backend server:

   ```bash
   python app.py
   ```

   The API will be available at `http://localhost:5000`.

### Frontend Setup

1. Navigate to the frontend directory:

   ```bash
   cd frontend
   ```

2. Install dependencies:

   ```bash
   npm install
   ```

3. Start the development server:

   ```bash
   npm run dev
   ```

   The dashboard will be available at `http://localhost:3000`.

---

## Configuration

Create a `.env` file inside the `backend/` directory with the following variables:

```env
# CoreIoT platform JWT token for API authentication
JWT_TOKEN=<your_coreiot_jwt_token>

# CoreIoT device group ID (fallback; each user stores their own in MongoDB)
GROUP_ID=<your_coreiot_group_id>

# MongoDB connection string
MONGO_URI=mongodb://localhost:27017
MONGO_DB_NAME=smarthome

# SQLite database file path
SQLITE_DB_PATH=energy.db

# SMTP settings for email alerts
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your_email@gmail.com
SMTP_PASS=your_app_password

# Google Gemini API key for the AI chatbot
GEMINI_API_KEY=<your_gemini_api_key>

# JWT secret for user authentication
JWT_SECRET=<your_jwt_secret>
```

---

## API Reference

### Control Endpoints

| Method | Path | Description |
|---|---|---|
| POST | `/api/control/<device_id>/on` | Turn a specific device ON |
| POST | `/api/control/<device_id>/off` | Turn a specific device OFF |
| POST | `/api/control/group/on` | Turn all user devices ON |
| POST | `/api/control/group/off` | Turn all user devices OFF |

### Device Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/api/devices` | List all devices for the authenticated user |
| POST | `/api/devices` | Register a new device |
| PUT | `/api/devices/<device_id>` | Update device metadata |
| DELETE | `/api/devices/<device_id>` | Remove a device |
| GET | `/api/devices/<device_id>/telemetry` | Get latest telemetry snapshot |

### Energy Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/api/energy/hourly` | Get hourly kWh history |
| GET | `/api/energy/plugs/<device_id>` | Get per-plug hourly energy |
| GET | `/api/energy/summary` | Monthly consumption and bill summary |

### Schedule Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/api/schedules` | List all schedules |
| POST | `/api/schedules` | Create a new schedule |
| PUT | `/api/schedules/<id>` | Update a schedule |
| DELETE | `/api/schedules/<id>` | Delete a schedule |

### Forecast and Budget Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/api/forecast` | Get current energy forecast |
| GET | `/api/budget` | Get active budget profile |
| POST | `/api/budget` | Create or update budget profile |
| GET | `/api/recommendations` | List optimization recommendations |
| POST | `/api/recommendations/<run_id>/approve` | Approve a recommendation run |

All endpoints (except auth) require a valid `Authorization: Bearer <token>` header.

---

## Device Control via SmartPlug and Tasmota

Each SmartPlug runs the [Tasmota](https://tasmota.github.io) open-source firmware. Tasmota exposes device control via MQTT using the standard `cmnd/<device_name>/POWER` topic, and reports energy metrics via the `tele/<device_name>/SENSOR` topic.

The devices are registered on the CoreIoT platform, which acts as an MQTT broker and REST API gateway. The backend communicates with CoreIoT using:

**Telemetry polling**

```
GET /api/plugins/telemetry/DEVICE/<id>/values/timeseries
```

Fetches ENERGY-Voltage, ENERGY-Current, ENERGY-Power, ENERGY-Today, ENERGY-Total, ENERGY-Factor every 10 seconds.

**Attribute polling**

```
GET /api/plugins/telemetry/DEVICE/<id>/values/attributes/CLIENT_SCOPE
```

Reads the `POWER` attribute (ON / OFF state) reported by Tasmota.

**RPC control**

```
POST /api/rpc/oneway/<device_id>
Body: {"method": "POWER", "params": "ON"}
```

Sends a one-way RPC to toggle the plug. CoreIoT translates this into an MQTT `cmnd` message to the Tasmota device.

Control flow example:

```
User clicks "Turn Off" on dashboard
    -> POST /api/control/<device_id>/off
    -> send_rpc_to_device(device_id, "OFF")
    -> CoreIoT REST API: POST /api/rpc/oneway/<device_id>
    -> MQTT: cmnd/<device>/POWER = OFF
    -> Tasmota cuts relay power
    -> Tasmota reports POWER=OFF via MQTT
    -> CoreIoT stores new attribute value
    -> Backend reads POWER attribute on next poll
    -> Socket.IO broadcasts updated state to all dashboard clients
```

---

## Energy Forecast and Budget Optimization

The system uses an ensemble of four ML models trained on historical hourly kWh data:

- Random Forest Regressor
- XGBoost Regressor
- Multi-Layer Perceptron (MLP)
- Linear Regression

Each model predicts the next 24 to 72 hours of energy consumption. Predictions are blended using a weighted average based on each model's validation R2 score.

When a user sets a monthly budget:

1. The forecast estimates total kWh and electricity bill for the remaining days of the month.
2. If the projected bill exceeds the budget, the optimizer calculates the required kWh reduction.
3. The optimizer analyzes each device's usage profile from `plug_consumption_profiles` and generates a set of `recommendation_actions` such as:
   - Moving usage from peak hours to off-peak hours
   - Shortening runtime blocks
   - Turning off non-critical devices during high-tariff windows
   - Delaying device start times
4. Approved recommendations are automatically converted into scheduled ON/OFF commands in the `schedules` table.
5. The background schedule executor applies these commands at the designated times, logging each execution in `schedule_execution_log`.

---

## AI Chatbot

The chatbot is built on the Google Gemini API (google-genai >= 1.0). It is integrated into the dashboard as a persistent sidebar.

Capabilities:

- List and query device status and energy data
- Execute control commands via natural language, for example: "Turn off the bedroom plug"
- Summarize energy usage and budget status
- Explain optimization recommendations in plain language
- Broadcast device state changes to all connected Socket.IO clients when commands are executed via chat

The chatbot has full tool access to the same backend API functions used by the REST endpoints, ensuring consistency between chat-driven and UI-driven actions.

---

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature-name`
3. Commit your changes: `git commit -m "feat: add your feature"`
4. Push to the branch: `git push origin feature/your-feature-name`
5. Open a Pull Request

Please follow existing code style and keep commit messages concise.
