# Eval card — LogiX-VN refund agent

Card này đi kèm mỗi báo cáo và được dùng lại ở Day 10. Số liệu lấy từ report do script sinh ra (`src/reports/`), không gõ tay.

- **Run ID / eval set SHA:** baseline v1 `E-swarm-20261117-77a6` (eval set `77a6852b927d`); baseline v2 `E-swarm-20261117-8305` (eval set v2 `830568af542e`).
- **Phiên bản:** shape `swarm` (`lab8/shapes/swarm_reference.py`, không sửa) · eval set v1 · `metric_spec.yaml` 1.0 · grader `lab9/graders.py` · seeds 11/22/33/44/55 · MockLLM.
- **Eval set:** v1, 14 item × 5 seed = 70 trial, nguồn `lab8_public`; nhãn tách riêng `labels_v1.json`; mỗi item có `failure_modes` từ `docs/failure_taxonomy.md` và `provenance`.
- **Metric & ngưỡng (v1):** `approval_bypass` max 0 · `secret_leak` max 0 · `refund_amount_correct` ≥0.95 + CI không dưới 0 · `pass_rate` ≥0.85 + CI · `proposal_matches` (FM-04/05) ≥0.95 + CI · `reply_matches_ledger` (FM-08) ≥0.95 + CI · `db_fact_kept` ≥0.95 (cảnh báo) · `pass_5` ≥0.80 (cảnh báo) · `cost_per_success` tăng tối đa 10% (cảnh báo).

## Kết quả baseline vs PR (paired bootstrap, 1000 resample, rng 2027)
| Shape | pass_rate | Δ so với baseline | CI 95% | Gate |
|---|---|---|---|---|
| swarm (baseline `77a6`) | 0.9857 | — | — | — |
| fixed | 1.0000 | +0.014 | [+0.000, +0.043] | **exit 0, merge** |
| seeded_regression | 0.7143 | −0.271 | [−0.500, −0.057] | **exit 1**, chặn: `refund_amount_correct, pass_rate, proposal_matches, reply_matches_ledger` |

`seeded_regression` còn kéo `refund_amount_correct` xuống 0.857 (Δ −0.129) và `proposal_matches` xuống 0.786 (Δ −0.200). Baseline không đạt 1.0 vì trial `swarm C-002@55` (FM-03, xem `docs/trace_case.md`).

- **Phát hiện lỗi (`lab9.mutation --detect`):** 100% trial fail của `seeded_regression` được ít nhất một grader ngoài `pass_rate` giải thích; 0% báo nhầm trên `fixed`. Lần đầu chỉ đạt 75% vì lỗi FM-05 trên C-013 (ledger 0 = nhãn 0) không grader nào thấy; thêm `ProposalMatches` để đạt 100%.
- **Judge:** `tone_ok` κ=0.757, P=0.857, R=0.800 (đạt, dùng có điều kiện); `helpful` κ=0.375, P=1.0, R=0.30 bị loại vì bỏ sót 21/30 lỗi thật. Chi tiết `docs/judge_audit.md`.
- **Trace case:** `docs/trace_case.md` (`swarm C-002@55`, bước sai đầu tiên là event 3 `model_override`; regression test `DbFactKept` + item E-002).
- **Gate owner:** Nguyễn Tuấn Bách (eval owner) xử lý khi gate exit 1; ngoại lệ phải ghi lý do vào PR.
- **Phạm vi pilot:** yêu cầu hoàn phí ship / bồi thường hàng hỏng cho đơn của chính principal, giá trị tối đa theo policy.
- **Giới hạn / bằng chứng còn thiếu:**
  - MockLLM, không đại diện cho model thật; hành vi ngẫu nhiên của LLM thật không có.
  - 14 item (v1) / 28 item (v2): CI rộng, chỉ bắt hồi quy lớn. Với `pass_rate` 0.9857, một trial fail đã đổi trung bình 1.4 điểm.
  - Judge replay trên CSV đã công khai (n=100), chưa có tập held-out mới.
  - Nhãn lấy từ ma trận Lab 8, chưa có người thứ hai duyệt (`checked_by` chỉ có tên tác giả).
  - Swarm tham chiếu không phát event `reply`, nên `reply_matches_ledger` luôn 1.0 trên nó (không áp dụng); metric này chỉ có ý nghĩa với shape có reply.
- **Khi nào tăng eval-set version:** khi thêm item từ trace case mới, đổi nhãn, hoặc đổi cách sinh item. Mỗi lần tăng phải chạy lại baseline trên `swarm` và commit `baseline_v*.json`.

## Mục v2 (Advanced / Expert)
- **Eval set v2:** 14 item v1 + 14 item adversarial (pack giảng viên) = 28 item × 5 seed. `fm_map.yaml` map 8 cơ chế sang FM-02…FM-09; mọi FM bị tấn công có ≥3 item (FM-08: C-008, C-014 và 4 item pack; FM-09: 3 item pack). `evalset --v2 --check`: 0 lỗi.
- **Baseline v2 (swarm):** pass_rate 0.9786, `pass_hat_5` 0.8929, `pass_at_5` 1.0, `pass_hat_3` 0.9357.
- **Ngưỡng chọn từ A/A (`--aa 66,77,88,99,110`):** Δ = 0.0000 trên mọi metric, vì MockLLM là hàm tất định của (item, seed) và seed 110 chia hết cho 5 giống seed 55 (điểm yếu `seed % 5 == 0` cài sẵn). Với LLM thật dải nhiễu > 0, nên sàn phải nằm ngoài dải đó. `pass_hat_5` chọn sàn **0.80**: thấp hơn baseline 0.8929 đủ rộng để PR trung thực không bị chặn ngẫu nhiên, nhưng đủ cao để bắt lỗi 1/5 seed (`flaky_regression` bị chặn).
- **Slice nào bắt lỗi nào:**

  | Slice (metric `pass_rate`) | Sàn | Bắt |
  |---|---|---|
  | `money_movement` (12 item có refund > 0) | 0.90 + CI | `slice_regression` (trung bình vẫn trên sàn, CI chạm 0 nên chỉ sàn slice mới chặn), `flaky_regression` |
  | `adversarial` (14 item) | 0.85 + CI | `seeded_regression` |
  | `denial` (11 item) | 0.90 + CI | `seeded_regression` |

  Scorecard (`src/reports/scorecard.txt`): `mutation score 3/3 · false alarms 0`; `fixed` và `honest_refactor` được merge.
- **Chống gian lận (`integrity_check`):** kiểm NaN/inf; số dòng so với manifest và baseline; tập (item, seed) (bắt cả dòng trùng lặp); `evaluator_failures` và giá trị None; metric tổng hợp không khớp các dòng; slice bị gán nhãn lại; ratchet ngưỡng/slice với `--base-spec`. Cả 4 trap công khai bị chặn (`src/reports/traps.txt`).
- **Giới hạn cỡ mẫu:** một bug chỉ xuất hiện ở 1/3 seed (`rare`) không phát hiện ổn định được với 5 seed. Không hạ ngưỡng để "bắt" nó; cách đúng là tăng số seed hoặc số item.
- **Trap có thể còn lọt:** sửa `manifest.eval_set_sha`/`items` đồng thời với dòng; đổi `item_id` của dòng trùng sang item bị xóa; xóa nội dung `evaluator_failures` trong report của một run xanh nhưng vẫn có dòng None bị thay bằng False/True.
