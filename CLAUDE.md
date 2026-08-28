# emse2026-multiagent-impact — bản đồ dự án

Paper: **"Participation Is Not Collaboration: Tracing Public Ownership After
Cross-Product Agent Review"**
Venue: **EMSE 2026 Special Issue — Agentic Software Engineering**, hạn 28/09/2026.

> Nguồn sự thật về nội dung bài là `paper/manuscript/main.tex` và
> `paper/manuscript/technical_appendix.tex`. Số liệu là các artifact trong
> `outputs/`. Đừng cache số vào file này.

---

## 1. Tìm file ở đâu

| Cần gì | Vào đâu |
|---|---|
| Bài chính (LaTeX) | `paper/manuscript/main.tex` |
| Online Resource 1 | `paper/manuscript/technical_appendix.tex` |
| Bảng phụ lục (sinh tự động, **đừng sửa tay**) | `paper/manuscript/generated_appendix_tables.tex` |
| PDF đã build | `build/pdf/` |
| Gói nộp Editorial Manager | `build/submission/emse_portal_staging/` |
| Hình của bài | `build/figures/FigN_v2.pdf` → copy sang `paper/manuscript/FigN.pdf` |
| Kết quả phân tích | `outputs/<tên-phân-tích>/` |
| Script chạy phân tích | `scripts/analysis/` |
| Script vẽ hình | `scripts/figures/` |
| Quyết định nghiên cứu | `docs/decisions/` |
| Kiểm toán, dữ liệu ngoài | `docs/audits/` |
| Hướng dẫn, codebook | `docs/guides/` |

**`build/` và `outputs/` khác nhau**: `outputs/` là *kết quả phân tích* (đọc bởi
bảng và hình); `build/` là *sản phẩm sinh ra* (PDF, hình đã render, gói nộp).
Trước đây hai thư mục tên `output/` và `outputs/` — đã đổi để hết nhầm.

---

## 2. Cấu trúc

```
scripts/
  build_submission.ps1      ← entry point: chạy hết rồi build PDF
  package_submission.ps1    ← entry point: đóng gói nộp
  analysis/                 run_*.py — mọi phân tích
  figures/                  visualize_*.py
  reporting/                sinh bảng phụ lục, notebook
  validation/               validate_*.py — cổng kiểm tra
  audit/                    prepare_*, profile_* — packet cho người code tay
  _superseded/              study TRƯỚC pivot, KHÔNG đụng vào

outputs/                    kết quả phân tích hiện hành
  _superseded/              kết quả study cũ (có file tên rq1_/rq2_/rq3_ trả lời
                            câu hỏi KHÁC — đừng đọc nhầm)

build/
  figures/  pdf/  submission/  qa/

src/multiagent_impact/      thư viện dùng chung
tests/                      pytest
```

---

## 3. Chạy lại

```powershell
uv sync
.\scripts\build_submission.ps1        # toàn bộ: phân tích → hình → bảng → PDF → gói
uv run --with pytest python -m pytest -q
```

Chạy lẻ một phân tích:
`.\.venv\Scripts\python.exe scripts\analysis\run_<tên>.py`

Thứ tự chạy đầy đủ nằm ở mục "Reproduce the headline analysis" trong `README.md`
— và bảng `tab:s-runorder` trong phụ lục được sinh **từ chính README đó**, nên
sửa README là bảng tự đổi theo. Thêm script mới vào README thì phải thêm luôn
một dòng vào `REPRODUCTION_STEPS` trong
`scripts/reporting/generate_technical_appendix_tables.py`, nếu không build sẽ fail.

---

## 4. Luật của dự án này

1. **Không sửa tay `generated_appendix_tables.tex`.** Sửa generator rồi chạy lại.
2. **Không dùng heredoc bash để vá file `.tex`/`.py`.** Đã hai lần làm `\textbf`
   biến thành `\t`+TAB mà LaTeX vẫn compile im lặng. Dùng file Python rồi chạy.
3. **Hình phải rộng đúng 372 pt** = `\textwidth` của `sn-jnl`, để in ra tỉ lệ 1:1.
   `scripts/figures/visualize_manuscript_figures.py` có cổng QA tự động chặn
   chữ tràn canvas, chữ dưới 7 pt, và hai annotation đè nhau.
4. **Mọi số trong bài phải truy được về một artifact trong `outputs/`.**
5. **Kết quả âm tính được giữ lại**, ghi trong
   `protocol/experiment_disposition_20260826.csv` và bảng disposition ở phụ lục.
   Không im lặng bỏ đi.
6. **Không đụng `_superseded/`** trừ khi cố ý đọc lịch sử.

---

## 5. Trạng thái

Bài đã reproducible và compile sạch. Còn mở:

- Metadata tác giả (affiliation, email, ORCID, CRediT), declarations, ethics.
- Artifact DOI — `10.5281/zenodo.22140821`, reserved on a Zenodo draft, not yet published.
- Editorial Manager từng hiện cảnh báo "site under development" (26/08/2026),
  cần kiểm tra lại.
- Semantic coding của 167 locus vẫn pending — chỉ bắt buộc nếu thêm claim về
  duplication/complementarity/contradiction. Bài hiện tại **không** có claim đó.

Chi tiết: `paper/SUBMISSION_READINESS.md`.

Repo này **chưa có commit git nào**. Nên commit trước khi làm gì lớn.
