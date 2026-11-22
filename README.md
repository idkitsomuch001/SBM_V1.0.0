# SBM

[![License](https://img.shields.io/badge/License-All%20rights%20reserved-red.svg)](https://github.com/idkitsomuch001)
[![GitHub](https://img.shields.io/badge/GitHub-idkitsomuch001-181717?logo=github&logoColor=white)](https://github.com/idkitsomuch001)
[![Discord DM](https://discord.com/users/1574160545064558685)

**A screen-only bot for Brawl Stars.** SBM reads the game from an Android emulator's screen with computer vision, decides what to do, and plays through touch input. It never reads the game's memory and never modifies the client: everything it knows comes from pixels.

> [!WARNING]
> Automating Brawl Stars breaks Supercell's terms of service and can get the account banned. Use it only with accounts you are willing to lose.

## What it does

- **Sees the game**: detects players, enemies, teammates, obstacles and terrain with ONNX models running on ONNX Runtime.
- **Understands the game state**: lobby, brawler selection, matchmaking, in-match and end screens, with recovery when something unexpected appears.
- **Plays**: movement and attacks are driven by scriptable *playstyles* (`playstyles/*.sbm`).
- **Controls the emulator** through ADB and scrcpy.
- **Local web dashboard** (Flask): queue, playstyles, settings, live logs and match history in six views, with a pywebview desktop window, the system browser or headless mode.
- **Notifications and remote control** (optional): Discord webhook, Telegram bot or a Discord bot with slash commands.

## Tech stack

| Area | Tools |
| --- | --- |
| Language | Python 3.11 |
| Vision | OpenCV, ONNX Runtime, NumPy |
| Device control | ADB (`adbutils`), scrcpy |
| Interface | Flask web UI, pywebview desktop window, `discord.py` |

## Requirements

- Windows (the desktop window, console handling and process tuning are Windows-specific).
- Python 3.11.9.
- An Android emulator with ADB enabled, set to 1920x1080 for correct coordinate scaling.
- **NVIDIA GPUs**: `setup.py` installs `onnxruntime-gpu` when an NVIDIA GPU is detected, and falls back to DirectML, then CPU, if CUDA does not load.
- **AMD / Intel / iGPU**: DirectML on Windows (`onnxruntime-directml`), with CPU fallback.

## Installation

The easy way on Windows: double-click **`start.bat`**. On the first run it installs Python 3.11 if it is missing, creates `.venv`, downloads the dependencies (again only when `requirements.txt` changes) and then opens the SBM window. Every later start reuses all of that and is quick.

Manual setup:

```sh
python setup.py install
```

## Running

```sh
python main.py
```

| Flag | Effect |
| --- | --- |
| *(none)* | Console visible, UI in the SBM desktop window |
| `--no-console` | Hides the console window; output goes to `sbm.log`. Ignored when started from an existing terminal. |
| `--desktop` | Force the integrated pywebview window |
| `--web`, `--browser`, `--no-webapp` | Open the UI in the system browser instead |
| `--headless` | Serve the local web UI without opening anything |
| `--benchmark` | Measure capture FPS, emulator delay and bot processing time, then exit (`--frame-age`, `--input-latency`, `--ping` add optional tests) |

The web UI listens on `127.0.0.1` only and requires a per-start token, which the interface reads from the page itself.

## Playstyles

A playstyle is a small Python program that runs once per frame and returns a joystick vector. The first line is JSON metadata, everything after it is the script:

```text
{"name": "Default - UP", "description": "...", "brawlers": ["all"], "gamemodes": ["3v3"], "author": "...", "date": "..."}
movement = (0, -JOYSTICK_RADIUS)
```

The runtime exposes the current frame's data (`player_data`, `enemy_data`, `teammate_data`, `walls`, `bushes`, `brawlers_info`, ability readiness) and helpers (`find_closest_enemy`, `is_enemy_hittable`, `is_path_blocked`, `is_there_poison_gas`, `attack`, `use_super`, `use_gadget`, `use_hypercharge`). Scripts run with an empty `__builtins__` after an AST check that blocks imports and private attributes, so only import playstyles you trust. `playstyles/skeleton.py` documents the full context for editor autocompletion.

Bundled playstyles: Default (up/right), Follower, Showdown Follower, Showdown Survivor and Rush Mode (aggressive).

## Models

The free build ships three models in `models/`, all ONNX and all loaded through ONNX Runtime:

| File | Purpose |
| --- | --- |
| `mainInGameModel.onnx` | Entity detection (player, teammate, enemy, summonables) with a ground-point keypoint |
| `tileDetector.onnx` | Terrain segmentation converted into wall, bush, rope-fence, water and out-of-bounds tiles |
| `closeTileDetector.onnx` | Alternative terrain model, not used by the default pipeline |

`*.json` next to each model documents the classes, input size and preprocessing.

## Project layout

| Path | Contents |
| --- | --- |
| `main.py` | Startup, CLI flags, the frame loop and crash recovery |
| `window_controller.py` | ADB/scrcpy connection, screenshots, touch injection |
| `play.py` | Per-frame pipeline: detections, walls, abilities, playstyle execution |
| `state_finder.py` | Screen-state detection by template matching |
| `stage_manager.py` | What to do on each screen (lobby, match end, shop, popups...) |
| `lobby_automation.py` | Brawler selection and idle-screen handling |
| `trophy_observer.py` | Trophy/win accounting and `cfg/match_history.csv` |
| `detect.py`, `model_input.py` | ONNX session management, preprocessing and postprocessing |
| `console/` | Flask app, data service and runtime manager |
| `static/`, `templates/` | The web interface (single-page app, five languages) |
| `cfg/` | All configuration (buttons, timers, thresholds, webhooks, brawler data) |
| `scrcpy/` | Vendored scrcpy client used for the video stream and input |

## Configuration

Everything lives in `cfg/*.toml` and can be edited from the Settings view or by hand:

- `general_config.toml`: FPS cap, threads, GPU/CPU, ADB port, interface mode, queue order, run time.
- `bot_config.toml`: detection thresholds, tile size, active playstyle, hold-attack handling.
- `buttons_config.toml`: every touch coordinate, in 1920x1080 space.
- `lobby_config.toml`: template-matching regions and HSV bounds.
- `time_tresholds.toml`: how often the bot checks states, walls, abilities and crashed apps.
- `debug_settings.toml`: debug view, match logging, verbose output.
- `webhook_config.toml`: Discord webhook/bot and Telegram credentials.
- `brawlers_info.json`: per-brawler ranges, super type and wall behaviour.

## License

Copyright (c) 2026 **Idkitsomuch** — https://github.com/idkitsomuch001

All rights reserved. See [LICENSE](LICENSE).
