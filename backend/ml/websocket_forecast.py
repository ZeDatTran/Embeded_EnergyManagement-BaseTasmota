# websocket_forecast.py
import websocket
import json
import logging
import threading
import os

class ForecastClient:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance.ws = None
                    cls._instance.connected = False
                    cls._instance.response_timeout_sec = cls._instance._get_response_timeout()
        return cls._instance

    def _get_response_timeout(self):
        """Use longer, configurable timeout because ensemble forecast can be slow."""
        try:
            return max(30.0, float(os.getenv("FORECAST_RESPONSE_TIMEOUT_SEC", "90")))
        except (TypeError, ValueError):
            return 90.0

    def connect(self):
        if self.ws and self.connected and self.ws.sock and self.ws.sock.fileno() != -1:
            return self.ws

        server_url = self._resolve_server_url()

        try:
            self.ws = websocket.WebSocket()
            self.ws.connect(server_url, timeout=30)
            self.connected = True
            logging.info("Connected to forecast server: %s", server_url)
            return self.ws
        except Exception as e:
            logging.error("Forecast server connect failed (%s): %s", server_url, e)
            self.connected = False
            if self.ws:
                try:
                    self.ws.close()
                except Exception:
                    pass
            self.ws = None
            return None

    def _resolve_server_url(self):
        url = os.getenv("FORECAST_SERVER_URL")
        if url:
            return url

        host = os.getenv("FORECAST_SERVER_HOST", "127.0.0.1")
        port = os.getenv("FORECAST_SERVER_PORT", "8080")
        return f"ws://{host}:{port}"

    def predict(self, history_dict, consumed_this_month):
        ws = self.connect()
        if not ws: return None
        
        payload = {
            "Type": "PredictToEndOfMonth",
            "History": {k: float(v) for k, v in history_dict.items()},
            "ConsumedThisMonth": round(float(consumed_this_month), 4)
        }
        try:
            ws.send(json.dumps(payload))
            ws.settimeout(self.response_timeout_sec)
            resp = ws.recv()
            result = json.loads(resp)
            
            # Đóng connection sau khi nhận response
            self._close_connection()
            
            return result
        except Exception as e:
            logging.error(f"Predict error: {e}")
            self._close_connection()
            return None

    def send_feedback(self, predicted_details, actual_dict):
        ws = self.connect()
        if not ws: return False
        
        payload = {
            "Type": "Feedback",
            "PredictedDetails": predicted_details,
            "ActualKwh": {k: float(v) for k, v in actual_dict.items()}
        }
        try:
            ws.send(json.dumps(payload))
            ws.settimeout(10)
            ws.recv()
            
            # Đóng connection sau feedback
            self._close_connection()
            
            return True
        except Exception as e:
            logging.error(f"Feedback error: {e}")
            self._close_connection()
            return False

    def _close_connection(self):
        """Đóng connection"""
        self.connected = False
        if self.ws:
            try:
                self.ws.close()
            except:
                pass
            self.ws = None

forecast_client = ForecastClient()