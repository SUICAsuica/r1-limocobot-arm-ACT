# r1-limocobot-arm-ACT

LIMO Pro2 と myCobot 280 を使い、Action Chunking with Transformers (ACT) で移動ロボット上のアーム把持動作を学習・実行するための研究用リポジトリです。

このリポジトリには、研究で使った収集スクリプト、ACT 実行スクリプト、LeRobot 形式に変換したデータセット、実験ログ、セットアップメモをまとめています。

## 研究の目的

LIMO Pro2 に搭載した myCobot 280 を対象に、カメラ画像と関節状態からアーム動作を予測し、目標物への到達・把持に近い動作を再現することを目指します。データ収集、LeRobot データセット化、ACT policy の検証、実機実行までを一連の流れとして扱います。

## ディレクトリ構成

```text
.
├── scripts/                 # データ収集、変換、ACT 実行、ROS 確認用スクリプト
├── data/
│   ├── lerobot_datasets/    # LeRobot 形式に変換した研究データセット
│   ├── sample_images/       # カメラ画像サンプル
│   └── qwen_samples/        # Qwen2-VL 確認用サンプル画像
├── logs/act_logs/           # 実機 ACT 実行ログ
├── act_logs_visuals/        # エピソード確認用コンタクトシート
└── docs/                    # セットアップメモ、進捗メモ、実機起動手順
```

## 主なスクリプト

| ファイル | 用途 |
| --- | --- |
| `scripts/dataset_logger.py` | HTTP 経由で画像・状態・アクションを記録する簡易データロガー |
| `scripts/limo_pull_dataset_collector.py` | LIMO 側のデータを取得してエピソードとして保存 |
| `scripts/convert_limo_dataset_to_lerobot.py` | 収集データを LeRobotDataset 形式へ変換 |
| `scripts/make_actions_from_states.py` | 状態列から action 列を作る補助スクリプト |
| `scripts/validate_act_policy.py` | ACT policy の簡易検証 |
| `scripts/run_act_policy_on_limo.py` | LIMO + myCobot 実機で ACT policy を実行 |
| `scripts/run_act_policy_mycobot.py` | myCobot 単体向けの ACT 実行 |
| `scripts/probe_limo_angles_rate.py` | LIMO 側の関節角・更新周期確認 |
| `scripts/limo_camera_view.py` | ROS2 カメラトピックの表示確認 |
| `scripts/run_qwen2_vl_2b.py` | Qwen2-VL による画像確認実験 |

## データセット

`data/lerobot_datasets/` に LeRobot 形式のデータセットを置いています。

含まれる主なデータセット:

- `limo_cobot_20hz_target_h10_train`
- `limo_cobot_20hz_target_h10_val`
- `limo_cobot_blue_buddha_20hz_target_h10_train`
- `limo_cobot_blue_buddha_20hz_target_h10_val`
- `limo_cobot_center`
- `limo_cobot_center_h5_train`
- `limo_cobot_center_h5_val`
- `limo_cobot_center_target_h5_train`
- `limo_cobot_center_target_h5_val`

各データセットには `meta/`, `data/`, `videos/` が含まれます。`meta/info.json` で observation、action、fps などの定義を確認できます。

## 実験ログ

`logs/act_logs/` には 2026-05-15 に実機で ACT policy を試したログを保存しています。`act_logs_visuals/` には収集エピソードの画像確認用コンタクトシートを置いています。

詳細な作業履歴は `docs/LIMO_COBOT_ACT_PROGRESS_SUMMARY.md` を参照してください。

## セットアップ概要

Python/LeRobot 側の主要依存関係:

```bash
pip install -r requirements.txt
```

ROS2 や実機環境の詳細は以下のメモを参照してください。

- `docs/LIMO_FOXY_STARTUP_GUIDE.md`
- `docs/LIMO_FOXY_CAMERA_STARTUP_MEMO.md`
- `docs/LIMO_ISAACSIM_SETUP.md`

## よく使うコマンド例

LeRobot データセットの変換:

```bash
python scripts/convert_limo_dataset_to_lerobot.py \
  --source <raw_episode_dir> \
  --root data/lerobot_datasets/<dataset_name> \
  --repo-id local/<dataset_name> \
  --episodes 1-10 \
  --overwrite
```

ACT policy の検証:

```bash
python scripts/validate_act_policy.py \
  --dataset-root data/lerobot_datasets/limo_cobot_center_target_h5_train \
  --repo-id local/limo_cobot_center_target_h5_train \
  --policy-path <act_policy_checkpoint_dir>
```

実機で ACT policy を動かす例:

```bash
python scripts/run_act_policy_on_limo.py \
  --policy-path <act_policy_checkpoint_dir> \
  --limo-url http://<limo_ip>:8001 \
  --action-mode target \
  --steps 100
```

引数名や実機 URL は実験時の環境に合わせて調整してください。

## 注意

- Qwen2-VL などの大きな外部モデル重みは、このリポジトリには含めていません。必要に応じて Hugging Face などから別途取得してください。
- ACT の学習済み checkpoint は、手元の実験環境にあるパスを指定して実行する想定です。
- 実機制御スクリプトは LIMO Pro2、myCobot、ROS2、ネットワーク設定に依存します。実行前に非常停止できる状態で、低速・安全範囲から確認してください。
