"""stop.py - used by STOP.bat. Stops the app and both AI engines if they are running."""
from . import engine

if __name__ == "__main__":
    engine.kill_leftover_engines(roles=("chat", "embed", "ui"))
    print("QuantaKai and its AI engines have been stopped.")
