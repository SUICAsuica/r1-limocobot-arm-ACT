# LIMO Cobot ACT 実験まとめ

作成日: 2026-05-18  
対象: LIMO + myCobot280 + PC側LeRobot/ACTによる模倣学習

このメモは、これまで行ったデータ収集、データセット変換、ACT学習、実機実行、ログ解析、問題切り分け、青いブッダだけの再学習までをまとめたものです。

---

## 1. 全体方針

最初に決めた構成は以下。

```text
LIMO / Orin側
  = センサー・ロボット状態の配信側
  = myCobotへの低レベル命令実行側

PC側
  = データ保存
  = 可視化
  = LeRobot dataset変換
  = ACT学習
  = ACT推論
```

基本方針:

```text
LIMO側:
  camera + myCobot state をHTTP配信
  myCobot command serverでsend_angles / gripperを受ける

PC側:
  HTTPで画像・関節角・グリッパーを取得
  episode単位で保存
  LeRobot形式に変換
  ACTでBehavior Cloning
  ACT推論結果をHTTPでLIMOへ送信
```

---

## 2. HTTP構成

### 観測側

LIMO側の観測HTTP:

```text
http://192.168.0.161:8001
```

主に使ったendpoint:

```text
GET /state.json
GET /image.jpg
GET /stream.mjpg
```

`state.json` には以下のような情報が入る想定。

```text
arm.angles
arm.gripper_value
arm.coords
camera状態
timestamp
```

### 命令側

LIMO側の命令HTTP:

```text
http://192.168.0.161:8002
```

主に使ったendpoint:

```text
GET  /angles
GET  /health
POST /send_angles
POST /set_gripper
POST /stop
POST /power_on
```

重要:

```text
/angles はPC側ACTが現在関節角を読むために使う
/send_angles はPC側ACTが目標関節角を送るために使う
/set_gripper はグリッパー命令に使う
```

---

## 3. 作成・使用した主要ファイル

### PC側

```text
/home/shori/limo_pull_dataset_collector.py
```

LIMOのHTTP配信から画像と状態をpullして、PC側にepisode保存するcollector。

```text
/home/shori/convert_limo_dataset_to_lerobot.py
```

raw datasetをLeRobot形式へ変換するスクリプト。

```text
/home/shori/run_act_policy_on_limo.py
```

ACT policyをPCで推論して、LIMO command serverへHTTP命令を送る実行スクリプト。

```text
/home/shori/validate_act_policy.py
```

学習済みACT policyをLeRobot dataset上で評価するためのスクリプト。

```text
/home/shori/limo_20hz_episode_classification.csv
```

episodeごとの動作特徴を分類したCSV。

```text
/home/shori/episode_contact_sheets/
```

episodeごとのサムネイル一覧。青い物体かどうかの目視分類に使った。

### LIMO側に置く想定のサーバー

```text
/home/shori/limo_cobot_setup/simple_mycobot_target_server.py
```

シンプルなmyCobot command server。複雑なchunk controllerをいったんやめ、基本のHTTP命令に戻すために使った。

```text
/home/shori/limo_cobot_setup/limo_mycobot_command_server.py
```

chunk-httpやsmooth controllerを含む、より複雑なcommand server。

---

## 4. 最初のmyCobotテスト

最初に作った確認用コード:

```python
from pymycobot import MyCobot280
import time

mc = MyCobot280('/dev/ttyACM0', 115200)

print("mode:", mc.get_transponder_mode())
print("set mode:", mc.set_transponder_mode(1))
print("free:", mc.is_free_mode())
print("set free 0:", mc.set_free_mode(0))
print("error:", mc.get_error_information())

angles = mc.get_angles()
print("angles:", angles)

target = angles[:]
target[5] += 2
print("send:", mc.send_angles(target, 10))
time.sleep(3)
print("after:", mc.get_angles())
```

目的:

```text
myCobot280が/dev/ttyACM0で読めるか
get_anglesが返るか
send_anglesで微小動作できるか
```

---

## 5. データ収集方針

PC側に正式datasetを保存する方針にした。

推奨構成:

```text
dataset/
  episode_0001/
    rgb/
      000000.jpg
      000001.jpg
      ...
    states.csv
    actions.csv
    meta.json
```

最低限保存する情報:

```csv
seq,limo_time_ns,pc_receive_time_ns,j1,j2,j3,j4,j5,j6,gripper,image_path
```

