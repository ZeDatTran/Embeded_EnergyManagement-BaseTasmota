import joblib
import numpy as np
import pandas as pd
from pathlib import Path
from typing import Dict, List


ROOT_DIR = Path(__file__).resolve().parent.parent
MODELS_DIR = ROOT_DIR / "models"


class ImprovedModelEnsemble:
    
    def __init__(self, use_improved=True):
        self.use_improved = use_improved
        
        if use_improved:
            model_suffix = "_improved"
            print(" Loading IMPROVED models with advanced features...")
        else:
            model_suffix = ""
            print(" Loading original models...")
        
        self.rf_model = None
        self.xgb_model = None
        self.cat_model = None

        load_errors = []
        optional_missing = []

        try:
            self.rf_model = joblib.load(MODELS_DIR / f"model_rf{model_suffix}.pkl")
        except Exception as e:
            load_errors.append(f"RandomForest: {e}")

        try:
            self.xgb_model = joblib.load(MODELS_DIR / f"model_xgb{model_suffix}.pkl")
        except Exception as e:
            load_errors.append(f"XGBoost: {e}")

        try:
            self.cat_model = joblib.load(MODELS_DIR / f"model_cat{model_suffix}.pkl")
        except FileNotFoundError:
            optional_missing.append("CatBoost")
        except Exception as e:
            load_errors.append(f"CatBoost: {e}")

        if optional_missing:
            print(f" Optional models not loaded: {', '.join(optional_missing)}")

        if load_errors:
            print("⚠️  Some models could not be loaded:")
            for err in load_errors:
                print(f"   - {err}")

        if not any([self.rf_model, self.xgb_model, self.cat_model]):
            raise FileNotFoundError("No usable improved models could be loaded")

        print(" Improved ensemble initialized")
        
        # Dynamic weights - can be adjusted based on recent performance
        self.model_weights = {
            "XGBoost": 0.40,
            "RandomForest": 0.35,
            "CatBoost": 0.25,
        }
        
        # Recent predictions history for adaptive tuning
        self.recent_predictions = []
        self.max_history = 100
        
        # Anomaly detection threshold
        self.outlier_threshold = 2.0  # Standard deviations

    def predict_all(self, input_data) -> Dict[str, float]:
        preds = {}

        if self.xgb_model is not None:
            preds["XGBoost"] = float(self.xgb_model.predict(input_data)[0])
        if self.rf_model is not None:
            preds["RandomForest"] = float(self.rf_model.predict(input_data)[0])
        if self.cat_model is not None:
            preds["CatBoost"] = float(self.cat_model.predict(input_data)[0])

        if not preds:
            raise RuntimeError("No available model for prediction")
        
        # Validate predictions (should be positive)
        for model_name, value in preds.items():
            if value < 0:
                print(f"⚠️  {model_name} predicted negative value: {value:.4f} -> clipped to 0.1")
                preds[model_name] = 0.1
        
        return preds

    def detect_outliers(self, predictions: Dict[str, float]) -> Dict[str, bool]:
        values = np.array(list(predictions.values()))
        median = np.median(values)
        mad = np.median(np.abs(values - median))
        
        outliers = {}
        for model_name, value in predictions.items():
            # Use modified Z-score
            if mad > 0:
                modified_z_score = 0.6745 * (value - median) / mad
                outliers[model_name] = abs(modified_z_score) > self.outlier_threshold
            else:
                outliers[model_name] = False
        
        return outliers

    def predict_ensemble(self, input_data, method='weighted_average') -> Dict:
        preds = self.predict_all(input_data)
        outliers = self.detect_outliers(preds)
        
        result = {
            "individual_predictions": preds,
            "outliers_detected": outliers,
        }
        
        if method == 'weighted_average':
            # Filter out detected outliers
            valid_preds = {k: v for k, v in preds.items() if not outliers[k]}
            
            if not valid_preds:
                # If all are outliers, use all anyway
                valid_preds = preds
                result["warning"] = "All predictions detected as outliers - using all models"
            
            # Weighted average
            total_weight = sum(self.model_weights.get(k, 0) for k in valid_preds.keys())
            if total_weight == 0:
                ensemble_pred = np.mean(list(valid_preds.values()))
            else:
                ensemble_pred = sum(
                    valid_preds[k] * self.model_weights.get(k, 0)
                    for k in valid_preds.keys()
                ) / total_weight
        
        elif method == 'median':
            # Robust to outliers
            ensemble_pred = np.median(list(preds.values()))
        
        elif method == 'trimmed_mean':
            # Remove high and low outliers, then average
            values = sorted(preds.values())
            trimmed = values[1:-1] if len(values) > 2 else values
            ensemble_pred = np.mean(trimmed)
        
        else:
            raise ValueError(f"Unknown method: {method}")
        
        result["ensemble_prediction"] = round(ensemble_pred, 4)
        result["method"] = method
        
        return result

    def predict_with_confidence(self, input_data) -> Dict:
        preds = self.predict_all(input_data)
        values = np.array(list(preds.values()))
        
        ensemble_result = self.predict_ensemble(input_data)
        ensemble_pred = ensemble_result["ensemble_prediction"]
        
        # Calculate standard deviation and confidence interval
        std_dev = np.std(values)
        cv = std_dev / (ensemble_pred + 0.001)  # Coefficient of variation
        
        result = {
            **ensemble_result,
            "standard_deviation": round(std_dev, 4),
            "coefficient_of_variation": round(cv, 4),
            "confidence_low_95": round(max(0.1, ensemble_pred - 1.96 * std_dev), 4),
            "confidence_high_95": round(ensemble_pred + 1.96 * std_dev, 4),
        }
        
        # Confidence level assessment
        if cv < 0.1:
            result["confidence_level"] = "Very High"
        elif cv < 0.15:
            result["confidence_level"] = "High"
        elif cv < 0.25:
            result["confidence_level"] = "Medium"
        else:
            result["confidence_level"] = "Low"
        
        return result

    def predict_next_hours(self, input_data_list: List) -> List[Dict]:
        predictions = []
        for i, input_data in enumerate(input_data_list):
            pred = self.predict_with_confidence(input_data)
            pred["hour_ahead"] = i + 1
            predictions.append(pred)
        
        return predictions

    def update_adaptive_weights(self, actual_values: List[float], predictions: List[Dict]):
        if len(predictions) == 0:
            return
        
        active_models = [k for k in ["XGBoost", "RandomForest", "CatBoost"] if k in self.model_weights]
        individual_errors = {name: [] for name in active_models}
        
        for actual, pred_dict in zip(actual_values, predictions):
            preds = pred_dict["individual_predictions"]
            for model_name, pred_value in preds.items():
                if model_name not in individual_errors:
                    continue
                error = abs(actual - pred_value)
                individual_errors[model_name].append(error)
        
        # Calculate average errors
        avg_errors = {k: np.mean(v) for k, v in individual_errors.items() if len(v) > 0}
        if not avg_errors:
            return
        total_error = sum(avg_errors.values())
        
        if total_error > 0:
            # Update weights inversely proportional to error
            model_count = len(avg_errors)
            for model_name in list(self.model_weights.keys()):
                if model_name not in avg_errors:
                    continue
                weight = (total_error - avg_errors[model_name]) / (model_count * total_error)
                self.model_weights[model_name] = max(0.1, min(0.7, weight))
            
            # Normalize weights
            total_weight = sum(self.model_weights.values())
            for model_name in self.model_weights.keys():
                self.model_weights[model_name] /= total_weight
            
            print(f" Weights updated based on recent accuracy:")
            for model_name, weight in self.model_weights.items():
                print(f"   {model_name}: {weight:.3f}")


