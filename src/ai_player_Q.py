import copy
import socket
import argparse
import numpy as np
from classes import Action, Strategy, QTable, Player, get_card_info, get_action_name
from config import PORT, BET, INITIAL_MONEY, N_DECKS


# 1ゲームあたりのRETRY回数の上限
RETRY_MAX = 10


### グローバル変数 ###

# ゲームごとのRETRY回数のカウンター
g_retry_counter = 0

# カードカウンティング用（Hi-Lo）
# 低いカード(2〜6)が出ると +1, 高いカード(10,J,Q,K,A) が出ると -1, 7〜9 は 0
g_hilo_count = 0

#カウントのリセット&更新関数
def reset_card_counter():
    global g_hilo_count
    g_hilo_count = 0

def update_card_counter(card_ids):
    """
    card_ids: Dealer.get_info() 形式（0〜51）の整数のリスト
    """
    global g_hilo_count
    for cid in card_ids:
        rank = cid % 13 + 1   # 1〜13

        if 2 <= rank <= 6:
            g_hilo_count += 1       # 低いカード
        elif rank == 1 or 10 <= rank <= 13:
            g_hilo_count -= 1       # 高いカード
        # 7,8,9 のときは 0


# プレイヤークラスのインスタンスを作成
player = Player(initial_money=INITIAL_MONEY, basic_bet=BET)

# ディーラーとの通信用ソケット
soc = None

# Q学習用のQテーブル
q_table = QTable(action_class=Action, default_value=1.0)#Qテーブルの初期値

# Q学習の設定値

# ε-greedy の ε はゲーム回数に応じて変化させる
EPS_START = 0.5   # 学習開始時の ε（探索多め）
EPS_END   = 0.03  # 学習終了時の ε（ほぼ活用）
EPS = EPS_START   # 実際に使う現在の ε

# 学習率はゲーム回数に応じて変化させる
ALPHA_START = 0.1   # 学習開始時の学習率（大きめ）
ALPHA_END   = 0.005   # 学習終了時の学習率（小さめ）

DISCOUNT_FACTOR = 0.99  # 割引率


### 関数 ###

# ゲームを開始する
def game_start(game_ID=0):
    global g_retry_counter, player, soc

    print('Game {0} start.'.format(game_ID))
    print('  money: ', player.get_money(), '$')

    # RETRY回数カウンターの初期化
    g_retry_counter = 0

    # ディーラープログラムに接続する
    soc = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    soc.connect((socket.gethostname(), PORT))
    soc.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    # ベット
    bet, money = player.set_bet()
    print('Action: BET')
    print('  money: ', money, '$')
    print('  bet: ', bet, '$')

    # ディーラーから「カードシャッフルを行ったか否か」の情報を取得
    # シャッフルが行われた場合は True が, 行われなかった場合は False が，変数 cardset_shuffled にセットされる
    # なお，本サンプルコードではここで取得した情報は使用していない
    cardset_shuffled = player.receive_card_shuffle_status(soc)
    if cardset_shuffled:
        print('Dealer said: Card set has been shuffled before this game.')
        reset_card_counter()#ここを追加

    # ディーラーから初期カード情報を受信
    dc, pc1, pc2 = player.receive_init_cards(soc)
    update_card_counter([dc,pc1,pc2])#ここを追加

    print('Delaer gave cards.')
    print('  dealer-card: ', get_card_info(dc))
    print('  player-card 1: ', get_card_info(pc1))
    print('  player-card 2: ', get_card_info(pc2))
    print('  current score: ', player.get_score())

# 現時点での手札情報（ディーラー手札は見えているもののみ）を取得
def get_current_hands():
    return copy.deepcopy(player.player_hand), copy.deepcopy(player.dealer_hand)

# HITを実行する
def hit():
    global player, soc

    print('Action: HIT')

    # ディーラーにメッセージを送信
    player.send_message(soc, 'hit')

    # ディーラーから情報を受信
    pc, score, status, rate, dc = player.receive_message(dsoc=soc, get_player_card=True, get_dealer_cards=True)
    update_card_counter([pc])#ここを追加
    print('  player-card {0}: '.format(player.get_num_player_cards()), get_card_info(pc))
    print('  current score: ', score)

    # バーストした場合はゲーム終了
    if status == 'bust':
        update_card_counter(dc)#バースト時のディーラのカードもカウント
        for i in range(len(dc)):
            print('  dealer-card {0}: '.format(i+2), get_card_info(dc[i]))
        print("  dealer's score: ", player.get_dealer_score())
        soc.close() # ディーラーとの通信をカット
        reward = player.update_money(rate=rate) # 所持金額を更新
        print('Game finished.')
        print('  result: bust')
        print('  money: ', player.get_money(), '$')
        return reward, True, status

    # バーストしなかった場合は続行
    else:
        return 0, False, status

