import sys, os
from pathlib import Path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))
import numpy as np

from ml.train_improved_models import load_data_for_training, create_advanced_features

df = load_data_for_training()
print("Raw points:", len(df))
print("Non-zero rows:", (df['kwh_hour'] > 0).sum())
print("Zero rows:", (df['kwh_hour'] == 0).sum())
print("Min:", df['kwh_hour'].min(), "Max:", df['kwh_hour'].max(), "Mean:", df['kwh_hour'].mean().round(4))

df_feat = create_advanced_features(df)
print("After feature engineering:", len(df_feat), "rows")
print("n_hours >= 500?", len(df) >= 500)
# Show the gap between raw and after-features
print("Lost rows:", len(df) - len(df_feat))
# Check NaN counts per column
nan_cols = df_feat.isna().sum()
print("NaN counts:\n", nan_cols[nan_cols > 0])
