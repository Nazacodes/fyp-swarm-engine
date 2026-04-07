#!/usr/bin/env python
"""Generate 10 config files with mixed starting temperatures."""

import json
import os

# Create 10 config files with varied starting temperatures
target_temp = 22.0

# Mix: cold, medium, hot spread across first 10 nodes
start_temps = [
    12.0,   # node1 - cold
    14.0,   # node2 - cold
    18.0,   # node3 - cool
    20.0,   # node4 - near target
    21.5,   # node5 - near target
    22.0,   # node6 - at target
    23.5,   # node7 - above target
    26.0,   # node8 - warm
    30.0,   # node9 - hot
    34.0,   # node10 - very hot
]

for i, start_temp in enumerate(start_temps, 1):
    node_id = f"node{i}"
    config = {
        "node_id": node_id,
        "rabbit_host": "localhost",
        "rabbit_user": "guest",
        "rabbit_password": "guest",
        "target_temp": target_temp,
        "has_sensor": False,
        "start_temp": start_temp
    }
    
    filename = f"config_node{i}.json"
    filepath = os.path.join(".", filename)
    
    with open(filepath, 'w') as f:
        json.dump(config, f, indent=2)
    
    print(f"Created {filename} with start_temp={start_temp:.1f}°C")

print(f"\nCreated {len(start_temps)} config files with mixed temperatures")
