# Setup pydexbot Guide

## 1. Preparation

### Preparation Checklist

| Item       | Value              | Description                                       |
| ---------- | ------------------ | ------------------------------------------------- |
| trade_pair | eth.usdt           | trade pair name                                   |
| target_dir | /opt/data/pydexbot | target directory of the pydexbot docker container |


## 2. Login to the Running Server by `ssh`

Login to the Running Server by `ssh`.


## 3. Set ENV variables

```bash
# prepare env
target_dir="/opt/data/pydexbot"
trade_pair="eth.usdt"

```

## 4. Change to `target_dir` directory
```bash
cd $target_dir
```

## 5. Edit config file to add new trade_pair

edit `config/config.yaml` file, add new trade_pair to `trade_pairs` section:
```bash
vim config/config.yaml
```
add new trade_pair `eth.usdt` to `trade_pairs` section as below:
```yaml
trade_pairs:
  - "flon.usdt"
  - "eth.usdt"
```
save and exit vim editor with `:wq` command.

## 6. Restart pydexbot docker container
```bash
docker restart pydexbot
```

## 7. Verify the new trade_pair bot is running

```bash
tail -n 10 -f "logs/trade_${trade_pair//./_}.log"
```
