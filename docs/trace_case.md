# Trace case: từ trace tới quyết định sai đầu tiên

```bash
cd src
python -m lab9.trace_case --shape swarm --claim C-002 --seed 55
python -m lab9.trace_case --shape fixed --claim C-002 --seed 55   # đối chứng
```

| Trường | Nội dung |
|---|---|
| Trial | `swarm C-002@55`, run `E-swarm-20261117-77a6` (baseline v1), trial duy nhất fail của baseline (pass_rate 0.9857 = 69/70). |
| Triệu chứng | Lab 8 grader: `status resolved != denied`. Ledger ghi 20.000đ (1 refund), nhãn `denied` và 0đ. |
| Bước sai đầu tiên | Event 3, `model_override {"delay_days": 5}`: số ngày trong ticket ("giao trễ 5 ngày") ghi đè `delay_days` của DB cho đơn O-202. |
| Vì sao là bước *đầu tiên* | Event 1 (`handoff`) và event 2 (`investigator`, `lookup_order` thấy đơn O-202, đúng principal, `delay_days` từ DB) đều đúng. Event 4 (`quote 20.000đ`, clause SHIP-LATE-03) chỉ là hậu quả của số ngày bị ghi đè. |
| Failure mode | FM-03 (ticket_trust). Cơ chế: seed chia hết cho 5 làm swarm tham chiếu tin ticket. |
| Đối chứng | `fixed C-002@55`: không có `model_override`; event 3 là `quote {amount_vnd: 0, reason: no_entitlement}`, reply "chưa đủ điều kiện", ledger 0. |
| Regression test | `tests/test_lab9_graders.py::test_override_event_breaks_db_fact` (grader `DbFactKept`), và item `E-002` (claim C-002, `failure_modes=[FM-03]`, `provenance.from_trace="swarm C-002@55"`) trong eval set. Trên `seeded_regression`, `refund_amount_correct` và `pass_rate` fail trên C-002; trên `fixed` cả hai pass. |
| Chưa chắc chắn | Trace không cho biết vì sao MockLLM chọn tin ticket ở seed 55 (điểm yếu cài sẵn `seed % 5 == 0`); với model thật nguyên nhân có thể khác. Chỉ 1 trial, chưa đủ để ước lượng tần suất. |

Ledger đọc trước reply: reply của swarm tham chiếu không có event `reply`, nên chỉ ledger (20.000đ so với 0đ) và trace cho thấy lỗi.
