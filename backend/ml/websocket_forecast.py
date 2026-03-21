# websocket_forecast.py
import websocket
import json
import logging
import threading

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
        return cls._instance

    def connect(self):
        if self.ws and self.connected and self.ws.sock and self.ws.sock.fileno() != -1:
            return self.ws
            
        try:
            self.ws = websocket.WebSocket()
            self.ws.connect("ws://127.0.0.1:8080", timeout=30)
            self.connected = True
            logging.info("Connected to forecast server (8080)")
            return self.ws
        except Exception as e:
            logging.error(f"Forecast server connect failed: {e}")
            self.connected = False
            if self.ws:
                try:
                    self.ws.close()
                except:
                    pass
            self.ws = None
            return None

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
            ws.settimeout(30)
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