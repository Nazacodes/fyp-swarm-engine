# Node Configs

Use `nodes/configs/` as the preferred location for per-node configuration files.

The supervisor launcher expects:

1. `nodes/configs/config_nodeN.json`

One-time migration helper:

```bash
python scripts/migrate_node_configs.py
```

Generation helpers now write to this folder directly.