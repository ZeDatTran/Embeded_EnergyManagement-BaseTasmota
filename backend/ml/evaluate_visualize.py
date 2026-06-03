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

def evaluate_and_visualize(start_date: str = '2026-05-07'):
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
    all_predictions = {}

    print("Dang danh gia va du doan...")
    for name, model in models.items():
        # Predict on the FULL dataset so we can plot from any start date
        y_pred_all = model.predict(X_scaled)
        y_pred_all = np.maximum(y_pred_all, 0)
        all_predictions[name] = y_pred_all

        # Metrics on test set only
        y_pred_test = y_pred_all[len(X_train):]
        r2   = r2_score(y_test, y_pred_test)
        rmse = np.sqrt(mean_squared_error(y_test, y_pred_test))
        scores.append({'Model': name, 'R2 Score': r2, 'RMSE': rmse})

    # Keep separate test predictions for scatter chart
    predictions = {name: v[len(X_train):] for name, v in all_predictions.items()}

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
    # CHART 2: PREDICTION OVER TIME (from start_date)
    # ==========================================
    print("Ve bieu do Prediction Over Time...")

    # Build full-dataset arrays
    all_times  = time_index
    all_actual = y.values

    # Filter from start_date
    start_ts = pd.Timestamp(start_date)
    mask     = all_times >= start_ts

    x_times_full  = all_times[mask]
    y_actual_full = all_actual[mask]

    if len(x_times_full) == 0:
        print(f"  Khong co du lieu tu {start_date}, bo qua Chart 2.")
    else:
        # Index of train/test boundary in the full time_index array
        n_train = len(X_train)
        train_end_time = all_times[n_train - 1]  # last training timestamp

        plt.figure(figsize=(18, 7))

        # Actual energy
        plt.plot(x_times_full, y_actual_full,
                 label='Actual Energy', color='black', linewidth=2, linestyle='solid')

        colors = ['royalblue', 'forestgreen', 'crimson']
        for idx, (name, y_pred_all) in enumerate(all_predictions.items()):
            y_pred_filtered = y_pred_all[mask]
            plt.plot(x_times_full, y_pred_filtered,
                     label=f'Predicted ({name})',
                     color=colors[idx % len(colors)],
                     linewidth=1.8, alpha=0.8, linestyle='--')

        # Vertical line marking train/test split
        if start_ts <= train_end_time:
            plt.axvline(x=train_end_time, color='gray', linewidth=1.5,
                        linestyle=':', alpha=0.9, label=f'Train/Test split ({train_end_time.strftime("%m-%d %H:%M")})')
            plt.axvspan(all_times[mask][0], train_end_time,
                        alpha=0.04, color='gray', label='_nolegend_')

        date_from = x_times_full[0].strftime('%d/%m/%Y')
        date_to   = x_times_full[-1].strftime('%d/%m/%Y')
        plt.title(f'Actual vs Predicted Energy Consumption\n({date_from} - {date_to}, {len(x_times_full)} hours)',
                  fontsize=14, fontweight='bold')
        plt.xlabel('Time', fontsize=12)
        plt.ylabel('Energy (kWh)', fontsize=12)
        plt.legend(fontsize=10)
        plt.grid(True, alpha=0.4)
        plt.xticks(rotation=45)

        plt.tight_layout()
        pred_path = RESULTS_DIR / "prediction_over_time.png"
        plt.savefig(pred_path, dpi=300, bbox_inches='tight')
        print(f"  -> Saved: {pred_path}")
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

