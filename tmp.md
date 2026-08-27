2Faculty of Information and Technology, Ho Chi Minh City University of Science
(HCMUS), Vietnam
3Vietnam National University - Ho Chi Minh City (VNU-HCM), Vietnam

affiliate nè : 
rồi duy minh với trung kiet là co-first auth á : 

Tận dụng multiagent nè : 

Nè coi adress hết đi nè :( đặc biệt mấy cái limitation , adress chạy được exp này kia thì coi chạy exp các thứ các kiểu cho chuẩn đi nè chạy hết verify hết , adress hết limitation của paper luôn nè ) :
(rồi cảm giác paper bây giờ cái caption của figure quá dài nè cảm giác hơi dài quá không có chuẩn chuyên nghiệp nè ) 


Mình đã audit **toàn bộ 29 trang**, soi cả logic nội tại, sample flow, denominator, wording, statistics, threats, references, figures, reproducibility, và đối chiếu các nguồn công khai hiện tại. Kết luận thẳng:

# Verdict

**Paper này có chất để đi journal Q1, đặc biệt EMSE, nhưng bản PDF hiện tại CHƯA nên submit.**

Không phải vì idea yếu. Ngược lại, **ý tưởng khá tốt và câu chuyện empirical rất có giá trị**. Vấn đề nằm ở chỗ hiện tại vẫn còn vài điểm mà reviewer Q1 có thể bắt rất mạnh, trong đó có **2 nhóm lỗi “must-fix”**:

1. **Sample-flow / denominator chưa đóng kín hoàn toàn**, đặc biệt `4,824 → 3,942 → 3,526 → 1,067`.
2. **RQ3 và RQ4 vẫn có vấn đề về estimand/selection/time ordering**, dù paper đã ý thức và thừa nhận khá nhiều limitation.

Ngoài ra có một loạt lỗi submission-readiness rất rõ: metadata/declarations còn `PENDING`, nhiều arXiv ID format sai, và bibliography cần rà lại.

---

# 1. Cái mình thích: core story thực sự khá mạnh

Paper có một insight rất rõ:

> **co-presence ≠ collaboration ≠ connected interaction**

Đây là framing tốt. Paper không chỉ đếm “hai agent cùng xuất hiện”, mà cố dựng một **evidence ladder** từ presence → exact reply → actor → later state. Phần này khá thuyết phục và có tính methodological contribution. 

Đặc biệt, authors **không cố cứu hypothesis khi placebo phá nó**. RQ3 thừa nhận anchor chính xác không phải thứ tạo ra association; chính paper kết luận rằng “precision bought attribution, not prediction.” Đây là kiểu self-falsification khá đẹp đối với empirical SE. 

Phần limitations cũng khá honest: task difficulty, maintainer intent, private communication, scripted user accounts, selection bias đều được thừa nhận. 

**Đây là điểm khiến mình nghĩ paper đáng cứu để Q1, chứ không phải paper cần đổi topic.**

---

# 2. BLOCKER #1 — Sample flow đang bị “đứt mạch”

Đây là thứ mình sẽ sửa đầu tiên.

Paper nói:

* 8,608 cross-product trigger PRs.
* 4,824 có inline comment làm first cross-product review → “therefore in scope”. 
* Figure 4 lại dùng **3,942 PRs**. 
* Threats lại nói cross-product inline triggers là **3,526**, và 13/3,526 là mid-thread. 
* Hour-48 cohort là **1,067**. 

Các con số này **có thể hoàn toàn coherent**, thậm chí mình nghi là pipeline thực tế của các bạn là:

`8,608`
→ `4,824` first cross-product inline trigger
→ `3,942` có đủ 30-day follow-up
→ `3,526` trigger mở thread / edge-eligible
→ `1,067` còn open tại hour 48

Nhưng **paper không viết flow này ra một cách explicit**.

Đối với reviewer, hiện tại sẽ xuất hiện câu hỏi:

