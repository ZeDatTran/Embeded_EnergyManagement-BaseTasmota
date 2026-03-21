import joblib
from pathlib import Path

try:
	from .ensemble_model import ModelEnsemble
except ImportError:
	from ensemble_model import ModelEnsemble


ROOT_DIR = Path(__file__).resolve().parent.parent
ENSEMBLE_PATH = ROOT_DIR / "ensemble_model.pkl"

print("Đang tạo file ensemble_model.pkl...")
model = ModelEnsemble()
joblib.dump(model, ENSEMBLE_PATH)
print("Đã tạo ensemble_model.pkl thành công.")