重要な考え:

```text
LIMO側で取得時刻を付ける
PC側受信時刻も別で保存する
画像と関節角はseqで必ず対応させる
```

手で動かすデモでは、命令actionは存在しないため、

```text
action_t = joint_angles_{t+h} または joint_angles_{t+h} - joint_angles_t
```

として後処理で生成する方針にした。

---

## 6. raw dataset

raw dataset root:

```text
/home/shori/dataset
```

episodeは以下のように保存された。

```text
/home/shori/dataset/episode_0039
/home/shori/dataset/episode_0040
...
/home/shori/dataset/episode_0100
```

途中から20Hzでデータを取った。

使えるepisodeを後からLeRobot形式へ変換した。

---

## 7. LeRobot変換スクリプトの仕様

変換スクリプト:

```text
/home/shori/convert_limo_dataset_to_lerobot.py
```

重要な引数:

```text
--source
  raw dataset root

--episodes
  変換するraw episode番号

--repo-id
  LeRobot datasetのrepo_id

--root
  LeRobot datasetの保存先

--fps
  datasetのfps

--action-horizon-frames
  何フレーム先をactionにするか

--action-mode
  delta or target

--overwrite
  既存datasetを上書き
```

action生成:

```python
def expert_action_from_states(current, future):
    deltas = future[:6] - current[:6]
    return [delta_j1, ..., delta_j6, future_gripper]
```

```python
def target_action_from_state(future):
    return [future_j1, ..., future_j6, future_gripper]
```

今回主に使ったのは:

```text
--action-mode target
--action-horizon-frames 10
--fps 20
```

つまり:

```text
20Hzで10フレーム先 = 0.5秒先
action = 0.5秒先の目標関節角そのもの
```

注意:

```text
変換後のフレーム数 = raw states.csvの行数 - action_horizon_frames
```

例:

```text
raw episode_0039: 240 frames
LeRobot train episode_index=0: 230 frames
```

---

## 8. episode番号の対応

LeRobot datasetに変換すると、episode番号は振り直される。

例:

```text
raw:
  /home/shori/dataset/episode_0039

LeRobot:
  episode_index=0
```

青ブッダdatasetの対応:

```text
train:
0  -> 39
1  -> 40
2  -> 41
3  -> 42
4  -> 44
5  -> 48
6  -> 56
7  -> 59
8  -> 60
9  -> 61
10 -> 67

val:
0 -> 68
1 -> 86
2 -> 87
3 -> 100
```

確認例:

```text
train episode_index=0 first state
  [-94.92, 0.96, 2.81, -99.14, 5.97, 32.95, 81.0]

raw episode_0039 first state
  [-94.92, 0.96, 2.81, -99.14, 5.97, 32.95, 81.0]
```

---

## 9. 最初の大きな20Hz target h10 dataset

dataset:

```text
/home/shori/lerobot_datasets/limo_cobot_20hz_target_h10_train
/home/shori/lerobot_datasets/limo_cobot_20hz_target_h10_val
```

内容:

```text
train: 43 episodes
val:   8 episodes
total: 51 episodes
```

設定:

```text
fps=20
action_horizon_frames=10
action_mode=target
```

学習モデル:

```text
/home/shori/outputs/train/act_limo_cobot_20hz_target_h10_chunk50/checkpoints/015000/pretrained_model
```

注意:

```text
ディレクトリ名に chunk50 とあるが、実際のACT設定は chunk_size=100, n_action_steps=100
```

つまり:

```text
20Hz
chunk_size=100
100 steps = 5秒分のaction chunk
```

---

## 10. ACT学習コマンド例

20Hz target h10 datasetの学習コマンド例:

```bash
/home/shori/venvs/lerobot_act/bin/lerobot-train \
  --dataset.repo_id=local/limo_cobot_20hz_target_h10_train \
  --dataset.root=/home/shori/lerobot_datasets/limo_cobot_20hz_target_h10_train \
  --dataset.video_backend=pyav \
  --policy.type=act \
  --policy.chunk_size=100 \
  --policy.n_action_steps=100 \
  --policy.device=cuda \
  --policy.push_to_hub=false \
  --wandb.enable=false \
  --output_dir=/home/shori/outputs/train/act_limo_cobot_20hz_target_h10_chunk50 \
  --job_name=act_limo_cobot_20hz_target_h10_chunk50 \
  --steps=15000 \
  --batch_size=4 \
  --num_workers=2 \
  --save_checkpoint=true \
  --save_freq=3000 \
  --log_freq=20 \
  --eval_freq=0
```

