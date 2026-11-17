# Judge audit

Chạy: `python -m lab9.judge --csv <file> --audit 5` (backend replay, không cần API key). Người thực hiện: Nguyễn Tuấn Bách (2A202603596).

| Tiêu chí | n | κ | Precision | Recall | Đạt FLOORS (κ≥0.6, P≥0.8, R≥0.7)? | Quyết định |
|---|---|---|---|---|---|---|
| tone_ok | 100 | 0.757 | 0.857 | 0.800 | **Đạt** (tp 24, fp 4, fn 6, tn 66) | **Dùng** (tín hiệu phụ, không làm gate chặn tiền) |
| helpful | 100 | 0.375 | 1.000 | 0.300 | **Không đạt** (tp 9, fp 0, fn 21, tn 70) | **Loại** khỏi gate |

Tỉ lệ FAIL quan sát của `tone_ok` là 0.28; hiệu chỉnh Rogan-Gladen ra 0.30. Với `helpful`, quan sát 0.09 nhưng hiệu chỉnh ra 0.30: judge bỏ sót hơn 2/3 lỗi thật, nên con số "9% lỗi" thấp hơn thực tế khoảng ba lần.

## ≥5 case audit thủ công (tone_ok)
| # | Case | Judge nói | Người nói | Ai đúng? | Ghi chú / sửa rubric |
|---|---|---|---|---|---|
| 1 | H-008 "Em đã hoàn tiền cho anh rồi nha…" | PASS | FAIL | Người | Xưng "em", "nha" quá suồng sã. Rubric thêm: xưng hô phải là "LogiX" / "anh/chị", cấm "em", "bạn", "nha", "nhé". |
| 2 | H-017 "Dạ, bạn ơi LogiX đã hoàn 25.000đ… rồi nha" | PASS | FAIL | Người | Gọi khách là "bạn". Cùng điều khoản xưng hô ở dòng 1. |
| 3 | H-029 "Dạ, vui lòng chờ… không cần nhắn thêm." | PASS | FAIL | Người | Giọng ra lệnh bị che bởi "Dạ, vui lòng". Rubric thêm: câu phủ định hướng dẫn khách ("không cần…") là FAIL dù có từ lịch sự. |
| 4 | H-042 "Dạ, đơn O-808 đã hoàn 120.000đ. Tiền về trong 3–5 ngày ạ." | FAIL | PASS | Người | Ngắn nhưng đủ ý; judge phạt vì thiếu xin lỗi. Rubric sửa: không bắt buộc xin lỗi khi yêu cầu được chấp nhận. |
| 5 | H-051 "Dạ, LogiX đã refund 90.000đ…" | FAIL | PASS | Người | "refund" là từ CS LogiX cho phép. Rubric thêm: thuật ngữ nghiệp vụ tiếng Anh trong danh sách cho phép không bị phạt. |
| 6 | H-063 "…và sẽ hoàn thêm cho anh/chị ạ." | PASS | FAIL | Người | Hứa hẹn ngoài kết quả hệ thống. Đây là lỗi nội dung, không phải giọng điệu; chuyển sang grader code (FM-08, `ReplyMatchesLedger`) thay vì để judge tone gánh. |

Ở cả 6 case, nhãn của người đúng (ghi chú trong CSV nêu lý do), nên hành động là sửa rubric của judge, không sửa nhãn.

## Kết luận
- **Loại `helpful` khỏi gate**: recall 0.30 < 0.70 và κ 0.375 < 0.6. 21/30 reply lỗi thật bị judge cho PASS, gồm reply nêu sai số tiền (HL-015: 55.000đ so với ledger 40.000đ; HL-020: 90.000đ so với 120.000đ) và các câu xin lỗi dài dòng không giải quyết gì (HL-016, HL-028, HL-035, HL-041). Precision 1.0 không cứu được: khi judge nói FAIL thì đúng, nhưng nó hầu như không bao giờ nói. Dùng nó làm gate sẽ cho lọt phần lớn lỗi.
- **Sai số tiền không bao giờ giao cho judge**: đã có grader code `ReplyMatchesLedger` (FM-08) so số tiền trong reply với ledger.
- **Dùng `tone_ok`** có điều kiện: đạt cả ba ngưỡng, nhưng vùng bất đồng tập trung ở xưng hô và giọng ra lệnh, nên cập nhật rubric theo bảng trên rồi chấm lại trước khi tin con số.
- Rủi ro còn lại: judge chỉ được kiểm trên dữ liệu replay đã công khai (n=100, 30 FAIL thật), chưa có held-out mới. Khoảng tin cậy của κ với n này rộng. Cần nhãn người mới cho rubric đã sửa.
