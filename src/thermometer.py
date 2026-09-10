import random
import time
from datetime import datetime

# Initial temperature (°C)
temperature = 22.0

while True:
    # Simulate small temperature changes
    temperature += random.uniform(-0.5, 0.5)

    # Limit temperature range
    temperature = max(15, min(35, temperature))

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    print(f"[{timestamp}] Temperature: {temperature:.1f} °C")

    # Wait 1 minute
    time.sleep(60)
    