過去に出たエラー:

```text
ValueError:
The chunk size is the upper bound for the number of action steps per model invocation.
Got 100 for n_action_steps and 50 for chunk_size.
```

原因:

```text
chunk_size=50 にしたのに n_action_steps が100のままだった
```

修正:

```text
chunk_size >= n_action_steps にする
```

または:

```text
--policy.chunk_size=100
--policy.n_action_steps=100
```

---

## 11. ACT実行スクリプト

実行スクリプト:

```text
/home/shori/run_act_policy_on_limo.py
```

主な機能:

```text
1. policyをload
2. LIMOからimage/state/anglesを取得
3. ACTでactionを推論
4. action-mode targetなら現在角との差分を計算
5. action-scaleをかける
6. joint-max-delta-degで1stepごとの最大変化を制限
7. LIMO command serverへHTTP POST
8. gripper-modeに応じてグリッパー命令
9. log-fileに実行ログ保存
```

重要な引数:

```text
--policy-path
  実行する学習済みACTモデル

--limo-url
  観測HTTP

--command-url
  命令HTTP

--angles-url
  現在関節角を読むendpoint

--force-angles-url
  state.jsonではなくangles-urlを優先する

--command-mode
  http or chunk-http

--action-mode
  target or delta

--hz
  PC側推論・送信周期

--steps
  実行step数

--replan-steps
  何stepごとに再推論するか

--action-scale
  モデル出力を現在角へ反映する割合

--joint-max-delta-deg
  1stepあたりの最大角度変化

--speed
  myCobot send_anglesのspeed

--gripper-mode
  none / model / model_latch など

--log-file
  実行ログの保存先
```

---

## 12. 実機実行で試した主な方針

### 最初の強すぎる設定

```bash
--hz 10
--steps 220
--replan-steps 10
--action-scale 0.9
--joint-max-delta-deg 3,1.0,0.4,3.0,1.5,2.0
--speed 30
```

問題:

```text
動きが遅い
途中で終わる
手首やJ2/J4が追従しにくい
物体を見失う
```

### 速くした設定

```bash
--hz 20
--replan-steps 5
--action-scale 1.0
--joint-max-delta-deg 7,7,2,7,2,2
--speed 35
```

良くなった点:

```text
最初の動きは速くなった
qpos_staleも改善した
```

問題:

```text
勢いが強く、物体を見失う
行き過ぎる
モデルが目標物体に安定して向かえない
```

### シンプル構成に戻した設定

複雑なchunk-httpをやめて、PCから1stepずつHTTP `/send_angles` する構成に戻した。

```bash
--command-mode http
--action-mode target
--force-angles-url
```

理由:

```text
chunk receiver / smoothing / controller / cached angles などが絡み、問題切り分けが難しくなったため
```

---

## 13. グリッパーについて

グリッパーはモデル出力では閉じる方向の命令が出ていた。

ログ例:

```text
gripper=84.0->model:10.7 command:10.7
gripper sent=10 result=-1
```

これは:

```text
モデルは閉じる値を出している
PC側コードも/set_gripperへ送っている
```

ただし課題:

```text
掴んだあとに再び開いてしまう
chunk再推論時にgripperが戻る
接触後の保持が弱い
```

対策として入れた考え:

```text
--gripper-mode model_latch
--gripper-latch-threshold 35
--gripper-latch-value 10
```

意味:

```text
モデルが一度35以下を出したら「閉じた」と判断
以後は10を維持する
```

---

## 14. 実行ログ解析で分かったこと

解析対象例:

```text
/home/shori/act_logs/
```

一時期の問題:

```text
1. qpos/current が更新されていないように見える
2. J2/J4のdeltaが大きすぎる
3. replan後にsawtooth状の動きが出る
4. action-scale / speed / smoothing が攻めすぎ
5. モデル自体が汎化できていない可能性
```

特に見た指標:

```text
qpos_stale_steps
qpos_age
raw_delta
scaled_delta
clamped_delta
server_delta
gripper model/command
```

一時的に疑ったこと:

```text
/angles が古い値を返している
send_angles中にget_anglesが詰まっている
PC側が古いqposで推論している
```

その後、`--force-angles-url` と simple serverでかなり改善した。

---