> “Where did 4,824 become 3,942?”
> “Why is mid-thread measured over 3,526 rather than 4,824 or 3,942?”
> “Why is Figure 4 described as all cross-product inline-trigger PRs when its denominator is 3,942?”

Đây là một **major transparency problem**, không nhất thiết là statistical error, nhưng cực dễ làm reviewer nghi ngờ pipeline.

### Cần làm

Thêm một **study-flow figure/table** kiểu:

```text
8,608 cross-product PRs
        |
        | first cross-product event is inline review comment
        v
4,824 inline-trigger PRs
        |
        | sufficient 30-day follow-up
        v
3,942 follow-up eligible PRs
        |
        | trigger opens its own review thread
        v
3,526 edge-eligible PRs
        |
        | still open at hour 48
        v
1,067 RQ3 outcome cohort
```

và ở mỗi arrow ghi **exclusion count + exact reason**.

Đây sẽ biến một điểm “hơi đáng ngờ” thành một điểm rất mạnh về reproducibility.

---

# 3. BLOCKER #2 — Figure 4 đang dùng wording hơi sai so với denominator

Caption hiện nói:

> “Every cross-product inline-trigger PR is followed…”

nhưng figure lại báo **3,942 PRs**, trong khi phần method trước đó nói có **4,824** first inline cross-product triggers.  

Nếu 3,942 là cohort sau 30-day observability filter thì phải viết đúng là:

> “Every cross-product inline-trigger PR with sufficient follow-up…”

Chỉ một chữ `eligible` thôi nhưng cực quan trọng.

---

# 4. BLOCKER #3 — RQ3 đang là observational association, nhưng hour-48 conditioning rất dễ bị reviewer đánh

Paper làm:

1. Chỉ giữ PR còn open tại hour 48.
2. Xác định có reply trước hour 48 hay không.
3. Xem merge sau hour 48.

Mục tiêu là đảm bảo exposure xảy ra trước outcome. Ý này đúng và paper giải thích khá tốt. 

Nhưng đổi lại bạn đang **conditioning on surviving to hour 48**.

Nghĩa là cohort `1,067` không còn đại diện cho toàn bộ cross-product population nữa; chính paper cũng thừa nhận nó là “slower-moving part”. 

Worse nữa, “reply within 48h” và “still open at 48h” có thể liên quan tới cùng underlying engagement process.

Cho nên:

> **17.3 pp later merge** không nên được đọc như một generic effect của “reply”.

Paper hiện nay đã khá cẩn thận, nhưng mình vẫn muốn wording mạnh hơn:

> **conditional association among PRs that remained open 48 hours after the trigger**

thay vì để reviewer tự phát hiện.

---

# 5. RQ3 có một điểm còn nguy hiểm hơn: exact edge bị falsify

Đây là một trong những điểm thú vị nhất của paper.

Bạn xây dựng hypothesis rằng:

> exact reply to trigger = strongest measurable connection.

Nhưng placebo cho thấy:

* reply anchored elsewhere: **17.9 pp**
* exact trigger edge: **18.9 pp**
* difference ≈ **1 pp**, CI spans zero
* anchor shuffle: null centered around **16.8 pp**, observed 17.3 pp. 

Tức là:

**anchor itself contributes basically nothing predictive.**

Paper có thừa nhận điều này. Rất tốt.

Nhưng abstract/conclusion vẫn có wording hơi dễ khiến người đọc nghĩ rằng:

> “exact addressed edge → later merge”

trong khi kết quả mạnh nhất thực ra là:

> **a human reply / human attention signal → later merge**,
> not **the precise addressed edge → later merge**.

Đây là khác biệt rất lớn.

Mình sẽ xem đây là **claim-alignment issue**, không phải data problem.

---

# 6. 128 reply events → 109 exposed PRs → 105 user-written replies: cần khóa unit of analysis

Paper có:

