import joblib
import numpy as np
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
MODELS_DIR = ROOT_DIR / "models"

class ModelEnsemble:
    def __init__(self):
        # Load các mô hình phù hợp
        self.rf_model = joblib.load(MODELS_DIR / "model_rf.pkl")
        self.xgb_model = joblib.load(MODELS_DIR / "model_xgb.pkl")
        self.mlp_model = joblib.load(MODELS_DIR / "model_mlp.pkl")
        
        # [OPTIONAL] Vẫn load LR để backward compatible
        try:
            self.lr_model = joblib.load(MODELS_DIR / "model_lr.pkl")
            self.has_lr = True
        except:
            self.has_lr = False
        
        # [FIX] CHỈ dùng 3 models tốt nhất, loại bỏ LinearRegression
        self.model_scores = {
            "XGBoost": 1.00,       # Tốt nhất cho time series
            "RandomForest": 0.95,  # Rất ổn định
            "MLP": 0.70,           # Có thể học non-linear nhưng cần cẩn thận
        }
        
        self.outlier_threshold = 1.5  # Giảm từ 2.0 xuống 1.5 để strict hơn

    def predict_all(self, input_data):
        """Dự đoán từ các mô hình tốt"""
        preds = {
            "RandomForest": self.rf_model.predict(input_data)[0],
            "XGBoost": self.xgb_model.predict(input_data)[0],
            "MLP": self.mlp_model.predict(input_data)[0],
        }
        
        # [OPTIONAL] Thêm LR chỉ để so sánh (không tham gia ensemble)
        if self.has_lr:
            preds["LinearRegression"] = self.lr_model.predict(input_data)[0]
        
        preds = {model: float(round(value, 4)) for model, value in preds.items()}
        return preds

    def predict_best(self, input_data):
        """
        Weighted average CHỈ với 3 models tốt (loại bỏ LR)
        """
        all_preds = self.predict_all(input_data)
        
        # CHỈ lấy predictions từ models trong ensemble
        preds = {k: v for k, v in all_preds.items() if k in self.model_scores}
        
        # Outlier detection
        values = list(preds.values())
        median_pred = np.median(values)
        
        adjusted_scores = {}
        for model, pred_value in preds.items():
            base_score = self.model_scores[model]
            
            if median_pred > 0.1:
                deviation_ratio = abs(pred_value - median_pred) / median_pred
                if deviation_ratio > self.outlier_threshold:
                    adjusted_scores[model] = base_score * 0.4  # Penalty mạnh hơn
                else:
                    adjusted_scores[model] = base_score
            else:
                adjusted_scores[model] = base_score
        
        # Weighted average
        total_score = sum(adjusted_scores.values())
        weighted_sum = sum(preds[model] * adjusted_scores[model] for model in preds)
        weighted_avg = weighted_sum / total_score
        
        # Không âm
        weighted_avg = max(0, weighted_avg)
        
        # Smoothing cho giá trị thấp
        if max(values) < 0.3:
            weighted_avg = min(weighted_avg, 0.25)
        
        weighted_avg = float(round(weighted_avg, 4))
        
        # Return all predictions để log (bao gồm cả LR nếu có)
        return weighted_avg, all_preds

    def predict_robust(self, input_data):
        """
        Robust prediction: Median của XGBoost + RandomForest
        (Loại bỏ hoàn toàn MLP nếu nó là outlier)
        """
        all_preds = self.predict_all(input_data)
        preds = {k: v for k, v in all_preds.items() if k in self.model_scores}
        
        # Tính median và MAD (Median Absolute Deviation)
        values = list(preds.values())
        median_val = np.median(values)
        mad = np.median([abs(v - median_val) for v in values])
        
        # Chỉ lấy các predictions không phải outlier
        threshold = 1.5 * mad if mad > 0 else 0.5
        filtered_preds = [v for v in values if abs(v - median_val) <= threshold]
        
        # Nếu filter quá nhiều, ít nhất giữ lại 2 models tốt nhất
        if len(filtered_preds) < 2:
            sorted_by_score = sorted(preds.items(), key=lambda x: self.model_scores[x[0]], reverse=True)
            filtered_preds = [sorted_by_score[0][1], sorted_by_score[1][1]]
        
        robust_prediction = float(round(np.median(filtered_preds), 4))
        
        return robust_prediction, all_preds

    def predict_conservative(self, input_data):
        """
        [UPDATED] Conservative prediction: Chỉ dùng XGBoost + RandomForest
        Trọng số ĐỘNG dựa trên hiệu suất thực tế (self.model_scores)
        """
        all_preds = self.predict_all(input_data)
        
        xgb_pred = all_preds["XGBoost"]
        rf_pred = all_preds["RandomForest"]
        
        # 1. Lấy điểm số hiện tại (được cập nhật qua feedback)
        score_xgb = self.model_scores.get("XGBoost", 1.0)
        score_rf = self.model_scores.get("RandomForest", 0.95)
        
        # 2. Tính tổng để chuẩn hóa trọng số
        total_score = score_xgb + score_rf
        
        # Tránh lỗi chia cho 0 (dù khó xảy ra vì min score là 0.3)
        if total_score == 0:
            weight_xgb = 0.55
            weight_rf = 0.45
        else:
            weight_xgb = score_xgb / total_score
            weight_rf = score_rf / total_score
            
        # 3. Tính Weighted Average
        conservative_pred = (xgb_pred * weight_xgb + rf_pred * weight_rf)
        
        # Log tỉ lệ để debug (có thể bỏ đi khi chạy prod)
        # print(f"Weights used -> XGB: {weight_xgb:.2f}, RF: {weight_rf:.2f}")
        
        conservative_pred = float(round(max(0, conservative_pred), 4))
        
        return conservative_pred, all_preds

    def update_scores(self, predicted_details, actual_value):
        """
        Cập nhật scores CHỈ cho models trong ensemble
        LinearRegression bị bỏ qua
        """
        errors = {}
        for model_name, predicted_value in predicted_details.items():
            # Chỉ update models trong ensemble
            if model_name not in self.model_scores:
                continue
                
            abs_error = abs(predicted_value - actual_value)
            if actual_value > 0.01:
                pct_error = abs_error / actual_value
            else:
                pct_error = abs_error
            errors[model_name] = pct_error

        if not errors:
            return
            
        sorted_models = sorted(errors.items(), key=lambda x: x[1])
        
        # Learning rate nhỏ hơn vì chỉ còn 3 models
        score_changes = [0.003, 0.001, -0.002]
        
        for idx, (model_name, error) in enumerate(sorted_models):
            change = score_changes[idx] if idx < len(score_changes) else score_changes[-1]
            
            # Bonus/Penalty
            if error < 0.05:
                change += 0.002
            if error > 0.5:
                change -= 0.003
            
            new_score = self.model_scores[model_name] + change
            self.model_scores[model_name] = round(max(0.3, min(1.0, new_score)), 4)

        print(f"📊 Updated scores (best: {min(errors.values()):.1%}, worst: {max(errors.values()):.1%})")
        print(f"   XGB: {self.model_scores['XGBoost']:.3f} | "
              f"RF: {self.model_scores['RandomForest']:.3f} | "
              f"MLP: {self.model_scores['MLP']:.3f}")