# radio-recorder

NHKラジオの自動録音に向けた作業用リポジトリです。NHK番組表APIから AM/FM の番組表を取得し、対象番組の録音計画を作る CLI を用意しています。

## 前提

- Python 3.10+
- NHK番組表API の API キー

NHK の API ポータルで登録後、`NHK_API_KEY` 環境変数に設定してください。

```bash
export NHK_API_KEY=""
```

## 使い方

東京の NHK AM の番組表を取得:

```bash
python3 scripts/fetch_schedule.py --area 130 --service r1 --date 2026-08-20
```

JSON をそのまま見たい場合:

```bash
python3 scripts/fetch_schedule.py --area 130 --service r1 --date 2026-08-20 --raw
```

主なサービスID:

- `r1`: NHK AM
- `r3`: NHK FM

ラジオドラマ、朗読、ラジオ深夜便の録音対象を AM/FM 両方から一覧表示:

```bash
python3 scripts/record_daily_shows.py --area 130 --services r1,r3 --date 2026-08-20
```

録音対象ルールを別ファイルで差し替える場合:

```bash
python3 scripts/record_daily_shows.py \
  --area 130 \
  --services r1,r3 \
  --date 2026-08-20 \
  --rules config/recording_rules.json
```

実際に録音する場合:

```bash
export NHK_R1_STREAM_URL="https://example.invalid/r1.m3u8"
export NHK_R3_STREAM_URL="https://example.invalid/r3.m3u8"
export FFMPEG_BIN="/usr/bin/ffmpeg"
python3 scripts/record_daily_shows.py --area 130 --services r1,r3 --date 2026-08-20 --record
```

保存先は `recordings/<service>/<category>/<series>/` です。

## 録音対象ルール

録音対象の番組判定は [recording_rules.json](/home/katsuwo/work/radio-recorder/config/recording_rules.json) で管理します。形式は `include` と `exclude` の2種類です。

- `exclude`: 先に除外するキーワード群
- `include`: 録音対象に採用するキーワード群と保存先カテゴリ

各ルールは `title` / `subtitle` / `series_name` / `genres` を連結した文字列に対する部分一致です。今の既定値は、従来のハードコードと同じ内容です。

```json
{
  "exclude": [
    { "match": ["みんなのうた"] }
  ],
  "include": [
    {
      "category": "ラジオ深夜便",
      "folder_name": "radio_shinyabin",
      "match": ["ラジオ深夜便"]
    }
  ]
}
```

`systemd --user` 運用では、[radio-recorder.env.example](/home/katsuwo/work/radio-recorder/config/radio-recorder.env.example) の `RECORDING_RULES_PATH` で差し替えられます。

よく使う地域ID:

- `130`: 東京
- `270`: 大阪
- `280`: 神戸

## systemd で日次自動録音

常時運用するなら `cron` より `systemd --user` の方が扱いやすいです。再起動後の取りこぼし補完、ログ確認、環境変数の分離がしやすいため、このリポジトリでは `systemd/radio-recorder.service` と `systemd/radio-recorder.timer` を用意しました。

1. 設定ファイルを配置:

```bash
mkdir -p ~/.config/radio-recorder
cp config/radio-recorder.env.example ~/.config/radio-recorder/radio-recorder.env
```

2. `~/.config/radio-recorder/radio-recorder.env` を編集して API キー、配信 URL、保存先を設定。
   `ffmpeg` が標準 PATH にない環境では `FFMPEG_BIN=/absolute/path/to/ffmpeg` も設定。

3. user unit を配置:

```bash
./scripts/install_systemd_user.sh
```

4. リポジトリの配置場所が `/home/katsuwo/work/radio-recorder` と違う場合は、unit 内の `WorkingDirectory` と `ExecStart` を修正。

5. timer を有効化:

```bash
systemctl --user daemon-reload
systemctl --user enable --now radio-recorder.timer
systemctl --user list-timers radio-recorder.timer
```

デフォルトでは毎日 00:05 にその日の対象番組を取得し、番組開始時刻まで待機しながら順番に録音します。起動確認だけしたい場合は次で手動実行できます。

```bash
systemctl --user start radio-recorder.service
journalctl --user -u radio-recorder.service -n 100 --no-pager
```

## 運用前チェック

日次運用を始める前に、環境変数、`ffmpeg`、配信 URL 解決、当日の番組表取得が通るかを一括確認できます。

```bash
python3 scripts/preflight_check.py
```

直近の録音・文字起こしの生成物だけ見たい場合:

```bash
python3 scripts/report_latest_run.py --hours 24
```

## Google Drive へ自動保存

Google Drive 連携は `rclone` を前提にしています。録音完了後に `scripts/sync_to_gdrive.sh` が `rclone copy` を実行し、`recordings/` 以下を Drive へ複製します。`sync` ではなく `copy` を使っているので、Drive 側の既存ファイルを削除しません。

1. `rclone` をインストール。

2. Google Drive remote を作成:

```bash
rclone config
```

3. `~/.config/radio-recorder/radio-recorder.env` の以下を設定:

```bash
ENABLE_GDRIVE_SYNC=1
GDRIVE_REMOTE=gdrive
GDRIVE_REMOTE_PATH=radio-recorder
```

4. 先に単体で同期確認:

```bash
./scripts/sync_to_gdrive.sh
```

Drive への保存先は `gdrive:radio-recorder` が初期値です。録音後に毎回同期したくない場合は `ENABLE_GDRIVE_SYNC=0` にしてください。

ローカルの保存構成がそのまま Drive 側に再現されるか確認したい場合は、テストファイルを作って検証できます。

```bash
./scripts/verify_gdrive_sync.sh
```

このスクリプトは `recordings/<service>/<category>/<series>/` 配下にテスト用 `.m4a` ファイルを作り、同期後に `gdrive:radio-recorder/<service>/<category>/<series>/...` に同じ相対パスで存在することを `rclone lsf` で確認します。

## 補足

- API は 2026-03-30 時点の Ver.3 ラジオ API (`papiPgDateRadio`) を使っています。
- 2026-03-30 の再編以降、ラジオ系の案内は `r1` と `r3` ベースです。`r1` の表示名は「NHKラジオ第1」から「NHK AM」に変更されています。