## 15. chunk-http構成で考えたこと

一時期、以下の構成を検討した。

```text
PC:
  ACTでaction chunkを推論
  LIMOへ短いchunkとして送る

LIMO:
  chunkを受信
  trajectory bufferに入れる
  smooth controllerで20Hz実行
  myCobotへsend_angles
```

狙い:

```text
PCから1stepずつ送るより滑らかに動かす
LIMO側で低レベル制御を安定化する
```

しかし実際には:

```text
設定項目が多い
どこで詰まっているか分かりにくい
動かないときの切り分けが難しい
```

そのため一度シンプル構成に戻した。

現在の優先:

```text
まずACTモデルとデータの問題を切り分ける
低レベル制御はシンプルに保つ
```

---

## 16. 青いブッダだけに絞る判断

混合データには以下が含まれていた。

```text
青いブッダ
青い立方体
緑/白っぽい箱
左右/前後/底面違い
成功/失敗っぽいもの
```

問題:

```text
モデルがまだ弱い段階で複数物体・複数パターンを混ぜると、動作が平均化されやすい
今の目的は「青いブッダを安定して掴む」なので、まず対象を絞った方がよい
```

そのため:

```text
青いブッダだけ
success=Trueだけ
20Hz
target action
horizon=10 frames
```

で再学習した。

---

## 17. 青いブッダepisodeの選定

サムネイルを作成:

```text
/home/shori/episode_contact_sheets/
```

目視で青いブッダ候補:

```text
39-48,56,59-61,66-68,86-87,93,100
```

そのうち `meta.json` の `success=True` のみ採用。

採用したepisode:

```text
39,40,41,42,44,48,56,59,60,61,67,68,86,87,100
```

train/val split:

```text
train:
  39,40,41,42,44,48,56,59,60,61,67

val:
  68,86,87,100
```

除外した例:

```text
43 success=False
45 success=False
46 success=None
47 success=False
66 success=None
93 success=False
```

---

## 18. 青いブッダdataset変換コマンド

### train

```bash
/home/shori/venvs/lerobot_act/bin/python /home/shori/convert_limo_dataset_to_lerobot.py \
  --source /home/shori/dataset \
  --episodes 39,40,41,42,44,48,56,59,60,61,67 \
  --repo-id local/limo_cobot_blue_buddha_20hz_target_h10_train \
  --root /home/shori/lerobot_datasets/limo_cobot_blue_buddha_20hz_target_h10_train \
  --task "grasp blue buddha" \
  --fps 20 \
  --action-horizon-frames 10 \
  --action-mode target \
  --overwrite
```

### val

```bash
/home/shori/venvs/lerobot_act/bin/python /home/shori/convert_limo_dataset_to_lerobot.py \
  --source /home/shori/dataset \
  --episodes 68,86,87,100 \
  --repo-id local/limo_cobot_blue_buddha_20hz_target_h10_val \
  --root /home/shori/lerobot_datasets/limo_cobot_blue_buddha_20hz_target_h10_val \
  --task "grasp blue buddha" \
  --fps 20 \
  --action-horizon-frames 10 \
  --action-mode target \
  --overwrite
```

変換後:

```text
train:
  /home/shori/lerobot_datasets/limo_cobot_blue_buddha_20hz_target_h10_train
  11 episodes / 2804 frames

val:
  /home/shori/lerobot_datasets/limo_cobot_blue_buddha_20hz_target_h10_val
  4 episodes / 1436 frames
```

---

## 19. 青いブッダACT学習コマンド

```bash
rm -rf /home/shori/outputs/train/act_limo_cobot_blue_buddha_20hz_target_h10_chunk100

/home/shori/venvs/lerobot_act/bin/lerobot-train \
  --dataset.repo_id=local/limo_cobot_blue_buddha_20hz_target_h10_train \
  --dataset.root=/home/shori/lerobot_datasets/limo_cobot_blue_buddha_20hz_target_h10_train \
  --dataset.video_backend=pyav \
  --policy.type=act \
  --policy.chunk_size=100 \
  --policy.n_action_steps=100 \
  --policy.device=cuda \
  --policy.push_to_hub=false \
  --wandb.enable=false \
  --output_dir=/home/shori/outputs/train/act_limo_cobot_blue_buddha_20hz_target_h10_chunk100 \
  --job_name=act_limo_cobot_blue_buddha_20hz_target_h10_chunk100 \
  --steps=8000 \
  --batch_size=4 \
  --num_workers=2 \
  --save_checkpoint=true \
  --save_freq=2000 \
  --log_freq=20 \
  --eval_freq=0
```