# STANDを実行する
def stand():
    global player, soc

    print('Action: STAND')

    # ディーラーにメッセージを送信
    player.send_message(soc, 'stand')

    # ディーラーから情報を受信
    score, status, rate, dc = player.receive_message(dsoc=soc, get_dealer_cards=True)
    print('  current score: ', score)
    for i in range(len(dc)):
        print('  dealer-card {0}: '.format(i+2), get_card_info(dc[i]))
    print("  dealer's score: ", player.get_dealer_score())
    update_card_counter(dc)#ディーラのカードを取得
    # ゲーム終了，ディーラーとの通信をカット
    soc.close()

    # 所持金額を更新
    reward = player.update_money(rate=rate)
    print('Game finished.')
    print('  result: ', status)
    print('  money: ', player.get_money(), '$')
    return reward, True, status

# DOUBLE_DOWNを実行する
def double_down():
    global player, soc

    print('Action: DOUBLE DOWN')

    # 今回のみベットを倍にする
    bet, money = player.double_bet()
    print('  money: ', money, '$')
    print('  bet: ', bet, '$')

    # ディーラーにメッセージを送信
    player.send_message(soc, 'double_down')

    # ディーラーから情報を受信
    pc, score, status, rate, dc = player.receive_message(dsoc=soc, get_player_card=True, get_dealer_cards=True)
    print('  player-card {0}: '.format(player.get_num_player_cards()), get_card_info(pc))
    print('  current score: ', score)
    for i in range(len(dc)):
        print('  dealer-card {0}: '.format(i+2), get_card_info(dc[i]))
    print("  dealer's score: ", player.get_dealer_score())
    update_card_counter([pc])#プレイヤーのカードを追加
    update_card_counter(dc)#ディーラのカードを追加
    # ゲーム終了，ディーラーとの通信をカット
    soc.close()

    # 所持金額を更新
    reward = player.update_money(rate=rate)
    print('Game finished.')
    print('  result: ', status)
    print('  money: ', player.get_money(), '$')
    return reward, True, status

# SURRENDERを実行する
def surrender():
    global player, soc

    print('Action: SURRENDER')

    # ディーラーにメッセージを送信
    player.send_message(soc, 'surrender')

    # ディーラーから情報を受信
    score, status, rate, dc = player.receive_message(dsoc=soc, get_dealer_cards=True)
    print('  current score: ', score)
    for i in range(len(dc)):
        print('  dealer-card {0}: '.format(i+2), get_card_info(dc[i]))
    print("  dealer's score: ", player.get_dealer_score())

    # ゲーム終了，ディーラーとの通信をカット
    soc.close()

    # 所持金額を更新
    reward = player.update_money(rate=rate)
    print('Game finished.')
    print('  result: ', status)
    print('  money: ', player.get_money(), '$')
    return reward, True, status

# RETRYを実行する
def retry():
    global player, soc

    print('Action: RETRY')

    # ベット額の 1/4 を消費
    penalty = player.current_bet // 4
    player.consume_money(penalty)
    print('  player-card {0} has been removed.'.format(player.get_num_player_cards()))
    print('  money: ', player.get_money(), '$')

    # ディーラーにメッセージを送信
    player.send_message(soc, 'retry')

    # ディーラーから情報を受信
    pc, score, status, rate, dc = player.receive_message(dsoc=soc, get_player_card=True, get_dealer_cards=True, retry_mode=True)
    print('  player-card {0}: '.format(player.get_num_player_cards()), get_card_info(pc))
    print('  current score: ', score)
    update_card_counter([pc])#プレイヤーカードを追加
    # バーストした場合はゲーム終了
    if status == 'bust':
        update_card_counter(dc)
        for i in range(len(dc)):
            print('  dealer-card {0}: '.format(i+2), get_card_info(dc[i]))
        print("  dealer's score: ", player.get_dealer_score())
        soc.close() # ディーラーとの通信をカット
        reward = player.update_money(rate=rate) # 所持金額を更新
        print('Game finished.')
        print('  result: bust')
        print('  money: ', player.get_money(), '$')
        return reward-penalty, True, status

    # バーストしなかった場合は続行
    else:
        return -penalty, False, status