* 128 exposed reply events.
* 105 đến từ ordinary users.
* 13 triggering product self-reply.
* 7 other bots.
* 3 other mapped products. 

Sau đó lại nói:

* 109 exposed PRs.
* 92 có exactly one reply.
* 17 không xác định được exact answering relation. 

Con số này **có thể đúng** vì một PR có thể có nhiều reply events.

Nhưng reviewer sẽ hỏi:

> Are the statistical units PRs or reply events?

Phải ghi cực rõ:

* primary unit = **PR**
* 128 = reply events
* 109 = PRs with ≥1 exposed-thread reply
* 105 = user-authored reply events
* 59 = substantive user-written reply events
* 56 = PRs containing ≥1 substantive reply

Hiện tại reader phải tự reconstruct.

---

# 7. RQ2 có một structural-comparability issue khá nặng

Đây là điểm mình muốn các bạn kiểm tra trong code.

Paper nói exact reply chỉ có thể xảy ra nếu trigger là **first comment of its thread**.

Cross-product:

> chỉ 13 / 3,526 là mid-thread.

Same-product:

> **46%** sit mid-thread. 

Như vậy nếu Figure 3 so sánh:

> “The review point gets a reply”

giữa cross-product và same-product,

mà same-product side vẫn chứa rất nhiều mid-thread triggers,

thì outcome đó có thể có **structural zeros**.

Paper có nói:

> restriction bites hard for same-product triggers.

Nhưng mình chưa thấy trong main manuscript một chỗ đủ explicit để nói:

> “For the reply outcome, we therefore restricted both arms to thread-opening triggers.”

Nếu **đúng là code đã làm như vậy**, phải viết rõ.

Nếu **chưa làm**, đây là **major methodological fix**.

Và đừng dựa vào câu “Figure 3 outcome -0.9 pp” để biện minh; đây chính là kiểu subtle selection issue reviewer Q1 rất thích soi.

---

# 8. RQ2 “general finding” đang hơi overclaimed

Các bạn viết:

> “The direction, then, is general by our own standard.” 

Nhưng ngay sau đó:

* hai product-pair lớn nhất gần −20 và −26 pp,
* bốn pair còn lại khoảng ±6 pp,
* chỉ **một pair** có CI tự thân exclude zero. 

Nói “general by our own standard” technically defensible nhưng **không đẹp về journal writing**.

Reviewer có thể đọc thành:

> “They define their own criterion, then declare generality.”

Nên đổi concept thành:

> **directionally stable under the prespecified leave-one-repository / leave-one-pair sensitivity criterion**

và ngay lập tức thêm:

> **the magnitude is heterogeneous and concentrated in two author-product strata.**

Thực tế paper đã có dữ liệu để nói câu này rất đẹp. 

---

# 9. RQ4 — 13.3 pp không phải phép trừ nhìn trên Figure

Figure 6:

* cross-product: 12.7 → 28.3 = **+15.6 pp**
* same-product: 21.3 → 19.8 = **−1.5 pp**

Raw difference-in-differences:

**15.6 − (−1.5) = 17.1 pp**

Nhưng paper báo:

**13.3 pp (95% CI 4.4–22.2)**.

Điều này **không phải contradiction** nếu 13.3 là **adjusted within-repository/month DID**. Text thực sự nói như vậy. 

Nhưng figure hiện chưa nói đủ rõ.

Reviewer nhìn graph sẽ làm phép:

`28.3−12.7 − (21.3−19.8) = 17.1`

rồi hỏi:

> “Why does manuscript report 13.3?”

### Fix rất đơn giản

Figure panel B đổi label thành:

> **Adjusted difference-in-differences: +13.3 pp**

và panel A giữ raw rates.

Hoặc caption:

> “Raw differences are shown in Panel A; Panel B reports the repository/month-adjusted difference-in-differences.”

Cực kỳ nên làm.

---

# 10. RQ4 “pre-existing issue link” thực ra chưa chứng minh được là pre-existing

