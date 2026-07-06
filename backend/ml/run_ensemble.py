import joblib
from pathlib import Path

try:
	from .ensemble_model_improved import ImprovedModelEnsemble
except ImportError:
	from ensemble_model_improved import ImprovedModelEnsemble


ROOT_DIR = Path(__file__).resolve().parent.parent
ENSEMBLE_PATH = ROOT_DIR / "ensemble_model_improved.pkl"

print(f"Đang tạo file {ENSEMBLE_PATH.name}...")
model = ImprovedModelEnsemble(use_improved=True)
joblib.dump(model, ENSEMBLE_PATH)
print(f"Đã tạo {ENSEMBLE_PATH.name} thành công.")