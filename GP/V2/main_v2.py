import sys
from pathlib import Path

# Add project root to path so imports work
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.append(str(PROJECT_ROOT))

from src.viz.server import run_server

if __name__ == "__main__":
    print("Starting OS City V2...")
    print("Dashboard will be available at http://127.0.0.1:8050")
    run_server()