Paper nói issue link là thứ có trước review, rồi từ đó suy luận cơ chế context.

Nhưng threat section lại thú nhận:

> PR bodies can be edited
> dataset has no timestamp for the link
> cannot prove every link was present before trigger. 

Đây là **một contradiction về wording, không phải data**.

Bạn không nên gọi:

> “pre-existing task context”

như một established fact.

Nên gọi:

> **issue linkage observed in the PR body**

và nếu có thể:

> “intended to approximate pre-review task context”

Còn câu:

> “The one thing under a vendor’s control…”

mình thấy quá causal/prescriptive so với evidence hiện có.

Paper itself says:

> “These are links in observed data, not causes.” 

Vậy discussion phải obey chính statement đó.

---

# 11. E-value: numerical story có vẻ plausible, nhưng reporting chưa đủ

Paper báo:

> E-value = 2.27
> interval E-value = 1.67. 

Về magnitude thì nó **không có vẻ vô lý** với relative risk khoảng `0.55/0.379 ≈ 1.45`.

Nhưng trong manuscript hiện tại chưa đủ rõ:

* E-value tính từ exact estimand nào?
* risk ratio hay odds ratio?
* adjusted estimate hay crude?
* CI nào được dùng?
* exact formula/software/version?

Đừng chỉ viết “E-value 2.27”.

Journal-grade nên report:

> adjusted risk ratio = X.XX (95% CI …), E-value = 2.27, E-value for CI limit = 1.67

hoặc nếu model không cho RR trực tiếp, nói rõ conversion.

---

# 12. Statistical Methods hiện chưa đủ reproducible cho Q1

Paper nói:

> “Main intervals cluster or resample by repository.”
> “Outcome models adjust for product, channel or month…” 

Nhưng reviewer vẫn thiếu:

* exact model formula
* link function
* covariate list
* matching algorithm implementation
* whether replacement/no replacement
* caliper
* balance diagnostics
* number of bootstrap repetitions
* treatment of ties
* missing-data handling
* multiple-testing policy
* exact definition of “public activity”
* exact definition of “branch movement”
* exact event priority when two events have identical timestamp

Với paper methodological/measurement như này, **Online Resource 1 không nên là nơi duy nhất chứa toàn bộ model specification**.

Main paper ít nhất phải có:

> model equation + estimand + cohort + clustering level.

---

# 13. RQ2 matching cần thêm balance diagnostics

Matching:

* same repository
* same PR-author account
* same author product
* same source channel
* same month
* nearest time without replacement. 

Cách này nghe hợp lý.

Nhưng reviewer sẽ hỏi:

> Did matching actually balance the pre-trigger variables?

Phải có bảng kiểu:

| Variable              | Before matching | After matching |
| --------------------- | --------------: | -------------: |
| PR age                |               … |              … |
| prior review activity |               … |              … |
| prior comments        |               … |              … |
| repo activity         |               … |              … |
| author history        |               … |              … |

Ít nhất standardized mean difference.

Không có balance table thì “matched pairs” mới chỉ là **matching rule**, chưa phải evidence rằng confounding được giảm.

---

# 14. RQ3 whole-population Figure 4 có một insight hay nhưng presentation hơi dangerous

Figure 4 báo:

* reply elsewhere = 89%
* trigger thread = 85%
* no inline reply = 78%. 

Paper đã giải thích rằng curves cross và 48h cohort là slower PRs.

Điểm này hay.

Nhưng cần viết mạnh hơn rằng **the 17.3 pp effect is not population-wide**.

Bạn đã có chính dữ liệu:

> by day 30 the difference is only a few points. 

Đây nên thành **central interpretation**, chứ không phải footnote.

---

# 15. “The reply marks human attention” — hợp lý hơn “human collaboration”

Một điểm rất đáng sửa:

Paper title vẫn dùng:

> “Participation Is Not Collaboration”

và trong intro nói:

