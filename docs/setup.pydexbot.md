# Setup pydexbot Guide

## 1. Preparation

### Preparation Checklist

| Item          | Value                | Description                                       |
| ------------- | -------------------- | ------------------------------------------------- |
| trade_privkey | {YOUR_TRADE_PRIVKEY} | bot_trade_privkey                                 |
| bot_admin     | flonian              | Bot admin account, exists account                 |
| trade_pair    | flon.usdt            | trade pair name                                   |
| target_dir    | /opt/data/pydexbot   | target directory of the pydexbot docker container |


## 2. Login to the Running Server by `ssh`

Login to the Running Server by `ssh`.


## 3. Set ENV variables

```bash
# prepare env
export trade_privkey="${YOUR_TRADE_PRIVKEY}"
export target_dir="/opt/data/pydexbot"
export bot_admin="flonian"
export tokenx_mm_contract="tokenx.mm"
export buylowsellhi_contract="buylowsellhi"
export trade_pair="flon.usdt"
export url="https://m.flonscan.io"
```

## 4. Clone `pydexbot` repo

```bash
cd $HOME
# clone pydexbot repo
git clone --recurse-submodules https://github.com/tychefi/pydexbot.git
```
## 5. `cd` into `pydexbot` source directory

```bash

cd $HOME/pydexbot
```
## 6. Build and Run `pydexbot` docker image

```bash
bash build.docker.image.sh
```

## 6. configure the bot settings
```bash
cat <<EOF > config/.config.yaml
node_url: "${url}"
trade_privkey: "${trade_privkey}"
bot_admin: "${bot_admin}"
tokenx_mm_contract: "${tokenx_mm_contract}"
buylowsellhi_contract: "${buylowsellhi_contract}"
trade_pair: "${trade_pair}"
min_interval_seconds: 3
max_interval_seconds: 10
EOF
```
## 7. [optional] create dest root dir
```bash
sudo mkdir -p $target_dir; sudo chown -R $(id -u):$(id -g) $target_dir
```

## 8. Execute `setup.py` to install files to `target_dir`

```bash
bash setup.sh "$target_dir"
```
## 9. [optional] Check the config file
```bash
cat $data_dir/config/config.yaml
```

## 10. run pydexbot
```bash
cd $target_dir && bash run.sh
```

## 11. Check the log
```bash
docker logs -n 10 -f pydexbot
```