学習済みモデル:

```text
/home/shori/outputs/train/act_limo_cobot_blue_buddha_20hz_target_h10_chunk100/checkpoints/008000/pretrained_model
```

保存されたcheckpoint:

```text
002000
004000
006000
008000
```

---

## 20. 青いブッダ学習データのstep数

train:

```text
2804 frames
```

batch size:

```text
4
```

1 epochあたりのoptimizer steps:

```text
2804 / 4 = 約701 steps
```

学習steps:

```text
8000
```

したがって:

```text
8000 / 701 = 約11.4 epoch
```

まとめ:

```text
学習データ量: 2804 frame
1 epoch: 約701 optimizer steps
今回の学習: 8000 optimizer steps = 約11.4周
```

---

## 21. 青いブッダ学習結果

学習中loss:

```text
初期: 30前後
数百step: 3前後
2000 step付近: 1.4前後
4000 step付近: 0.7前後
6000 step付近: 0.3前後
8000 step付近: 0.25前後
```

val評価:

```text
frames=1436
episodes=4
loss=1.5114
l1=1.2971
kl=0.0214
```

解釈:

```text
train lossはかなり下がっている
val lossはtrainより高い
データ数が少ないため過学習気味の可能性はある
ただし「青いブッダだけで動作を切り分ける」目的には有効
```

---

## 22. 青いブッダモデル実行コマンド

まず試すコマンド:

```bash
/home/shori/venvs/lerobot_act/bin/python /home/shori/run_act_policy_on_limo.py \
  --policy-path /home/shori/outputs/train/act_limo_cobot_blue_buddha_20hz_target_h10_chunk100/checkpoints/008000/pretrained_model \
  --limo-url http://192.168.0.161:8001 \
  --command-url http://192.168.0.161:8002 \
  --angles-url http://192.168.0.161:8002/angles \
  --force-angles-url \
  --command-mode http \
  --action-mode target \
  --hz 20 \
  --steps 600 \
  --replan-steps 5 \
  --action-scale 1.0 \
  --joint-max-delta-deg 5,5,2,5,2,2 \
  --speed 25 \
  --fallback-gripper 80 \
  --enable-motion \
  --gripper-mode model_latch \
  --gripper-latch-threshold 35 \
  --gripper-latch-value 10 \
  --log-file /home/shori/act_logs/run_$(date +%Y%m%d_%H%M%S)_blue_buddha.log
```

安全寄りにするなら:

```text
--action-scale 0.7
--joint-max-delta-deg 3,3,1.5,3,1,1
--speed 20
```

速くするなら:

```text
--action-scale 1.0
--joint-max-delta-deg 7,7,2,7,2,2
--speed 35
```

ただし、速くすると物体を見失いやすい。

---

## 23. 重要な学習設定の意味

### fps

```text
--fps 20
```

20Hzなので:

```text
1 frame = 0.05秒
```

### action horizon

```text
--action-horizon-frames 10
```

20Hzなので:

```text
10 frames = 0.5秒
```

actionは:

```text
今の観測から0.5秒先の目標関節角
```

### ACT chunk size

```text
--policy.chunk_size=100
--policy.n_action_steps=100
```

20Hzなので:

```text
100 steps = 5秒分のaction chunk
```

ただし実行時に全部を一気に盲目的に使うわけではなく、`replan-steps` ごとに再推論する。

### replan steps

```text
--replan-steps 5
```

20Hzなら:

```text
5 steps = 0.25秒ごとに再推論
```

```text
--replan-steps 10
```

なら:

```text
0.5秒ごとに再推論
```

1秒ごと以上は把持には遅い可能性が高い。

### action scale

```text
--action-scale 1.0
```

target actionの場合:

```text
target = current + (model_target - current) * action_scale
```

つまり:

```text
1.0 = モデル出力をそのまま目標にする
0.5 = モデル出力への移動量を半分にする
```

---

## 24. 今分かっている課題

### 1. モデルが目標物体を見失う

原因候補:

```text
データに複数物体・複数パターンが混ざっていた
カメラ視点で物体がすぐ画角外に出る
手首/先端姿勢の制御が弱い
速すぎる設定で行き過ぎる
```

対策:

```text
青いブッダだけで再学習済み
実行時はreplanを短くする
速すぎる場合はaction-scaleかjoint-max-deltaを下げる
```

### 2. 掴んだあと離す

原因候補:

```text
モデルがgripperを再び開く値を出す
chunk再推論時にgripperが戻る
訓練データに保持動作が少ない
```

対策:

```text
model_latchを使う
gripper-latch-threshold=35
gripper-latch-value=10
```

### 3. データが少ない

青いブッダだけ:

```text
train 11 episodes
val 4 episodes
```

これは切り分けには良いが、汎化には少ない。

### 4. 失敗データの扱い

失敗データは最初のBCには基本入れない方がよい。

理由:

```text
BCは「真似する」学習なので、失敗も真似してしまう
```

ただし将来的には:

```text
失敗データを分類器・価値関数・DAGGER的改善に使う
```

のは有効。

---

## 25. 次にやるべきこと

### 優先1: 青いブッダモデルを実機で試す

使うモデル:

```text
/home/shori/outputs/train/act_limo_cobot_blue_buddha_20hz_target_h10_chunk100/checkpoints/008000/pretrained_model
```

まずは安全寄り:

```text
hz=20
replan-steps=5
action-scale=0.7〜1.0
joint-max-delta-deg=3,3,1.5,3,1,1 から開始
speed=20〜25
gripper-mode=model_latch
```

### 優先2: 実行ログを見る

見るべき項目:

```text
current
raw_delta
scaled_delta
clamped_delta
target
server_delta
qpos_stale
gripper model/command
```

### 優先3: うまくいかない場合の切り分け

もし物体に向かわない:

```text
データ/モデル問題の可能性が高い
```

もし向かうが行き過ぎる:

```text
action-scale / joint-max-delta / speed を下げる
```

もし掴むが離す:

```text
gripper latch
保持データ追加
持ち上げ後の保持時間追加
```

もし動作がガクガク:

```text
replan-stepsを5
hz=20
joint-max-deltaを適度に下げる
simple serverで確認
```

### 優先4: 追加データ

青いブッダだけで安定しない場合:

```text
同じ初期姿勢
同じ青いブッダ
同じ照明
成功のみ
掴んで持ち上げて0.5〜1秒保持
20〜30 episode追加
```

追加データのポイント:

```text
物体が画角から消えないようにする
近づく途中で手首姿勢を安定させる
掴む直前と掴んだ後のフレームを多めに入れる
閉じたグリッパーを保持する
```

---

## 26. 現在の一番重要な結論

現時点の問題は、単純にLIMO側が全部悪いというより、

```text
1. データが混ざりすぎていた
2. モデルが対象物体を安定して追えていない
3. グリッパー保持が弱い
4. 実行設定が速すぎると画角外に出る
```

可能性が高い。

そのため今の正しい進め方は:

```text
青いブッダだけのモデルで実機確認
↓
ログを見る
↓
必要なら青いブッダ成功データを追加
↓
安定後に別物体・位置違いを段階的に混ぜる
```

---

## 27. 重要パス一覧

raw dataset:

```text
/home/shori/dataset
```

青ブッダLeRobot train:

```text
/home/shori/lerobot_datasets/limo_cobot_blue_buddha_20hz_target_h10_train
```

青ブッダLeRobot val:

```text
/home/shori/lerobot_datasets/limo_cobot_blue_buddha_20hz_target_h10_val
```

青ブッダACT model:

```text
/home/shori/outputs/train/act_limo_cobot_blue_buddha_20hz_target_h10_chunk100/checkpoints/008000/pretrained_model
```

全体20Hz target h10 model:

```text
/home/shori/outputs/train/act_limo_cobot_20hz_target_h10_chunk50/checkpoints/015000/pretrained_model
```

古いcenter model:

```text
/home/shori/outputs/train/act_limo_cobot_center_target_h5/checkpoints/005000/pretrained_model
```

実行ログ:

```text
/home/shori/act_logs
```

サムネイル:

```text
/home/shori/episode_contact_sheets
```

分類CSV:

```text
/home/shori/limo_20hz_episode_classification.csv
```

PC実行スクリプト:

```text
/home/shori/run_act_policy_on_limo.py
```

変換スクリプト:

```text
/home/shori/convert_limo_dataset_to_lerobot.py
```

評価スクリプト:

```text
/home/shori/validate_act_policy.py
```

