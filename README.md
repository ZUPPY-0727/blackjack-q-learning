# blackjack-q-learning

Q学習を用いて、授業内で設定された独自ルールのブラックジャックにおける行動選択を学習するプロジェクトです。  
配布されたQ学習版ブラックジャックのコードをベースに、状態設計・報酬設計・学習率/探索率の調整・平均報酬の可視化などの改良を加えました。



---



## 基本的な設計思想

- ディーラープログラムとプレイヤープログラムに分かれており、両者がソケット通信をしながらゲームを進めます。
- ディーラーにしか把握できない情報は `dealer.py` 側に記載されており、プレイヤー側は通信を通して必要な情報だけを受け取ります。
- `classes.py` や `config.py` に書かれている情報はプレイヤー側から参照してよい設計です。
- 本プロジェクトでは、配布されたQ学習版をもとに改良を加え、元の実装との比較ができるように `ai_player_Q_original.py` も残しています。



---



## このリポジトリで行った主な改良

- 状態に `usable ace` を追加
- ディーラーのアップカードをそのままではなくバケット化して使用
- Hi-Lo カウントを状態に追加
- 最後に引いたカードを除いた手札情報をもとにした `base_bucket` を状態に追加
- reward shaping を導入
- 学習率と ε をゲーム回数に応じて変化させるように調整
- 学習後半の平均報酬を `avg_reward_log.csv` に保存
- 平均報酬が最高になった時点のQテーブルを `q_best.pkl` として保存



---



## ディレクトリ構成
```text
blackjack-q-learning/
├─ src/
│  ├─ ai_player_Q_Final.py
│  ├─ ai_player_Q_original.py
│  ├─ dealer.py
│  ├─ classes.py
│  └─ config.py
├─ requirements.txt
└─ README.md
```



---



## 実行手順

- 前提として、ターミナルを二つ使用します。
- まず一方のターミナルで`dealer.py`を実行します。
- `dealer.py`が接続町状態になったら、もう一方のターミナルでプレイヤープログラムを実行します。
- プレイヤープログラムが終了しても`dealer.py`は終了せず接続町状態に戻るため、続けて別のプレイヤープログラムを実行できます。
- `dealer.py`を終了したい場合は`Ctrl + c`で停止してください。



---



## 必要ライブラリ

`requirements.txt`を使ってインストールできます。

```bash
pip install -r requirements.txt
```



---



## ソケット通信に失敗する場合の対処法

ディーラー・プレイヤーカンの通信に失敗する場合は、接続先を`127.0.0.1`にそろえると改善することがあります。
- `dealer.py`
```python
soc.bind(('127.0.0.1' , PORT))
```

-`ai_player_Q.py`/`ai_player_Q_original.py`

```python
soc.connect(('127.0.0.1' . PORT))
```



---



## dealer.py

ブラックジャックの進行を管理するディーラープログラムです。  
カード配布、勝敗判定、シャッフル、プレイヤーとの通信を担当します。  
基本的には先に起動して待機させるだけです。


### コマンド例
```bash
python src/dealer.py
`
``

### オプション

特にありません。



---



## ai_player_Q.py

改良版のQ学習プレイヤーです。
現在の状態をもとに`HIT / STAND / DOUBLE DOWN / SURRENDER / RETRY`を選択しながら学習します。


## 主な特徴

- 状態として以下化の情報を追加
  - プレイヤーの現在のスコア
  - usable ace の有無
  - ディーラーアップカードのバケット
  - Hi-Lo カウント
  - 最後に引いたカードを除いた手札に基づく`base_bucket`
- reward shapingを導入
- εと学習率をゲーム進行に応じて変化
- 学習後半の平均報酬を`avg_reward_log.csvに保存
- 平均報酬が過去最高になった場合、Qテーブルを`q_best.pklに保存


### コマンド例

```bash
# 一から学習する場合
python src/ai_player_Q_Final.py --games 100000 --history play_log.csv --save QTable.pkl

# 学習済みQテーブルをロードして学習を再開する場合
python src/ai_player_Q_Final.py --games 50000 --history play_log.csv --load QTable.pkl --save new_QTable.pkl

# 学習済みQテーブルをロードしてテストプレイのみ行う場合
python src/ai_player_Q_Final.py --games 1000 --history test_log.csv --load q_best.pkl --testmode
```


