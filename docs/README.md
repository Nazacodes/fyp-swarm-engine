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
│   ├── web_monitor.py     # Flask web monitor backend
│   ├── templates/         # Monitor HTML templates
│   ├── static/            # Monitor CSS assets
│   └── test_rabbitmq.py   # RabbitMQ test utility
├── requirements.txt       # Python dependencies
└── LICENSE
```

## Features

- **Swarm Nodes**: Multiple nodes that simulate temperature sensors and decide heating/cooling actions.
- **Leader Election**: Automatic leader selection based on node priorities.
- **Hierarchical Leaders**: One leader per group plus optional leader-council communication across groups.
- **ACO Optimization**: Uses Ant Colony Optimization with **shared pheromone trails** for collaborative learning across the swarm.
- **Messaging**: RabbitMQ for inter-node communication (with in-memory fallback).
- **Web Monitor**: Real-time dashboard with overview + trends pages.
- **Configurable**: Via JSON config files or environment variables.

## Architecture

- `src/config.py`: Loads configuration from files/env vars.
- `src/messaging.py`: Handles RabbitMQ or in-memory messaging.
- `src/sensor_input.py`: Temperature sensor abstraction (mock or real hardware).
- `src/leader_election.py`: Leader election logic.
- `src/aco.py`: **ACO-based** decision making for temperature control (shared pheromone trails across swarm, probabilistic action selection).
- `src/node.py`: Main node runner.
- `src/web_monitor.py`: Flask web app for monitoring and trend charts.
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
  "group_id": "zone_a",
  "rabbit_host": "localhost",
  "rabbit_user": "guest",
  "rabbit_password": "guest",
  "target_temp": 22.0,
  "has_sensor": false,
  "peer_stale_seconds": 10.0,
  "target_bounds": {
    "min": 10.0,
    "max": 35.0
  },
  "monitor_max_points": 300,
  "leader_bus_topic": "swarm.temperature.leaders",
  "enable_leader_council": true,
  "leader_sync_interval": 1.0,
  "leader_signal_stale_seconds": 8.0,
  "aco": {
    "alpha": 1.6,
    "beta": 1.2,
    "rho": 0.92,
    "q": 2.0,
    "deadband": 0.2,
    "local_weight": 0.7,
    "global_weight": 0.3,
    "group_weight": 0.2,
    "council_weight": 0.1,
    "history_size": 5,
    "tau0": 1.0,
    "local_decay": 0.15,
    "min_action_hold_seconds": 0.6
  }
}
```

Or set environment variables:
- `NODE_ID`
- `GROUP_ID`
- `RABBIT_HOST`
- `RABBIT_USER`
- `RABBIT_PASSWORD`
- `TARGET_TEMP`
- `HAS_SENSOR`
- `TARGET_MIN_TEMP`
- `TARGET_MAX_TEMP`
- `PEER_STALE_SECONDS`
- `LEADER_BUS_TOPIC`
- `GROUP_TARGET_TOPIC`
- `ENABLE_LEADER_COUNCIL`
- `TARGET_VERSION_START`
- `TARGET_EPOCH`
- `LEADER_SYNC_INTERVAL`
- `LEADER_SIGNAL_STALE_SECONDS`
- `MONITOR_MAX_POINTS`
- `ACO_ALPHA`, `ACO_BETA`, `ACO_RHO`, `ACO_Q`
- `ACO_DEADBAND`, `ACO_LOCAL_WEIGHT`, `ACO_GLOBAL_WEIGHT`
- `ACO_GROUP_WEIGHT`, `ACO_COUNCIL_WEIGHT`
- `ACO_HISTORY_SIZE`, `ACO_TAU0`, `ACO_LOCAL_DECAY`
- `ACO_MIN_ACTION_HOLD_SECONDS`

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
Use different `node_id` for each. Add `group_id` to split nodes into zones with one elected leader per zone:

```powershell
# Terminal 1
python src/node.py

# Terminal 2
NODE_ID=node2 python src/node.py

# Terminal 3
NODE_ID=node3 python src/node.py

# Terminal 4 (different group)
NODE_ID=node4 GROUP_ID=zone_b ENABLE_LEADER_COUNCIL=true python src/node.py
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

Nodes with the same `GROUP_ID` elect a local leader. If `ENABLE_LEADER_COUNCIL=true`, group leaders publish summaries on `LEADER_BUS_TOPIC` and consume summaries from other leaders.
For first runs, keep `ENABLE_LEADER_COUNCIL=false` until each group is converging, then enable it.

### Hierarchical Validation Scenarios

1. **One leader per group**
   - Start at least 2 groups (`GROUP_ID=zone_a`, `GROUP_ID=zone_b`) with 2+ nodes each.
   - Confirm monitor shows one active leader for each group.

2. **Failover inside a group**
   - Stop the current leader in `zone_a`.
   - Confirm a new `zone_a` leader appears within heartbeat timeout.

3. **Leader-council continuity**
   - Run with `ENABLE_LEADER_COUNCIL=true`.
   - Stop one group leader and verify remaining groups still publish fresh leader summaries.

### Web Monitor
Run the monitor to view the swarm:
```powershell
.\scripts\run_monitor.ps1
```

Access at: http://localhost:5000

Includes:
- Overview dashboard with leader status, convergence, heartbeat freshness, and action churn.
- Trends page (`/charts`) with temperatures, actions, average-vs-target, and pheromone evolution.

To allow connections from other machines:
```powershell
.\scripts\run_monitor.ps1 -BindHost 0.0.0.0
```

Then access at: http://<server-ip>:5000

### Target Propagation Hierarchy

Target updates now use a hierarchical control path to avoid split target state:

1. Monitor/API acts as command source and publishes `target_update` to `swarm.temperature.cmd.target.set`.
2. Group leaders consume that command, apply only newer `(epoch, version)` updates, then relay `group_target_apply` on `GROUP_TARGET_TOPIC` (default `swarm.temperature.group.target`).
3. Member nodes apply only relayed group updates for their own `group_id`, and ignore stale/duplicate versions.
4. Nodes publish `target_epoch` and `target_version` in telemetry so monitor can show consensus.

Version ordering is strict: higher `(epoch, version)` always wins. This keeps all groups and nodes converging on one canonical target.

### Run Complete Demo
Launch everything at once (nodes, monitor, visualization):
```powershell
.\scripts\run_all.ps1 -Nodes 4
```

Defaults to 3 nodes + 2 groups + monitor + visualize. Customize with `-Nodes 10 -Groups 2 -Monitor:$true`.

For CMD:
```bat
scripts\run_all.bat 10 2 yes yes
```

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
