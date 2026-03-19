# FYP Swarm Engine

A distributed temperature control system using swarm intelligence (ACO-inspired) with leader election, messaging via RabbitMQ, and a web monitor.

## Project Structure

```
fyp-swarm-engine/
├── docs/
│   └── README.md          # Comprehensive documentation
├── scripts/
│   ├── run.ps1            # Run single node (PowerShell)
│   ├── run.bat            # Run single node (CMD)
│   ├── run_swarm.ps1      # Run 2 nodes (PowerShell)
│   ├── run_swarm.bat      # Run 2 nodes (CMD)
│   ├── run_monitor.ps1    # Run web monitor (PowerShell)
│   ├── run_monitor.bat    # Run web monitor (CMD)
│   ├── run_visualize.ps1  # Run visualization (PowerShell)
│   ├── run_visualize.bat  # Run visualization (CMD)
│   ├── run_all.ps1        # Run complete demo (PowerShell)
│   └── run_all.bat        # Run complete demo (CMD)
├── src/
│   ├── config.py          # Configuration loader
│   ├── messaging.py       # RabbitMQ/in-memory messaging
│   ├── sensor_input.py    # Temperature sensor abstraction
│   ├── leader_election.py # Leader election logic
│   ├── aco.py             # ACO decision making
│   ├── node.py            # Main node runner
│   ├── web_monitor.py     # Flask web monitor with charts
│   └── test_rabbitmq.py   # RabbitMQ test utility
├── requirements.txt       # Python dependencies
└── LICENSE
```

## Features

- **Swarm Nodes**: Multiple nodes that simulate temperature sensors and decide heating/cooling actions.
- **Leader Election**: Automatic leader selection based on node priorities.
- **ACO Optimization**: Uses Ant Colony Optimization with **shared pheromone trails** for collaborative learning across the swarm.
- **Messaging**: RabbitMQ for inter-node communication (with in-memory fallback).
- **Web Monitor**: Real-time dashboard to view swarm state.
- **Configurable**: Via JSON config files or environment variables.

## Architecture

- `src/config.py`: Loads configuration from files/env vars.
- `src/messaging.py`: Handles RabbitMQ or in-memory messaging.
- `src/sensor_input.py`: Temperature sensor abstraction (mock or real hardware).
- `src/leader_election.py`: Leader election logic.
- `src/aco.py`: **ACO-based** decision making for temperature control (shared pheromone trails across swarm, probabilistic action selection).
- `src/node.py`: Main node runner.
- `src/web_monitor.py`: Flask web app for monitoring with real-time charts.
- `scripts/`: Run scripts for easy execution.
- `docs/`: Documentation.

## Prerequisites

- Python 3.8+
- RabbitMQ (for multi-node communication; optional, falls back to in-memory)

## Installation

1. Clone the repo:
   ```bash
   git clone https://github.com/Nazacodes/fyp-swarm-engine.git
   cd fyp-swarm-engine
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. (Optional) Install and start RabbitMQ:
   - Windows: Download from https://www.rabbitmq.com/install-windows.html
   - Or via Docker: `docker run -d --name rabbitmq -p 5672:5672 -p 15672:15672 rabbitmq:3-management`

## Configuration

Create a `config.json` file (optional; defaults are used otherwise):

```json
{
  "node_id": "node1",
  "rabbit_host": "localhost",
  "rabbit_user": "guest",
  "rabbit_password": "guest",
  "target_temp": 22.0,
  "has_sensor": false
}
```

Or set environment variables:
- `NODE_ID`
- `RABBIT_HOST`
- `RABBIT_USER`
- `RABBIT_PASSWORD`
- `TARGET_TEMP`
- `HAS_SENSOR`

## Usage

### Run a Single Node
```bash
python src/node.py --config config.json
```

Or use the script:
```powershell
# PowerShell
.\scripts\run.ps1 -Config config.json

# CMD
scripts\run.bat config.json
```

### Run Multiple Nodes (Swarm)
Use different `node_id` for each:

```powershell
# Terminal 1
python src/node.py

# Terminal 2
NODE_ID=node2 python src/node.py

# Terminal 3
NODE_ID=node3 python src/node.py
```

Or use the swarm launcher (starts 2 nodes):
```powershell
.\scripts\run_swarm.ps1
```

#### Adding More Nodes
To add more nodes to the swarm:
1. Open a new terminal.
2. Set a unique `NODE_ID` (e.g., `NODE_ID=node3`).
3. Run `python src/node.py`.
4. Repeat for as many nodes as needed.

All nodes will automatically join the same swarm via RabbitMQ and participate in leader election.

### Web Monitor
Run the monitor to view the swarm:
```powershell
.\scripts\run_monitor.ps1
```

Access at: http://localhost:5000

Includes:
- Real-time node states, leader, heartbeats.
- **Interactive charts** (/charts) showing temperatures, actions, and pheromone evolution.

To allow connections from other machines:
```powershell
.\scripts\run_monitor.ps1 -BindHost 0.0.0.0
```

Then access at: http://<server-ip>:5000

### Run Complete Demo
Launch everything at once (nodes, monitor, visualization):
```powershell
.\scripts\run_all.ps1 -Nodes 4
```

Defaults to 3 nodes + monitor + visualize. Customize with `-Nodes 5 -Monitor:$false` etc.

## Connecting from Remote Machines

To allow nodes or monitors from other machines:

1. **RabbitMQ**: Set `RABBIT_HOST` to the server's IP address in config/env vars.
   - Ensure RabbitMQ is bound to 0.0.0.0 (edit `rabbitmq.conf`: `listeners.tcp.default = 0.0.0.0:5672`)

2. **Web Monitor**: Run with `-BindHost 0.0.0.0` as above.

3. **Firewall**: Open ports 5672 (RabbitMQ), 5000 (web monitor) on the server.

## Development

- Run tests: `python -m pytest` (if you add tests)
- Lint: `python -m flake8`

## License

See LICENSE file.
