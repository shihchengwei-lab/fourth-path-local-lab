# AGENTS.md

## 這個 repo 是什麼

`fourth-path-local-lab` — separation-and-audit-alignment 的 local prototype。v3 在此 repo 加 **code review 層**治理（雲端 PR review 流程）。

核心目標：能力與安全同時成長。Main Agent 要更會產生正常任務的候選答案，但不能取得 final authority、tool/action authority 或自我放行權。外部 Classify / Cold Eyes / Action Gate 要擋住危險內容、假放行、hidden control-plane leakage 與 unaudited side effects；同時不要用過度保守封鎖犧牲正常能力。

## Review 指引

對本 repo PR 的 review，請遵守 [`docs/code-review.md`](docs/code-review.md) 的七欄 evidence-bound 結構。

特別重要：
- `evidence` 欄必填，空 evidence 的 high confidence 自動降為 medium
- `abstain_condition` 不為空 → 降一級 confidence

## 長期實驗與資源使用

這個 repo 會跑本機模型 eval、NVIDIA API teacher pass、LoRA/QLoRA 訓練與 release gate。開始任何長期循環前，先把任務分成兩類：

- 輕任務：讀檔、改 docs/code、寫資料集、CPU 單元測試、release gate、NVIDIA API teacher pass。這些通常可在使用者使用電腦時做，但涉及付費 API、帳號、憑證或大量外部請求時仍要確認授權。
- 重任務：GPU 訓練、長時間 Ollama/model-backed eval、大批量本機推理、會明顯占用 CPU/GPU/記憶體的工作。只有在使用者明確授權 idle/GPU window 時才啟動。

「繼續跑 loop」不等於可以在使用者正在用電腦時啟動重任務。若沒有 idle/GPU 授權，先做輕任務：補安全層測試、整理 failure labels、產生 verifier-backed repair rows、調用已授權的外部 teacher、跑小型 CPU validation、更新 handoff。

拿到 unattended / idle 授權後，不要在第一個 checkpoint 就停住。除非遇到失敗、資源限制、授權邊界、或已達使用者指定 stop condition，應持續推進下一個高價值步驟，並留下可接手的證據。

啟動重任務前要先明講：

```text
要跑什麼、會占用什麼資源、預期產物、停止條件。
```

使用者詢問「是否正在占用資源」時，立刻檢查並回報背景程序；若使用者正在使用電腦或要求停用資源，先停止本機重任務，再改做輕任務。