def evaluate_realtime_predictions():
    """
    So sánh dữ liệu dự đoán (user_forecast) và dữ liệu thực tế (hourly_kwh/plug_hourly_energy)
    từ lúc dự đoán cho tới hiện tại (lấy từ MongoDB).
    """
    from db_connection import get_db
    
    os.makedirs(RESULTS_DIR, exist_ok=True)
    db = get_db()
    
    print("Đang tải dữ liệu dự đoán từ MongoDB (user_forecasts)...")
    forecast = db.user_forecasts.find_one()
    if not forecast or "PredictedHourlyDetails" not in forecast:
        print("Không tìm thấy dữ liệu dự đoán trong MongoDB. Vui lòng chạy dự báo trước.")
        return
        
    predictions = forecast["PredictedHourlyDetails"]
    
    print("Đang tải dữ liệu thực tế từ MongoDB (hourly_kwh / plug_hourly_energy)...")
    # Ưu tiên lấy từ hourly_kwh (dữ liệu tổng hợp)
    actual_hourly = db.hourly_kwh.find()
    actual_by_hour = {doc["timestamp"]: doc["kwh"] for doc in actual_hourly}
    
    # Nếu hourly_kwh không có dữ liệu cho các giờ này, thử lấy từ plug_hourly_energy
    if len(actual_by_hour) < 10:
        print("Dữ liệu hourly_kwh ít, đang lấy từ plug_hourly_energy...")
        actuals = db.plug_hourly_energy.find()
        for doc in actuals:
            hr = doc["hour_bucket"]
            actual_by_hour[hr] = actual_by_hour.get(hr, 0) + doc.get("energy_kwh", 0)

    # Khớp dữ liệu
    matched_times = []
    actual_values = []
    pred_xgb = []
    pred_rf = []
    pred_cat = []
    
    # Lấy các mốc thời gian có cả dự đoán và thực tế
    for hr in sorted(predictions.keys()):
        if hr in actual_by_hour:
            matched_times.append(hr)
            actual_values.append(actual_by_hour[hr])
            pred_dict = predictions[hr]
            pred_xgb.append(pred_dict.get('XGBoost', 0))
            pred_rf.append(pred_dict.get('RandomForest', 0))
            pred_cat.append(pred_dict.get('CatBoost', 0))
            
    if not matched_times:
        print("Không có mốc thời gian nào trùng khớp giữa dự đoán và thực tế.")
        return
        
    print(f"Đã tìm thấy {len(matched_times)} giờ có cả dữ liệu dự đoán và thực tế.")
    
    # Tính toán các chỉ số
    print("\nKết quả Đánh giá Realtime (Thực tế vs Dự đoán):")
    models_pred = {'XGBoost': pred_xgb, 'Random Forest': pred_rf, 'CatBoost': pred_cat}
    
    for name, y_pred in models_pred.items():
        if len(y_pred) > 1:
            r2 = r2_score(actual_values, y_pred)
            rmse = np.sqrt(mean_squared_error(actual_values, y_pred))
            print(f"- {name}: R² = {r2:.4f}, RMSE = {rmse:.4f}")
        else:
            print(f"- {name}: Không đủ điểm dữ liệu để tính R².")
            
    # Vẽ biểu đồ So sánh Thực tế vs Dự đoán theo thời gian
    print("Đang vẽ biểu đồ So sánh Realtime...")
    plt.figure(figsize=(14, 7))
    
    # Giới hạn hiển thị 168 giờ (1 tuần) gần nhất nếu quá nhiều
    plot_len = min(168, len(matched_times))
    x_times = matched_times[-plot_len:]
    y_act = actual_values[-plot_len:]
    
    # Xoay nhãn thời gian cho dễ nhìn
    x_labels = [t[5:13].replace('T', ' ') for t in x_times] # Hiển thị MM-DD HH
    
    plt.plot(x_labels, y_act, label='Thực tế (CoreIoT)', color='black', linewidth=2.5, marker='o')
    
    colors = {'XGBoost': 'royalblue', 'Random Forest': 'forestgreen', 'CatBoost': 'crimson'}
    for name, y_pred in models_pred.items():
        plt.plot(x_labels, y_pred[-plot_len:], label=f'Dự đoán ({name})', color=colors[name], linewidth=2, linestyle='--', marker='x', alpha=0.8)
        
    plt.title('So sánh Thực tế (CoreIoT) vs Dự đoán (MongoDB)', fontsize=15, fontweight='bold')
    plt.xlabel('Thời gian', fontsize=12)
    plt.ylabel('Điện năng (kWh)', fontsize=12)
    plt.legend(fontsize=11)
    plt.grid(True, alpha=0.4)
    plt.xticks(rotation=45)
    plt.tight_layout()
    
    realtime_path = RESULTS_DIR / "realtime_prediction_comparison.png"
    plt.savefig(realtime_path, dpi=300, bbox_inches='tight')
    print(f"  -> Đã lưu biểu đồ tại: {realtime_path}")
    plt.close()

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='Danh gia mo hinh du doan')
    parser.add_argument('--mode', type=str, choices=['offline', 'realtime', 'all'], default='all',
                        help='offline | realtime | all')
    parser.add_argument('--start-date', type=str, default='2026-05-07',
                        help='Ngay bat dau bieu do Chart 2, dinh dang YYYY-MM-DD (mac dinh: 2026-05-07)')
    args = parser.parse_args()

    if args.mode in ['offline', 'all']:
        print("=== DANH GIA TREN TAP TEST (OFFLINE) ===")
        evaluate_and_visualize(start_date=args.start_date)

    if args.mode in ['realtime', 'all']:
        print("\n=== DANH GIA VOI DU LIEU THUC TE TU COREIOT (REALTIME) ===")
        evaluate_realtime_predictions()