# 行動の実行
def act(action: Action):
    if action == Action.HIT:
        return hit()
    elif action == Action.STAND:
        return stand()
    elif action == Action.DOUBLE_DOWN:
        return double_down()
    elif action == Action.SURRENDER:
        return surrender()
    elif action == Action.RETRY:
        return retry()
    else:
        exit()


### これ以降の関数が重要 ###

# プレイヤー手札の card_id のリストから BJ のスコアを計算する補助関数
def calc_score_from_cards(card_ids):
    # rank: 1=A, 2..10, 11=J,12=Q,13=K
    ranks = [(cid % 13) + 1 for cid in card_ids]

    total = 0
    n_ace = 0
    for r in ranks:
        if r == 1:          # A
            n_ace += 1
            total += 1      # ひとまず 1 点として足す
        elif 2 <= r <= 9:
            total += r
        else:               # 10, J, Q, K
            total += 10

    # A を 11 扱いにできるだけ昇格させる
    while n_ace > 0 and total + 10 <= 21:
        total += 10
        n_ace -= 1

    return total

# 現在の状態の取得
def get_state():
    p_hand, d_hand = get_current_hands()

    # プレイヤー：手札のスコア（現時点の合計）
    score = p_hand.get_score()

    # soft hand 判定（usable ace）
    have_ace = any(((c % 13) + 1) == 1 for c in p_hand.cards)
    usable_ace = 1 if (have_ace and score + 10 <= 21) else 0

    # --- ディーラーアップカード（1〜13: A,2,...,K） ---
    if d_hand.length() > 0:
        upcard_id = d_hand.cards[0]
        dealer_rank = upcard_id % 13 + 1
    else:
        dealer_rank = 0  # 安全側（ほぼ使われない想定）

    # ディーラーアップカードを 5 分割バケットに圧縮
    # 例:
    #   0 or (2,3)        -> 0  (情報なし or 2,3)
    #   4,5,6             -> 1  (弱い)
    #   7,8,9             -> 2  (中立)
    #   10,J,Q,K (10-13)  -> 3  (強い)
    #   A (1)             -> 4  (エース)
    if dealer_rank == 0 or dealer_rank in (2, 3):
        dealer_bucket = 0
    elif dealer_rank in (4, 5, 6):
        dealer_bucket = 1
    elif dealer_rank in (7, 8, 9):
        dealer_bucket = 2
    elif dealer_rank in (10, 11, 12, 13):
        dealer_bucket = 3
    else:  # dealer_rank == 1 (Ace)
        dealer_bucket = 4

    # --- ベース点（最後に引いたカードを除いたスコア） ---
    cards = p_hand.cards
    if len(cards) >= 2:
        base_score_raw = calc_score_from_cards(cards[:-1])
    else:
        # 1枚以下のときはとりあえず現スコアをそのまま使う
        base_score_raw = score

    # ベース点を 3 分割バケット化
    #   0: 〜7点
    #   1: 8〜11点
    #   2: 12点以上
    if base_score_raw <= 8:
        base_bucket = 0
    elif base_score_raw <= 11:
        base_bucket = 1
    else:
        base_bucket = 2

    # カードカウント（-6〜+6でクリップ）
    count = g_hilo_count
    if count > 6:
        count = 6
    elif count < -6:
        count = -6

    # 状態:
    #   (プレイヤースコア, soft/hard, ディーラーアップカード(5分割),
    #    Hi-Lo カウント, ベース点バケット)
    state = (score, usable_ace, dealer_bucket, count, base_bucket)
    return state


# 行動戦略
def select_action(state, strategy: Strategy):
    global q_table

    # Q値最大行動を選択する戦略
    if strategy == Strategy.QMAX:
        return q_table.get_best_action(state)

    # ε-greedy
    elif strategy == Strategy.E_GREEDY:
        if np.random.rand() < EPS:
            return select_action(state, strategy=Strategy.RANDOM)
        else:
            return q_table.get_best_action(state)

    # ランダム戦略
    else:
        z = np.random.randint(0, 5)
        if z == 0:
            return Action.HIT
        elif z == 1:
            return Action.STAND
        elif z == 2:
            return Action.DOUBLE_DOWN
        elif z == 3:
            return Action.SURRENDER
        else: # z == 4 のとき
            return Action.RETRY


