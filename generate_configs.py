#!/usr/bin/env python
"""Generate 50 config files with varied starting temperatures."""

import json
import os

# Create 50 config files with varied starting temperatures
configs_dir = "."
target_temp = 22.0

# Cold nodes: 10-19°C (20 nodes)
cold_temps = [10.0 + i*0.5 for i in range(20)]

# Hot nodes: 25-35°C (20 nodes)  
hot_temps = [25.0 + i*0.5 for i in range(20)]

# Medium nodes: 20-24°C (10 nodes)
medium_temps = [20.0 + i*0.4 for i in range(10)]

all_temps = cold_temps + hot_temps + medium_temps

for i, start_temp in enumerate(all_temps, 1):
    node_id = f"node{i}"
    config = {
        "node_id": node_id,
        "rabbit_host": "localhost",
        "rabbit_user": "guest",
        "rabbit_password": "guest",
        "target_temp": target_temp,
        "has_sensor": False,
        "start_temp": round(start_temp, 1)
    }
    
    filename = f"config_node{i}.json"
    filepath = os.path.join(configs_dir, filename)
    
    with open(filepath, 'w') as f:
        json.dump(config, f, indent=2)
    
    print(f"Created {filename} with start_temp={start_temp:.1f}°C")

print(f"\nCreated {len(all_temps)} config files")
print(f"Cold nodes (10-19°C): {len(cold_temps)}")
print(f"Hot nodes (25-35°C): {len(hot_temps)}")
print(f"Medium nodes (20-24°C): {len(medium_temps)}")