> “Almost none of it is teamwork.”

Nhưng data thực sự cho phép claim mạnh nhất là:

> **no evidence of observable public agent-to-agent handoff**

chứ không phải:

> **almost no teamwork**

Vì private communication/shared state/private orchestration hoàn toàn invisible.

Paper thực sự biết limitation này và nói rõ public trace không chứng minh shared memory/joint plan/private talk. 

Do đó title vẫn provocative tốt, nhưng prose nên nhất quán với scope:

**“Participation is not collaboration in the public trace”**

hoặc:

> “Co-presence is not evidence of public coordination.”

Câu này sẽ reviewer-proof hơn.

---

# 16. External replication gate: rất honest nhưng hiện tại không tạo validation

Paper nói external corpus:

> every candidate PR was already in ours → replication gate failed. 

Mình thích việc các bạn không giả vờ gọi nó là replication success.

Nhưng đừng để discussion gọi đây là “replication” quá mạnh.

Đây là:

> **external schema/identity cross-check**

chứ không phải independent replication.

Threat section đã nói gần như vậy. 

---

# 17. AIDev dataset verification: source là thật, nhưng terminology “AIDev-pop” cần khóa

Mình check trực tiếp source hiện tại của AIDev.

AIDev v5 đúng là:

* **7,685,281 PRs**
* **961,168 repositories**
* 6 agents: Codex, Copilot, Claude Code, Cursor, Google Jules, Devin
* cutoff **March 31, 2026**. ([Hugging Face][1])

Nên phần:

> “AIDev-7.6M” + six products + March 31, 2026

là phù hợp source hiện tại. 

Tuy nhiên, có một điểm phải cực kỳ cẩn thận:

AIDev repository công khai có một **AIDev-pop (>100 stars)** subset. Version cũ được công khai là **33,596 PRs / 2,807 repos**. ([GitHub][2])

Paper của bạn lại gọi:

> “the richer AIDev-pop layer: 361,296 PRs from repositories with more than 100 stars.” 

Mình **chưa tìm được public source hiện tại xác nhận con số 361,296** cho v5.

Điều đó không chứng minh `361,296` sai — có thể các bạn tự xây lại >100-star population trên v5 — nhưng khi submit phải làm rõ:

> **Is 361,296 an official AIDev v5 AIDev-pop count, or our own >100-star derivation?**

Nếu là custom derivation, đừng gọi đơn giản là:

> `AIDev-pop`

mà nên gọi:

> **our >100-star population subset of AIDev v5**

và báo:

* số repositories
* PR count
* per-agent counts
* exact star snapshot/source
* filtering code.

Đây là một **high-priority reproducibility clarification**.

---

# 18. Related work phải update rất gấp

Có một development cực quan trọng:

**AI-to-AI Code Reviews of GitHub Pull Requests**, Selvanayagam & Ghaleb, arXiv:2608.21311, vừa được public **21 Aug 2026**, tức chỉ vài ngày trước. Nó có:

* 248,641 AI-attributed PRs đã nhận AI review
* 45,269 cross-product
* 208,145 same-product
* 4,773 cả hai
* latency cross-product vs same-product
* product-pair analyses. ([arXiv][3])

Đây là **nearest-neighbor paper** của các bạn, không né được.

Tin tốt là paper của các bạn **không bị giết bởi nó**, vì contribution khác:

| Selvanayagam & Ghaleb                    | Your paper                    |
| ---------------------------------------- | ----------------------------- |
| prevalence / closed-loop AI-to-AI review | public connection / ownership |
| AI event attribution                     | exact reply-target anchoring  |
| latency / review output                  | handoff vs human bridge       |
| large-scale pairing                      | evidence ladder               |
| characterization                         | falsification / placebo       |
| agent-agent presence                     | human attention + later state |

Nhưng related work hiện tại phải viết rõ paper này là **nearest empirical baseline**, không thể chỉ gọi chung “one recent study”.

