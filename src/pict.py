import pandas as pd
import matplotlib.pyplot as plt

df = pd.read_csv('avg_reward_log.csv')
# 中点のゲーム番号を横軸にする
df['mid_game'] = (df['start_game'] + df['end_game']) / 2

plt.plot(df['mid_game'], df['avg_reward'])
plt.xlabel('Game')
plt.ylabel('Average reward (per 5000 games)')
plt.grid(True)
plt.show()