### ここから処理開始 ###

def main():
    global g_retry_counter, player, soc, q_table,EPS

    parser = argparse.ArgumentParser(description='AI Black Jack Player (Q-learning)')
    parser.add_argument('--games', type=int, default=1, help='num. of games to play')
    parser.add_argument('--history', type=str, default='play_log.csv', help='filename where game history will be saved')
    parser.add_argument('--load', type=str, default='', help='filename of Q table to be loaded before learning')
    parser.add_argument('--save', type=str, default='', help='filename where Q table will be saved after learning')
    parser.add_argument('--testmode', help='this option runs the program without learning', action='store_true')
    args = parser.parse_args()

    n_games = args.games + 1

    # Qテーブルをロード
    if args.load != '':
        q_table.load(args.load)

    # ログファイルを開く
    logfile = open(args.history, 'w')
    print('score,usable_ace,dealer_bucket,count,base_bucket,action,result,reward', file=logfile) # ログファイルにヘッダ行（項目名の行）を出力

    # ==== 学習過程の平均報酬ログ（学習時のみ） ====
    # 後半のゲームだけを対象に 5000ゲームごとに平均報酬を記録する
    avg_log = None
    block_size = 5000                         # 5000ゲーム単位
    total_episodes = n_games - 1              # 実際のゲーム数（args.games）
    start_collect = total_episodes // 2       # 後半 50% から記録開始

    block_sum = 0.0       # いまのブロック内の報酬合計
    block_count = 0       # ブロック内のゲーム数
    best_avg = None       #これまでの最高平均報酬(まだなし)

    if not args.testmode:
        avg_log = open('avg_reward_log.csv', 'w')
        print('start_game,end_game,avg_reward', file=avg_log)


    # n_games回ゲームを実行
    for n in range(1, n_games):

        # 学習率とEPSをゲーム回数に応じて線形に変化させる
        if not args.testmode:
            # 進捗（0.0 ～ 1.0）
            progress = n / n_games

            # 学習率 α
            current_alpha = ALPHA_START + (ALPHA_END - ALPHA_START) * progress

            # ε-greedy の ε（探索率）
            # 全体の 50% の時点で EPS を EPS_END まで減少させ、それ以降は固定
            decay_ratio = 0.5  # 50%
            scaled = progress / decay_ratio
            if scaled > 1.0:
                scaled = 1.0

            EPS = EPS_START + (EPS_END - EPS_START) * scaled

        else:
            current_alpha = 0.0  # testmodeでは学習しないので未使用
            # testmode では常に QMAX なので EPS は使われない
        # nゲーム目を開始
        game_start(n)


        #このゲーム(1エピソード)の報酬合計
        episode_reward = 0.0

        # 「現在の状態」を取得
        state = get_state()


        while True:

            # 次に実行する行動を選択
            if args.testmode:
                action = select_action(state, Strategy.QMAX)
            else:
                action = select_action(state, Strategy.E_GREEDY)
            if g_retry_counter >= RETRY_MAX and action == Action.RETRY:
                # RETRY回数が上限に達しているにもかかわらずRETRYが選択された場合，他の行動をランダムに選択
                action = np.random.choice([
                    Action.HIT, Action.STAND, Action.DOUBLE_DOWN, Action.SURRENDER
                ])
            action_name = get_action_name(action) # 行動名を表す文字列を取得

            # 選択した行動を実際に実行
            # 戻り値:
            #   - done: 終了フラグ．今回の行動によりゲームが終了したか否か（終了した場合はTrue, 続行中ならFalse）
            #   - reward: 獲得金額（ゲーム続行中の場合は 0 , ただし RETRY を実行した場合は1回につき -BET/4 ）
            #   - status: 行動実行後のプレイヤーステータス（バーストしたか否か，勝ちか負けか，などの状態を表す文字列）
            reward, done, status = act(action)

            #このゲームの報酬を積算(retryのペナルティも含めて合計)
            episode_reward += reward

            # 実行した行動がRETRYだった場合はRETRY回数カウンターを1増やす
            if action == Action.RETRY:
                g_retry_counter += 1

            # 「現在の状態」を再取得
            prev_state = state # 行動前の状態を別変数に退避
            prev_score = prev_state[0] # 行動前のプレイヤー手札のスコア（prev_state の一つ目の要素）
            state = get_state()
            score = state[0] # 行動後のプレイヤー手札のスコア（state の一つ目の要素）

            # ===========================
            #  中間報酬 (reward shaping)
            # ===========================
            shaped_reward = reward  # まずは本来の報酬からスタート

            if not args.testmode:
                # prev_state の中身:
                #   0: score
                #   1: usable_ace
                #   2: dealer_bucket
                #   3: count
                #   4: base_bucket
                prev_score        = prev_state[0]
                prev_usable_ace   = prev_state[1]
                prev_dealer_bucket = prev_state[2]
                prev_count        = prev_state[3]
                prev_base_bucket  = prev_state[4]

                # ----- HIT -----
                if action == Action.HIT:
                    prev_dist = abs(21 - prev_score)
                    new_dist  = abs(21 - score)
                    shaped_reward += 0.03 * (prev_dist - new_dist)

                    if score > 21:
                        shaped_reward -= 0.25 * BET

                    #17以上のhitを抑制する
                    if score >= 17:
                        shaped_reward -= 0.05 * BET

                # ----- STAND -----
                elif action == Action.STAND:
                    if prev_score >= 18:
                        shaped_reward += 0.25
                    elif prev_score < 12:
                        shaped_reward -= 0.2

                # ----- DOUBLE DOWN -----
                elif action == Action.DOUBLE_DOWN:
                    # 10〜11 かつディーラー 2〜9（バケット1〜3）のときだけ少し褒める
                    if 10 <= prev_score <= 11 and 1 <= prev_dealer_bucket <= 3:
                        shaped_reward += 0.25 * BET
                    else:
                        shaped_reward -= 0.3 * BET

                # ----- RETRY -----
                elif action == Action.RETRY:
                    # ベース点 9〜11（base_bucket == 1）かつ
                    # 現在のスコアが 18 未満のときに RETRY を「ちょい優遇」
                    if (prev_base_bucket == 1) and (prev_score < 18):
                        shaped_reward += 0.05 * BET   # 好みに応じて係数は調整してOK
                    else:
                        shaped_reward -= 0.07 * BET   # それ以外の RETRY は少し抑制

                    # RETRY 連打を抑えたいなら（いらなければこの if ごと消してOK）
                    if g_retry_counter >= 2:
                        shaped_reward -= 0.05 * BET        



            # Qテーブルを更新
            if not args.testmode:
                Q = q_table.get_Q_value(prev_state, action)

                if done:
                    target = shaped_reward      # 終局なので将来の報酬は無し
                else:
                    _, V = q_table.get_best_action(state, with_value=True)
                    target = shaped_reward + DISCOUNT_FACTOR * V

                # 学習率 current_alpha を使用
                Q = (1 - current_alpha) * Q + current_alpha * target
                q_table.set_Q_value(prev_state, action, Q)


            # ログファイルに「行動前の状態」「行動の種類」「行動結果」「獲得金額」などの情報を記録
            print('{},{},{},{},{},{},{},{}'.format(
                prev_state[0],  # score
                prev_state[1],  # usable_ace
                prev_state[2],  # dealer_bucket
                prev_state[3],  # count
                prev_state[4],  # base_bucket
                action_name,
                status,
                reward
            ), file=logfile)


            # 終了フラグが立った場合はnゲーム目を終了
            if done == True:
                break

        print('')


        # ==== 5000ゲームごとの平均報酬を集計（学習時のみ）====
        if (not args.testmode) and (n > start_collect):
            block_sum += episode_reward
            block_count += 1

            # 5000ゲームたまったら平均を出してログ
            if block_count == block_size:
                start_game = n - block_size + 1
                end_game = n
                avg_reward = block_sum / block_size
                print(f'{start_game},{end_game},{avg_reward}', file=avg_log)

                # ★ ここで「これまでの最高平均」を更新していたらQテーブルを保存
                if (best_avg is None) or (avg_reward > best_avg):
                    best_avg = avg_reward
                    print(f'[*] New best avg_reward = {avg_reward:.4f}  (games {start_game}–{end_game})')
                    q_table.save('q_best.pkl')   # ベスト版Qテーブルを保存

                    
                # 次のブロックに向けてリセット
                block_sum = 0.0
                block_count = 0


    # ログファイルを閉じる
    logfile.close()

    #平均報酬ログを閉じる。
    if avg_log is not None:
        avg_log.close()

    # Qテーブルをセーブ
    if args.save != '':
        q_table.save(args.save)


if __name__ == '__main__':
    main()