---

# 19. Zhong 2026 cũng làm novelty pressure tăng

Có ít nhất hai work rất gần:

**Human-AI Synergy in Agentic Code Review**, arXiv:2603.15911, dùng 278,790 review conversations trên 300 OSS projects. ([arXiv][4])

**From Human-Centric to Agentic Code Review**, arXiv:2607.13196, nghiên cứu 1.02M reviewed PRs trên 207 projects và review sequences. ([arXiv][5])

Vì vậy novelty claim không nên là:

> “we show humans still participate”

Cái đó đã crowded.

Novelty nên là:

> **we operationalize public cross-product coordination as an event-anchored trace problem and explicitly test whether the strongest machine-checkable connection carries incremental predictive information beyond generic human response.**

Đó mới là phần khác biệt.

---

# 20. Reference list có lỗi format thật

Mình đã check các arXiv references. Có một lỗi lặp theo pattern:

Ví dụ paper ghi:

> `arXiv:260721997`

nhưng DOI lại đúng:

> `10.48550/arXiv.2607.21997`

ArXiv chính xác là **2607.21997**. ([Hugging Face][6])

Tương tự trong PDF có hàng loạt entry kiểu:

* `arXiv:260816801` → `2608.16801`
* `arXiv:260115195` → `2601.15195`
* `arXiv:260602875` → `2606.02875`
* `arXiv:260404059` → `2604.04059`
* `arXiv:260703316` → `2607.03316`
* `arXiv:260208915` → `2602.08915`
* `arXiv:260818167` → `2608.18167`
* `arXiv:260706065` → `2607.06065`
* `arXiv:260704697` → `2607.04697`
* `arXiv:260713196` → `2607.13196`
* `arXiv:260315911` → **2603.15911**
* `arXiv:260613175` → `2606.13175`

Trong nhiều trường hợp DOI/URL phía sau đã đúng, nên đây là **formatting corruption**, nhưng phải sửa hết.

EMSE hiện yêu cầu DOI đầy đủ khi available và reference list phải chỉ chứa work đã published hoặc accepted. ([Springer][7])

---

# 21. Submission-readiness: hiện tại chắc chắn chưa pass

PDF vẫn còn:

* affiliation pending
* institution pending
* corresponding email pending
* funding pending
* competing interests pending
* DOI artifact pending
* ethics wording pending
* consent pending
* author contributions pending. 

Cái này **không được phép tồn tại trong submission version**.

Đặc biệt EMSE ghi rõ submissions thiếu relevant declarations có thể bị trả lại là incomplete. ([Springer][7])

Và title page của EMSE cần affiliation + active corresponding-author email. ([Springer][7])

---

# 22. AI-use disclosure hiện tại là điểm cộng, không phải điểm trừ

Paper nói Codex được dùng cho:

* data inspection
* code
* testing
* literature search
* figures
* editing

và human authors verified sources, reran analysis, checked figures/text. 

Điều này khá ổn.

EMSE hiện nói LLM **không đáp ứng authorship criteria**, và AI usage nên được document trong Methods. ([Springer][7])

Vậy section này nên giữ.

---

# 23. Figure quality: nhìn chung tốt

Mình đã kiểm tra rendered PDF:

* không thấy clipping nghiêm trọng
* không thấy overlapping text
* figure numbering ổn
* captions có đầy đủ
* visual narrative khá sạch

Figure 5 và Figure 6 đặc biệt khá tốt về storytelling.

Nhưng ở journal production size:

* Figure 5 labels hơi nhỏ/dense
* Figure 4 có quá nhiều explanatory text
* Figure 3 panel B cần làm rõ denominator
* Figure 6 cần label adjusted DID

EMSE yêu cầu figure lettering phải readable ở final size và artwork phải phù hợp kích thước publication. ([Springer][7])

---

# 24. EMSE/Q1 fit: rất ổn

