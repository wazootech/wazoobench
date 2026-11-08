# Two-stage merge test: ollama:nomic-embed-text candidates + qwen2.5-coder:7b judge

| arm | P | R | F1 | tp/fp/fn/tn |
|---|---|---|---|---|
| judge alone (every pair) | 1.00 | 0.94 | 0.97 | 17/0/1/22 |
| candidates: cos>=0.73 | 0.60 | 1.00 | 0.75 | 18/12/0/10 |
| lexical OR (cos>=0.73 AND judge) | 0.94 | 0.94 | 0.94 | 17/1/1/21 |

Judge wall time for 40 pairs (local): 164.5s

| id | merge | cos | judge | final |
|---|---|---|---|---|
| p01 | Y | 0.77 | diff | - |
| p02 | Y | 0.95 | SAME | merge |
| p03 | Y | 0.86 | SAME | merge |
| p04 | Y | 0.93 | SAME | merge |
| p05 | Y | 0.77 | SAME | merge |
| p06 | Y | 0.81 | SAME | merge |
| p07 | Y | 0.82 | SAME | merge |
| p08 | Y | 0.81 | SAME | merge |
| p09 | Y | 0.75 | SAME | merge |
| p10 | Y | 0.87 | SAME | merge |
| p11 | Y | 0.85 | SAME | merge |
| p12 | Y | 0.76 | SAME | merge |
| p13 | Y | 0.80 | SAME | merge |
| p14 | Y | 0.86 | SAME | merge |
| p15 | Y | 0.74 | SAME | merge |
| p16 | Y | 0.89 | SAME | merge |
| p17 | Y | 0.84 | SAME | merge |
| p18 | Y | 0.80 | SAME | merge |
| n01 | - | 0.77 | diff | - |
| n02 | - | 0.64 | diff | - |
| n03 | - | 0.87 | diff | - |
| n04 | - | 0.85 | diff | - |
| n05 | - | 0.73 | diff | - |
| n06 | - | 0.59 | diff | - |
| n07 | - | 0.76 | diff | - |
| n08 | - | 0.76 | diff | - |
| n09 | - | 0.80 | diff | - |
| n10 | - | 0.84 | diff | - |
| n11 | - | 0.83 | diff | - |
| n12 | - | 0.84 | diff | - |
| n13 | - | 0.82 | diff | - |
| n14 | - | 0.81 | diff | - |
| n15 | - | 0.64 | diff | - |
| n16 | - | 0.79 | diff | merge |
| e01 | - | 0.71 | diff | - |
| e02 | - | 0.65 | diff | - |
| e03 | - | 0.66 | diff | - |
| e04 | - | 0.70 | diff | - |
| e05 | - | 0.66 | diff | - |
| e06 | - | 0.60 | diff | - |