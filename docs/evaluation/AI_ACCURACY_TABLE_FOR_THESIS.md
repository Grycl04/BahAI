# AI accuracy tables (custom NLU model)

This document summarizes **your own trained intent classifier** (not an external chat API).  
Metrics come from **held-out test data** (20% holdout, stratified after balancing):  
`evaluation_outputs/aligned_option2_detailed_predictions.csv`.

---

## Table 1 — Overall NLU performance (all test queries)

| Metric | Value |
|--------|------:|
| **Total test queries** | 3037 |
| **Successful predictions** (expected intent = predicted intent) | 2828 |
| **Failed predictions** (wrong intent) | 209 |
| **Success rate** | **93.12%** |
| **Fail rate** (classification error) | **6.88%** |

*Fail rate* = the model picked the **wrong intent label** for that query.  
The live BahAI chatbot **adds rule-based overrides** on top of this model (not counted in this table).

CSV copy-paste: `evaluation_outputs/thesis_nlu_overall_performance.csv`

---

## Table 2 — Per-intent success and fail (%)

Each row is one **intent class**. **Success rate %** = correct ÷ test queries for that intent. **Fail %** = wrong ÷ test queries.

| Intent | Test queries | Success rate % | Fail % |
|--------|-------------:|---------------:|-------:|
| `buyer_email_verification` | 79 | 100.0% | 0.0% |
| `buyer_forgot_password` | 79 | 100.0% | 0.0% |
| `buyer_guest_access` | 79 | 100.0% | 0.0% |
| `buyer_login_google` | 79 | 100.0% | 0.0% |
| `buyer_recommendations_how` | 80 | 100.0% | 0.0% |
| `buyer_resend_otp` | 79 | 100.0% | 0.0% |
| `buyer_signup_password` | 79 | 100.0% | 0.0% |
| `buyer_signup_phone` | 80 | 100.0% | 0.0% |
| `buyer_signup_requirements` | 79 | 100.0% | 0.0% |
| `buyer_update_profile` | 80 | 100.0% | 0.0% |
| `buyer_verify_otp` | 80 | 100.0% | 0.0% |
| `schedule_viewing` | 79 | 100.0% | 0.0% |
| `thanks` | 80 | 100.0% | 0.0% |
| `buyer_messages_how` | 79 | 98.73% | 1.27% |
| `buyer_liked_saved_how` | 79 | 97.47% | 2.53% |
| `find_property_for_need` | 79 | 97.47% | 2.53% |
| `find_property_with_criteria` | 79 | 97.47% | 2.53% |
| `location_info` | 79 | 97.47% | 2.53% |
| `match_needs` | 79 | 97.47% | 2.53% |
| `buyer_kyc` | 80 | 96.25% | 3.75% |
| `find_near_landmark` | 80 | 95.0% | 5.0% |
| `find_with_feature` | 80 | 95.0% | 5.0% |
| `find_ready_property` | 79 | 94.94% | 5.06% |
| `buyer_dashboard_flow` | 80 | 93.75% | 6.25% |
| `financing` | 80 | 93.75% | 6.25% |
| `buyer_chatbot_how` | 80 | 92.5% | 7.5% |
| `process_info` | 80 | 92.5% | 7.5% |
| `buyer_logout` | 79 | 92.41% | 7.59% |
| `help` | 80 | 88.75% | 11.25% |
| `buyer_login_errors` | 80 | 87.5% | 12.5% |
| `buyer_signup` | 79 | 87.34% | 12.66% |
| `buyer_account_settings` | 79 | 86.08% | 13.92% |
| `out_of_scope` | 80 | 83.75% | 16.25% |
| `find_property` | 97 | 82.47% | 17.53% |
| `about_system` | 79 | 74.68% | 25.32% |
| `buyer_login` | 79 | 74.68% | 25.32% |
| `greeting` | 81 | 74.07% | 25.93% |
| `goodbye` | 79 | 69.62% | 30.38% |
| `TOTAL:` | 3037 | 93.12% | 6.88% |

Full table CSV: `evaluation_outputs/thesis_nlu_per_intent_success_fail.csv`

---

## Table 3 — What the model gets wrong most often (top confusion pairs)

True label → wrongly predicted as → count (held-out test):

| Expected intent | Predicted instead | Count |
|-----------------|-------------------|------:|
| goodbye | about_system | 21 |
| greeting | about_system | 18 |
| buyer_account_settings | buyer_update_profile | 11 |
| buyer_signup | buyer_logout | 9 |
| help | about_system | 9 |
| out_of_scope | about_system | 8 |
| buyer_login | buyer_logout | 8 |
| buyer_login | buyer_login_errors | 8 |
| buyer_login_errors | buyer_login | 7 |
| about_system | help | 7 |
| buyer_logout | buyer_login_errors | 6 |
| find_property | location_info | 6 |

Source: `evaluation_outputs/aligned_option2_confusion_pairs.csv`

---

## “What it cannot answer” (how to explain in your paper)

1. **Wrong intent (6.88% of test queries)** — The model still **answers**, but may run the **wrong handler** (e.g. confuses `greeting` with `about_system`). That is **classification error**, not silence.

2. **`out_of_scope` intent** — Training includes off-topic phrases; **not every possible off-topic** is in data. In held-out evaluation, `out_of_scope` had **16.25%** fail rate (see Table 2).

3. **Production system** — After NLU, `chatbot_backend.py` applies **regex / keyword overrides** and optional **Groq/OpenAI fallback** for some cases; that is **beyond** this pure NLU accuracy table.

### Intents with highest fail rate (hardest for the model)

| Intent | Success % | Fail % |
|--------|----------:|-------:|
| `goodbye` | 69.62% | 30.38% |
| `greeting` | 74.07% | 25.93% |
| `about_system` | 74.68% | 25.32% |
| `buyer_login` | 74.68% | 25.32% |
| `find_property` | 82.47% | 17.53% |
| `out_of_scope` | 83.75% | 16.25% |
| `buyer_account_settings` | 86.08% | 13.92% |
| `buyer_signup` | 87.34% | 12.66% |

---

## Files to submit with the thesis

| File | Purpose |
|------|---------|
| `evaluation_outputs/thesis_nlu_overall_performance.csv` | One-row overall success/fail % |
| `evaluation_outputs/thesis_nlu_per_intent_success_fail.csv` | Per-intent success % / fail % |
| `evaluation_outputs/aligned_option2_detailed_predictions.csv` | Every query + expected + predicted intent |
| `evaluation/build_thesis_accuracy_summary.py` | Regenerate tables after retraining |