Nếu mục tiêu của bạn là **Empirical Software Engineering (EMSE)** thì fit khá đẹp.

EMSE tự mô tả là journal tập trung vào empirical software-engineering research. ([Empirical Software Engineering][8])

Current Scopus-based rankings list EMSE là **Q1 trong Computer Science–Software**. ([WUR Library][9])

Thậm chí AIDev maintainers hiện đang công khai mời work sử dụng AIDev cho **EMSE 2026 Special Issue on Agentic Software Engineering**, deadline cuối được ghi là **30 Sep 2026**. ([Hugging Face][1])

Nên nếu target của bạn là EMSE, **topic fit hiện tại là rất tốt**.

---

# 25. Có một điểm rất hay nhưng nên biến thành “central methodological contribution”

Theo mình, thứ mạnh nhất của paper **không phải finding “human replies more often”**.

Finding đó sẽ sớm bị crowded.

Thứ mạnh hơn là:

### Evidence ladder + falsification

Bạn chứng minh:

```text
Two products on one PR
        ↓
cross-product review
        ↓
exact reply
        ↓
who wrote it?
        ↓
later merge
```

và sau đó cho thấy:

```text
exact anchor
      ↓
   placebo
      ↓
does NOT add predictive power
```

Đây là contribution kiểu:

> **measurement itself changes the scientific conclusion.**

Paper đã viết điều đó khá rõ. 

Mình sẽ push contribution này lên mạnh hơn nữa.

---

# 26. Những thứ hiện tại mình đánh giá “đã ổn”

| Thành phần            | Verdict                                                  |
| --------------------- | -------------------------------------------------------- |
| Research question     | 🟢 Strong                                                |
| Dataset choice        | 🟢 Excellent                                             |
| Timeliness            | 🟢 Excellent                                             |
| Core empirical story  | 🟢 Strong                                                |
| Falsification mindset | 🟢 Very strong                                           |
| Threats to validity   | 🟢 Better than average                                   |
| RQ1                   | 🟢 Good                                                  |
| RQ2                   | 🟡 Need comparability clarification                      |
| RQ3                   | 🟡 Important methodological tightening                   |
| RQ4                   | 🟡 Strong result, but causal wording too strong          |
| Figures               | 🟢 Good                                                  |
| Novelty               | 🟢/🟡 Strong but must update against Aug-2026 literature |
| Statistics reporting  | 🟡 Under-specified                                       |
| Reproducibility       | 🔴 Not submission ready                                  |
| Declarations          | 🔴 Not submission ready                                  |
| References            | 🟡 Multiple format errors                                |
| Q1 journal fit        | 🟢 Strong                                                |

---

# 27. Các lỗi mình xếp theo mức độ nguy hiểm

## 🔴 MUST FIX BEFORE SUBMIT

**1.** Explicit sample-flow `8,608 → 4,824 → 3,942 → 3,526 → 1,067`.

**2.** Resolve the same-product mid-thread structural-zero issue in RQ2.

**3.** Explicitly identify PR/event/person as statistical unit everywhere.

**4.** Fully specify RQ2/RQ3/RQ4 models and estimands.

**5.** Reframe RQ3 as conditional observational association, not effect.

**6.** Reframe RQ4 issue-link result as association, because link timestamp isn't observed.

**7.** Explain exactly what `361,296 AIDev-pop` means.

**8.** Replace every `PENDING`.

**9.** Fix all malformed arXiv identifiers.

**10.** Upload real artifact/code/DOI and Online Resource 1.

---

## 🟠 STRONGLY RECOMMENDED

**11.** Add matching-balance table.

**12.** Add exact model equations.

**13.** Rename Figure 6 panel B to “adjusted difference-in-differences”.

**14.** Add denominator explanation for Figure 3B.

**15.** Make Figure 4 wording say “eligible cohort”, not “every inline trigger”.

**16.** Explicitly position Selvanayagam & Ghaleb 2026 as the nearest paper. ([arXiv][3])