### オプション

- `games`
  - 連続して何回ゲームをプレイするかを指定します。
  - 指定しない場合、デフォルト値は`1`です。

- `history`
  - プレイヤーの行動ログを保存するCSVファイル名を指定します。
  - 指定しない場合、デフォルト値は`play_log.csv`です。

- `load`
  - 指定したファイルからQテーブルをロードします。
  - 指定しない場合、新しいQテーブルで学習を開始します。

- `save`
  - 学習後のQテーブルを指定したファイル名で保存します。
  - 指定しない場合は保存しません

- `testmode`
  - 指定するとQテーブルを更新せず、常にQ値最大の行動を選択します。
  - 学習ではなく評価用のモードです。


### 出力される主なファイル

- `play_log.csv`
  - 各ゲーム中の状態・行動・結果・報酬のログ

- `avg_reward_log.csv`
  - 学習後半について、5000ゲームごとの平均報酬を記録したCSV(追加分)

- `Qtable.pkl`
  - `--save`で指定した学習後のQテーブル

- `q_best.pkl`
  - 平均報酬が最もよかった時点のQテーブル(追加分)



---



## ai_player_Q_original.py

配布された元のQ学習プレイヤーです。
改良前の実装との比較用として残しています。
Final版より状態設計が単純で、平均報酬の可視化や追加のreward shapingなども入っていません。


### コマンド例

```bash
# 一から学習する場合
python src/ai_player_Q_original.py --games 10000 --history play_log.csv --save QTable.pkl

# 学習済みQテーブルをロードして再学習する場合
python src/ai_player_Q_original.py --games 10000 --history play_log.csv --load QTable.pkl --save new_QTable.pkl

# 学習済みQテーブルでテストプレイする場合
python src/ai_player_Q_original.py --games 1000 --history test_log.csv --load QTable.pkl --testmode
```


### オプション

オプションは`ai_player_Q.py`と同じです。


### 出力される主なファイル

- `play_log.csv`
  - 各ゲーム中の状態・行動・結果・報酬のログ

- `Qtable.pkl`
  - `--save`で指定した学習後のQテーブル



---



## pict.py 

`avg_reward_log.csv`を読み込み、平均報酬の推移を折れ線グラフで表示するための解析用スクリプトです。
学習が進むにつれて平均報酬がどう変化したかを確認するために使います。


### コマンド例

```bash
python src/pict.py
```


### 前提

事前に`ai_player_Q_Final.py`を学習モードで実行し、`avg_reward_log.csv`が生成されている必要があります。


### オプション

特にありません。



---



## classes.py

実行対象のプログラムではなく、共通で使うクラス群をまとめたファイルです。


## 主な内容

- `Action`
  - プレイヤーがとりうる行動の列挙

- `Strategy`
  - 行動選択戦略の列挙

- `CardSet`
  - カードのシャッフルとドロー

- `Hand`
  - 手札管理とスコア計算

- `Player`
  - 所持金、手札、通信、報酬更新などの管理

- `QTable`
  - Q値の保存、更新、ロード、セーブ



---



## config.py

各種設定値をまとめたファイルです。


## 主な設定

- `PORT`
  - ソケット通信で使用するポート番号

- `BET`
  - 基本ベット額

- `INITIAL_MONEY`
  - 初期所持金

- `N_DECKS`
  - 使用するデッキ数

- `SHUFFLE_INTERVAL`
  - 定期シャッフルの頻度

- `SHFFULE_THRESHOLD
  - 残りカード枚数による強制シャッフルの閾値

- `MAX_CARD_PER_GAME`
  - 1ゲームで使用できる最大カード枚数



## ルールについて

このプロジェクトで扱っているブラックジャックは、授業内で設定された独自ルールに基づいています。
通常のブラックジャックとは異なる部分があるため、詳しいルール説明や実験結果の考察は Qiita 記事側にまとめる予定です。




