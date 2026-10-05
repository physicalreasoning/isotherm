# G3: synthetic pretraining, learning curves

Day-before read, 6063 walk-forward ladders, Δ log score vs market (nats, positive is better), 95% date-block CIs, 3 seeds per arm.

| Real training data | No pretraining | Pretrained | Pretrained minus none |
|---|---|---|---|
| 10% | +0.0183 [+0.0124, +0.0244] | +0.0356 [+0.0292, +0.0422] | +0.0173 [+0.0128, +0.0218] |
| 25% | +0.0361 [+0.0282, +0.0440] | +0.0378 [+0.0310, +0.0448] | +0.0018 [-0.0020, +0.0053] |
| 50% | +0.0429 [+0.0344, +0.0519] | +0.0366 [+0.0297, +0.0438] | -0.0064 [-0.0108, -0.0019] |
| 100% | +0.0453 [+0.0368, +0.0541] | +0.0407 [+0.0342, +0.0474] | -0.0047 [-0.0090, -0.0005] |

Pretrained on 50% minus none on 100%: -0.0087 [-0.0133, -0.0046]
Control (market labels at both stages): +0.0046 [+0.0039, +0.0054]
Last 12 months, pretrained minus none at 100%: +0.0037 [-0.0010, +0.0085]

Gate: (a) False · (b) False · **FAIL**