**17.** Tone down “almost none of it is teamwork” to “we find little evidence of public agent-to-agent handoff.”

---

# 28. Submission status của mình nếu đây là manuscript hiện tại

### Scientific quality

**8.2/10**

### Novelty

**8.0/10**

### Empirical rigor

**7.8/10**

### Statistical transparency

**6.7/10**

### Reproducibility

**5.5/10**

### Presentation

**8.4/10**

### Q1 journal potential

**YES**

### Submit this exact PDF now?

**NO**

### After fixes?

**YES — realistically competitive for EMSE-level review.**

Mình đặc biệt đánh giá cao việc paper **tự giết chính hypothesis về exact anchoring** thay vì cố cherry-pick kết quả. Cái đó làm paper mature hơn rất nhiều.

---

## Một lưu ý rất quan trọng

Mình **không thấy một “fatal contradiction” kiểu số liệu A nói X nhưng kết luận Y hoàn toàn ngược nhau**.

Ngược lại, phần lớn apparent contradictions đều là dạng:

> **pipeline có thể hợp lý, nhưng manuscript chưa expose đủ intermediate definitions để reviewer tự verify.**

Đó là tin tốt, vì phần lớn có thể sửa bằng **protocol/table/definition/model specification**, không cần chạy lại toàn bộ project.

Điểm duy nhất mình muốn team **check lại trực tiếp trong code trước khi sửa prose** là:

> **RQ2 có thực sự loại same-product mid-thread triggers trước khi tính “review point gets a reply” hay không.**

Nếu câu trả lời là **không**, đây là chỗ nên sửa analysis chứ không chỉ sửa text.

Và với target EMSE, hiện journal yêu cầu editable source files, structured abstract 150–250 words, declarations đầy đủ, và có yêu cầu khá cụ thể cho figures/references; PDF hiện tại vẫn chưa đạt trạng thái submission-ready vì các placeholder còn tồn tại. ([Springer][7]) ([Springer][7])

**Bottom line:** **đừng đổi paper, đừng đổi research question, đừng chạy theo benchmark mới.** Hướng này đủ ngon. Việc cần làm bây giờ là biến nó từ một manuscript “insightful + honest” thành một manuscript **auditable, denominator-closed, estimator-explicit**. Khi ba thứ đó đóng lại, chất lượng tăng rõ rệt.

[1]: https://huggingface.co/datasets/hao-li/AIDev-7.6M "hao-li/AIDev-7.6M · Datasets at Hugging Face"
[2]: https://github.com/SAILResearch/AI_Teammates_in_SE3?utm_source=chatgpt.com "GitHub - SAILResearch/AI_Teammates_in_SE3: Replication package for \"The Rise of AI Teammates in Software Engineering (SE) 3.0: How Autonomous Coding Agents Are Reshaping SE\" · GitHub"
[3]: https://arxiv.org/abs/2608.21311?utm_source=chatgpt.com "AI-to-AI Code Reviews of GitHub Pull Requests"
[4]: https://arxiv.org/abs/2603.15911?utm_source=chatgpt.com "Human-AI Synergy in Agentic Code Review"
[5]: https://arxiv.org/abs/2607.13196?utm_source=chatgpt.com "From Human-Centric to Agentic Code Review: The Impact of Different Generations of Generative AI Technology on Review Quality"
[6]: https://huggingface.co/papers/2603.15911?utm_source=chatgpt.com "Paper page - Human-AI Synergy in Agentic Code Review"
[7]: https://link.springer.com/journal/10664/submission-guidelines "Submission guidelines | Empirical Software Engineering | Springer Nature Link"
[8]: https://emsejournal.github.io/?utm_source=chatgpt.com "Empirical Software Engineering - An International Journal"
[9]: https://library.wur.nl/WebQuery/utbrowser?issn=1573-7616&utm_source=chatgpt.com "Empirical Software Engineering"
