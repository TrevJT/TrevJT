# Undervalued-list deep dive (2026-10-14)

Owner ask: go through all 45 names on the "under" list (research_fund_screen.json), pick the top 10 by future growth, then the 3 best LEAPS fits. Answer Upbound/Rent-A-Center. **Research only — not advice. Nothing is affordable at $171 (cost ≤ cash), so all picks are paper-only.**

Method: 4 parallel web-research agents (filings, Q2 calls, news to Oct 2026), each scoring growth 1–10 and trap risk 1–10. yfinance long-dated chains after the close (`scratchpad leaps.py/chains2.py` logic, not committed). Report: claude.ai artifact "Gem Deep Dive".

## Results
- **Top 10 by growth (growth/trap):**
  - ACEL 7/3: Chicago legalized bar gaming machines on 1/1/26; Accel holds 44% of early approvals.
  - CSTL 7/3: TissueCypher volume +63%; net cash.
  - VMD 7/3: excluded from Medicare competitive bidding.
  - LWAY 7/4: kefir +24%; margin squeeze from costs is temporary.
  - REAL 7/5: GMV +22%; refinancing expected mid-November.
  - TCMD 6/3, TNC 6/3 (ERP rollout mess, robotics +56%), NGL 6/4, ORN 6/5, CMPR 5/3.
- **Just missed:** TWIN (already re-rated), BCRX (binary trial), ASAN.
- **LEAPS:** only REAL among the top 10 lists options ≥12 months out; the others stop at Feb–May 2027. The 3 LEAPS fits:
  - **BAH Jan-28 70C:** IV/RV 1.09, spread 20%, open interest 121, breakeven +17%.
  - **BRKR Dec-27 60C:** IV/RV 1.06, spread 16%, but open interest only 2; breakeven +31%.
  - **REAL Jan-28 10C:** IV/RV 1.31, spread 75%; place the bid low.
  - BAH and BRKR are ~$8.5B, so both sit in the one backtest cell that came out positive (mid-cap 12m LEAPS at mid). Paper entries are in `paper_leaps.jsonl`.
- **UPBD:** a value/yield stock, not a growth stock: ~3.7× EPS, 10% dividend, EV/EBITDA ~4.3.
  - Segments: Acima 57% of EBITDA and shrinking in 2026; stores mature; Brigit +37% but only 7%.
  - Ranked #1 only because the screen saw **zero debt**, plus rental accounting inflates GP/A.

## Screen failures caught by reading the filings (≈1/3 of the list)
- **Data errors:**
  - UPBD/REAL debt was missed. UPBD tags `DebtAndCapitalLeaseObligations`; REAL tags `ConvertibleDebtNoncurrent`.
  - **FIXED** in `research_fundamental.py`:
    - more `ltd` tags;
    - a summed `conv`+`notes` floor (d3);
    - paying interest > $1M/qtr with no debt tag now sets debt = NaN, not 0.
  - FORM mapped to Graybar's filings with FormFactor's price (CIK→ticker collision). **Not yet fixed.**
- **Pending buyouts:** WEAV ($7.40 cash), SMTI (MiMedx). Low IV on a merger name = deal pinned, not bad data.
- **Tariff refunds** (SCOTUS 2/20/26) booked in COGS inflate 2026 GP/margins: KSS, M, CRCT, CAL, OXM, KRT, PII.
- **Peak-cycle margins:** PARR. **Partial ownership:** WLKP (22.8% of OpCo). **Special distributions:** VISN ($15).
- **Shrinking businesses:** TDOC, MYGN, CRCT, SFIX, YELP, KSS, AMCX.

## Reusable insight
- The deep dive promoted names the screen ranked middling (CSTL #34, VMD #43, TCMD #31, LWAY #27). Their cheapness came from a **temporary** problem: a reimbursement rule, a cost spike, an ERP rollout.
- Screen → "why is it cheap" filter is the right pipeline. Automatable pieces:
  - 8-K item 1.01 (merger) → exclude;
  - guidance raised vs cut;
  - one-off items in COGS;
  - revenue yoy < 0 → never "cheap for growth".
- Small-cap growth names rarely have LEAPS; LEAPS availability pushes toward $2–10B names, where IV ≈ RV is more common.

## Re-run after fixes (same day)
- **Fix commit:**
  - `ltd` tags gained `DebtAndCapitalLeaseObligations`.
  - Added a summed `conv`+`notes` floor.
  - Rows paying >$1M/qtr interest with no debt tag now get debt = NaN (29,837 of 447,815 quarter rows).
  - The ticker matcher rejects symbols owned by a different live company: 335 rejected; HF coverage 2,296 → 2,200.
- **Gem signal, 12m, small caps:** IS +5.1% (t 3.1), OOS +7.4% (t 3.0), still passes BH. Before the fix: +5.4%/+7.2%. **Robust to the data fix.**
- **UPBD debt:** read as $0.99B of the true $1.42B; one tranche sits on a company-specific extension tag (`upbd:`) that this parser never reads.
- **List changes:** out FORM, TDOC, WLKP, TNC; in KD, GFF, HLF, CXM (not researched in depth; all have flat or shrinking sales).
