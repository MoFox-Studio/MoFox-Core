# MoFox_Bot Deployment Guide

Welcome! This guide walks you through deploying MoFox_Bot on Windows.

## 1. System Requirements

- **OS**: Windows 10 or Windows 11
- **Python**: >= 3.10
- **Git**: To clone repositories
- **uv**: Recommended Python package manager (>= 0.1.0)

## 2. Deployment Steps

### Step 1: Get the code

Create a folder for the deployment and clone MoFox_Bot plus the Napcat adapter.

```shell
mkdir MoFox_Bot_Deployment
cd MoFox_Bot_Deployment
git clone https://github.com/MoFox-Studio/MoFox_Bot.git
git clone https://github.com/MoFox-Studio/Napcat-Adapter.git
```

### Step 2: Install uv

We recommend `uv` for speed and dependency management.

```shell
pip install uv
```

### Step 3: Install dependencies

**1) MoFox_Bot deps**

Inside `mmc`, create a venv and install requirements.

```shell
cd mmc
uv venv
uv pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple --upgrade
```

**2) Napcat-Adapter deps**

Go back, enter `Napcat-Adapter`, create a venv, and install requirements.

```shell
cd ..
cd Napcat-Adapter
uv venv
uv pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple --upgrade
```

### Step 4: Configure MoFox_Bot and the adapter

**MoFox_Bot**
- In `mmc`, copy `template/bot_config_template.toml` to `config/bot_config.toml`.
- Copy `template/model_config_template.toml` to `config/model_config.toml`.
- Fill in API keys and other settings per [Model Configuration Guide](guides/model_configuration_guide.md) and comments in `bot_config.toml`.

**Napcat-Adapter**
- In `Napcat-Adapter`, copy `template/template_config.toml` to the root and rename to `config.toml`.
- Edit `config.toml`, set `[Napcat_Server]` and `[MaiBot_Server]`:
  - `[Napcat_Server].port` must match the reverse-proxy port set in Napcat.
  - `[MaiBot_Server].port` must match the port set in MoFox_Bot `bot_config.toml`.

### Step 5: Run

**1) Start Napcat**

See the [NapCatQQ docs](https://napcat-qq.github.io/) for deployment and startup.

**2) Start MoFox_Bot**

```shell
cd mmc
uv run python bot.py
```

**3) Start Napcat-Adapter**

In a new terminal:

```shell
cd Napcat-Adapter
uv run python main.py
```

MoFox_Bot should now be running.

## 3. Configuration Details

### `bot_config.toml`

Main config: bot nickname, owner QQ, command prefix, database, etc. Follow inline comments.

### `model_config.toml`

Configure AI models and providers. See [Model Configuration Guide](guides/model_configuration_guide.md).

### Plugin configs

Each plugin has its own config under `mmc/config/plugins/`, auto-generated from its `config_schema`. See [Plugin Configuration Guide](plugins/configuration-guide.md).

## 4. Troubleshooting

- **Dependency install fails**:
  - Switch PyPI mirror.
  - Check network.
- **API calls fail**:
  - Verify API key and `base_url` in `model_config.toml`.
- **Cannot reach Napcat**:
  - Ensure Napcat is running.
  - Confirm `[Napcat_Server].port` in `config.toml` matches Napcat settings.

For other issues, inspect logs in `logs/` for details.