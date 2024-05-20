# ANT+ Devices

A barebones CLI tool for reading ANT+ Device Data

### Quickstart

```shell

source "$CI_PROJECT_DIR/.venv/bin/activate"
printf '%s\n' $ANT_DEVICE_CFG | jq . > "$CI_PROJECT_DIR/.cache/ant.cfg"
cd "$CI_PROJECT_DIR/src"
python3 -m ant --log=WARNING read "$CI_PROJECT_DIR/.cache/ant.cfg" |
  tee "$CI_PROJECT_DIR/.cache/heartbeat-$(date -u '+%Y-%m-%d-%H-%M-%S').jsonl"

```