def demo_improved_ensemble():
    """Demo the improved ensemble"""
    print("="*70)
    print(" IMPROVED ENSEMBLE MODEL DEMO")
    print("="*70)
    
    ensemble = ImprovedModelEnsemble(use_improved=True)
    
    # Create dummy input (would be real scaled features in production)
    dummy_input = np.random.randn(1, 34)  # 34 features from improved model
    
    print("\n Getting predictions...")
    result = ensemble.predict_with_confidence(dummy_input)
    
    print("\n" + "-"*70)
    print("Individual Predictions:")
    for model_name, pred in result["individual_predictions"].items():
        is_outlier = result["outliers_detected"][model_name]
        outlier_marker = "  OUTLIER" if is_outlier else ""
        print(f"  {model_name:<15}: {pred:>7.4f} kWh{outlier_marker}")
    
    print("\n" + "-"*70)
    print("Ensemble Result:")
    print(f"  Prediction:             {result['ensemble_prediction']:>7.4f} kWh")
    print(f"  Std Deviation:          {result['standard_deviation']:>7.4f}")
    print(f"  Confidence Level:       {result['confidence_level']}")
    print(f"  95% CI: [{result['confidence_low_95']:.4f}, {result['confidence_high_95']:.4f}]")
    
    print("\n Ensemble ready for production!")


if __name__ == "__main__":
    demo_improved_ensemble()
