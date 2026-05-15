import os
import sys
import numpy as np
import pandas as pd
import joblib
from pathlib import Path
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_squared_error, r2_score

# Thêm thư mục backend vào sys.path để có thể import từ train_improved_models
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from ml.train_improved_models import load_data_for_training, create_advanced_features

# Cấu hình đường dẫn
MODELS_DIR = ROOT_DIR / "models"
SCALER_PATH = ROOT_DIR / "scaler_improved.pkl"
RESULTS_DIR = ROOT_DIR / "evaluation_results"

try:
    import matplotlib.pyplot as plt
    import seaborn as sns
except ImportError:
    print("Vui lòng cài đặt matplotlib và seaborn bằng lệnh: pip install matplotlib seaborn")
    sys.exit(1)

def evaluate_and_visualize():
    os.makedirs(RESULTS_DIR, exist_ok=True)

    print("Đang tải dữ liệu...")
    df = load_data_for_training()
    
    if df.empty or len(df) < 5:
        print("Không có đủ dữ liệu để đánh giá.")
        return

    df_features = create_advanced_features(df)
    
    FEATURES = [
        col for col in df_features.columns
        if col not in {'kwh_hour', 'kwh_detrended', 'time_idx', 'linear_trend', 'trend_slope'}
    ]
    TARGET = 'kwh_hour'

    X = df_features[FEATURES]
    y = df_features[TARGET]
    
    # Lấy index thời gian cho biểu đồ
    time_index = df_features.index

    print("Đang tải scaler...")
    if not SCALER_PATH.exists():
        print(f"Không tìm thấy scaler tại {SCALER_PATH}. Vui lòng huấn luyện mô hình trước.")
        return

    scaler = joblib.load(SCALER_PATH)
    X_scaled = scaler.transform(X)

    # Chia train/test giống như khi huấn luyện (test_size=0.15, shuffle=False)
    X_train, X_test, y_train, y_test = train_test_split(
        X_scaled, y, test_size=0.15, shuffle=False
    )
    
    # Chia time_index tương ứng để lấy thời gian cho tập test
    _, test_times = train_test_split(time_index, test_size=0.15, shuffle=False)

    print("Đang tải các mô hình...")
    models = {}
    model_names = ['xgb_improved', 'rf_improved', 'cat_improved']
    display_names = ['XGBoost', 'Random Forest', 'CatBoost']
    
    for name, display_name in zip(model_names, display_names):
        path = MODELS_DIR / f"model_{name}.pkl"
        if path.exists():
            models[display_name] = joblib.load(path)
        else:
            print(f"Cảnh báo: Không tìm thấy mô hình {display_name} tại {path}")

    if not models:
        print("Không tìm thấy mô hình nào để đánh giá.")
        return

    scores = []
    predictions = {}

    print("Đang đánh giá và dự đoán...")
    for name, model in models.items():
        y_pred = model.predict(X_test)
        
        # Đảm bảo không có dự đoán âm
        y_pred = np.maximum(y_pred, 0)
        
        predictions[name] = y_pred
        
        r2 = r2_score(y_test, y_pred)
        rmse = np.sqrt(mean_squared_error(y_test, y_pred))
        
        scores.append({
            'Model': name,
            'R2 Score': r2,
            'RMSE': rmse
        })

    df_scores = pd.DataFrame(scores)
    
    # ==========================================
    # CHART 1: MODEL COMPARISON
    # ==========================================
    print("Drawing model comparison chart...")
    
    # Set modern style
    sns.set_theme(style="whitegrid", palette="muted")
    
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    
    # Bar chart for R2
    sns.barplot(x='Model', y='R2 Score', data=df_scores, hue='Model', palette='viridis', legend=False, ax=axes[0])
    axes[0].set_title('R² Score Comparison (Higher is better)', fontsize=14, fontweight='bold')
    
    r2_min = df_scores['R2 Score'].min()
    r2_max = df_scores['R2 Score'].max()
    axes[0].set_ylim(min(0, r2_min - 0.1), max(1.0, r2_max + 0.1))
    
    axes[0].set_xlabel('')
    axes[0].set_ylabel('R² Score', fontsize=12)
    
    # Draw a horizontal line at y=0 for better visibility of negative values
    axes[0].axhline(0, color='black', linewidth=1.2, alpha=0.5)
    
    for index, row in df_scores.iterrows():
        r2_val = row['R2 Score']
        y_pos = r2_val + 0.02 if r2_val >= 0 else r2_val - 0.02
        va = 'bottom' if r2_val >= 0 else 'top'
        axes[0].text(index, y_pos, f"{r2_val:.4f}", color='black', ha="center", va=va, fontsize=11)

    # Bar chart for RMSE
    sns.barplot(x='Model', y='RMSE', data=df_scores, hue='Model', palette='magma', legend=False, ax=axes[1])
    axes[1].set_title('RMSE Comparison (Lower is better)', fontsize=14, fontweight='bold')
    axes[1].set_xlabel('')
    axes[1].set_ylabel('RMSE (kWh)', fontsize=12)
    for index, row in df_scores.iterrows():
        axes[1].text(index, row['RMSE'] + (0.02 * df_scores['RMSE'].max()), f"{row['RMSE']:.4f}", color='black', ha="center", fontsize=11)
    
    plt.tight_layout()
    comp_path = RESULTS_DIR / "model_comparison.png"
    plt.savefig(comp_path, dpi=300, bbox_inches='tight')
    print(f"  -> Saved model comparison chart at: {comp_path}")
    plt.close()

    # ==========================================
    # CHART 2: PREDICTION OVER TIME (COMBINED)
    # ==========================================
    print("Drawing prediction over time chart...")
    
    # Use the last 168 hours (1 week)
    plot_len = min(168, len(y_test))
    x_times = test_times[-plot_len:]
    y_actual = y_test.values[-plot_len:]
    
    plt.figure(figsize=(16, 7))
    plt.plot(x_times, y_actual, label='Actual Energy', color='black', linewidth=2.5, linestyle='solid')
    
    colors = ['royalblue', 'forestgreen', 'crimson']
    for idx, (name, y_pred) in enumerate(predictions.items()):
        plt.plot(x_times, y_pred[-plot_len:], label=f'Predicted ({name})', color=colors[idx % len(colors)], linewidth=2, alpha=0.8, linestyle='--')
    
    plt.title(f'Actual vs Predicted Energy Consumption ({plot_len} hours)', fontsize=14, fontweight='bold')
    plt.xlabel('Time', fontsize=12)
    plt.ylabel('Energy (kWh)', fontsize=12)
    plt.legend(fontsize=11)
    plt.grid(True, alpha=0.4)
    plt.xticks(rotation=45)
    
    plt.tight_layout()
    pred_path = RESULTS_DIR / "prediction_over_time.png"
    plt.savefig(pred_path, dpi=300, bbox_inches='tight')
    print(f"  -> Saved prediction over time chart at: {pred_path}")
    plt.close()

    # ==========================================
    # CHART 3: SCATTER PLOT (ACTUAL VS PREDICTED FOR ALL MODELS)
    # ==========================================
    print("Drawing actual vs predicted scatter plots...")
    
    fig, axes = plt.subplots(1, 3, figsize=(18, 6), sharey=True)
    
    for idx, (name, y_pred) in enumerate(predictions.items()):
        ax = axes[idx]
        ax.scatter(y_test, y_pred, alpha=0.4, color=colors[idx], edgecolor='w', s=50)
        
        # Ideal line y=x
        max_val = max(max(y_test), max(y_pred))
        min_val = min(min(y_test), min(y_pred))
        ax.plot([min_val, max_val], [min_val, max_val], 'k--', linewidth=2, label='Ideal Fit')
        
        # Calculate R2 for the subtitle
        model_r2 = df_scores[df_scores['Model'] == name]['R2 Score'].values[0]
        
        ax.set_title(f'{name} (R² = {model_r2:.4f})', fontsize=13, fontweight='bold')
        ax.set_xlabel('Actual Energy (kWh)', fontsize=11)
        if idx == 0:
            ax.set_ylabel('Predicted Energy (kWh)', fontsize=11)
        ax.legend(loc='upper left')
        ax.grid(True, alpha=0.4)
    
    plt.suptitle('Actual vs Predicted Scatter Comparison', fontsize=16, fontweight='bold', y=1.02)
    plt.tight_layout()
    
    scatter_path = RESULTS_DIR / "actual_vs_predicted_scatter.png"
    plt.savefig(scatter_path, dpi=300, bbox_inches='tight')
    print(f"  -> Saved scatter plot at: {scatter_path}")
    plt.close()

    print("\nHoàn tất việc xuất hình ảnh kết quả đánh giá!")
    print(f"Tất cả hình ảnh đã được lưu vào thư mục: {RESULTS_DIR}")

if __name__ == "__main__":
    evaluate_and_visualize()
