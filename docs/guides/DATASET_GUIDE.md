# Hướng dẫn nhanh về AIDev-7.6M

## Tóm tắt trong 30 giây

AIDev có hai tầng dữ liệu, không phải một bảng lớn duy nhất:

1. **Full corpus:** 7,685,281 pull request (PR). Tầng này phù hợp để nghiên cứu adoption, agent, contributor, trạng thái merge và thời gian trên toàn bộ dataset.
2. **AIDev-pop:** 361,296 PR trong repository có hơn 100 stars. Tầng này có thêm review, comment, timeline, commit, file change, task type và linked issue. Paper hiện tại dùng tầng này.

Không nối các bảng `pr_*` với `all_pull_request` để “tăng coverage”. Các bảng giàu tương tác được thiết kế quanh `pull_request` của AIDev-pop.

![AIDev schema and coverage](../outputs/figures/dataset_map_and_coverage.png)

## Sơ đồ nối bảng

```text
repository ── id = repo_id ── pull_request ── id = pr_id ─┬─ pr_reviews
                                                          ├─ pr_comments
                                                          ├─ pr_timeline
                                                          ├─ pr_commits
                                                          ├─ pr_commit_details
                                                          ├─ pr_task_type
                                                          └─ related_issue ── issue

pr_review_comments
  └─ pull_request_review_id = pr_reviews.pull_request_review_id
       └─ pr_reviews.pr_id = pull_request.id
```

Điểm quan trọng nhất: `pr_review_comments` không có `pr_id`. Muốn biết inline comment thuộc PR nào, phải đi qua review ID.

## Tầng full corpus

| Bảng | Số dòng | Một dòng là gì? | Nối bằng | Feature chính |
|---|---:|---|---|---|
| `all_pull_request` | 7,685,281 | một PR | backbone | agent, author, state, created/closed/merged time, repository |
| `all_repository` | 957,209 | một repository | `all_pull_request.repo_id = all_repository.id` | language, license, fork, stars, forks |
| `all_user` | 399,962 | một GitHub account | `all_pull_request.user_id = all_user.id` | login, followers, following, account age |

Tầng này có coverage rộng nhất nhưng không có đủ event để dựng review-response topology.

## Tầng AIDev-pop dùng cho paper

| Bảng | Số dòng | Grain | Nối về PR | Feature dùng được |
|---|---:|---|---|---|
| `pull_request` | 361,296 | một PR | backbone | agent tạo PR, author account, repository, state, timestamps |
| `repository` | 25,402 | một repository | `pull_request.repo_id = repository.id` | project context |
| `pr_reviews` | 281,170 | một submitted review | `pr_id = pull_request.id` | reviewer, state, review batch, submitted time |
| `pr_review_comments` | 289,780 | một inline comment | qua `pull_request_review_id` | exact parent reply, path, position, commit snapshot, text |
| `pr_comments` | 373,549 | một PR comment | `pr_id = pull_request.id` | public discussion, actor type, time |
| `pr_timeline` | 3,018,358 | một lifecycle event | `pr_id = pull_request.id` | assignment, labels, force-push, close/merge events |
| `pr_commits` | 718,779 | một commit trong PR | `pr_id = pull_request.id` | SHA, author, message; commit time không đủ an toàn cho sequence |
| `pr_commit_details` | 6,112,623 | một file trong một PR commit | `pr_id`, có thể thêm `sha` | filename, additions, deletions, patch |
| `pr_task_type` | 32,702 | một classified PR | `id = pull_request.id` | task type, reason, confidence |
| `related_issue` | 38,006 | một PR--issue link | `pr_id = pull_request.id` | liên kết PR với issue |
| `issue` | 29,111 | một issue | `related_issue.issue_id = issue.id` | title, body, state, timestamps |

## Feature dùng cho ba RQ

| Câu hỏi | Evidence tối thiểu | Feature chính | Không được suy ra |
|---|---|---|---|
| RQ1: participation hay handoff? | `pull_request` + reviews + inline/PR comments + timeline | author product, reviewer product, trigger time, parent ID, review-batch ID, actor type | hai product cùng xuất hiện không chứng minh collaboration |
| RQ2: ai bridge product boundary? | RQ1 events + toàn bộ submitted-review history trong repository | first user account, prior different-PR review count, recency | user account không chứng minh thao tác hoàn toàn thủ công |
| RQ3: hybrid relay và later state | 48-hour route + merge từ giờ 48 đến ngày 30 | early owner route, trigger age, pre-trigger event counts, later merge | association không phải causal effect hoặc code quality |

## Coverage thật của rich tables

Mẫu số là 361,296 PR trong `pull_request`.

| Nhóm feature | PR có ít nhất một row | Coverage |
|---|---:|---:|
| Timeline events | 197,471 | 54.66% |
| Commits | 197,335 | 54.62% |
| File-level changes | 197,330 | 54.62% |
| PR comments | 110,011 | 30.45% |
| Submitted reviews | 83,081 | 23.00% |
| Inline review comments | 47,251 | 13.08% |
| Task classification | 32,702 | 9.05% |
| Linked issues | 28,987 | 8.02% |

Missing row không tự động có nghĩa là “không có hoạt động”. Vì vậy paper báo mẫu số cho từng construct và không dùng raw product ranking.

## Các join contract quan trọng

1. **Exact reply:** `in_reply_to_id` của child comment phải bằng đúng event ID của trigger. Reply vào comment khác trên cùng PR không được tính.
2. **New review round:** review sau trigger phải có review-batch ID khác trigger. Review chứa inline trigger không được tự trả lời chính nó.
3. **Repository history:** cùng account, cùng repository, PR khác focal PR, và review time phải nhỏ hơn trigger time.
4. **Collision locus:** cùng PR, `original_commit_id`, `path`, và `original_position`; chỉ dùng top-level inline comments.
5. **Outcome landmark:** route chỉ dùng 48 giờ đầu; merge outcome bắt đầu sau giờ 48.

## Ba lỗi dễ mắc

1. **Nối theo row order.** Luôn dùng ID; thứ tự row không mang ý nghĩa join.
2. **Đếm raw rows như PRs.** Một PR có thể có nhiều comments, reviews, commits và file changes. Phải aggregate về `pr_id` khi model ở mức PR.
3. **Xem missing feature là zero.** Hãy tạo coverage flag và báo mẫu số của subset.

## Artifact để kiểm tra lại

- `outputs/tables/dataset_table_inventory.csv`: inventory, grain, key và role của từng bảng.
- `outputs/tables/dataset_feature_dictionary.csv`: feature và data type.
- `outputs/tables/dataset_join_coverage.csv`: coverage của rich tables.
- `outputs/tables/dataset_full_join_quality.csv`: chất lượng join ở full corpus.
- `outputs/figures/dataset_map_and_coverage.pdf`: schema và coverage figure.

Dataset được pin tại revision `37bbe1533e26cc1e1374917dba1186d1c8a4dc81`. Khi đổi revision, cần chạy lại schema profile, join checks và toàn bộ headline analysis.
