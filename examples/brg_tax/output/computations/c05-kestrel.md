# Kestrel Data Ltd - Corporation tax computation

Period 2025-07-01 to 2026-06-30 (365 days) · as of 2026-10-09 · status: **Needs review** · **provisional** (open review items)

| Line | £ | Rules | Authority |
|---|---:|---|---|
| Profit before tax per the accounts | £89,494.50 | CT-PROFIT-01 | CTA 2009 s35; CTA 2009 s46 |
| Add: depreciation and amortisation | £600.00 | EXP-DEP-01 | CTA 2009 s53; ITTOIA 2005 s33 |
| Less: full expensing (100% FYA) on new main-rate plant | (£1,800.00) | CA-FE-01 | CAA 2001 s45S; CAA 2001 s46 |
| **Trading profit / (loss)** | **£88,294.50** | CT-PROFIT-01 | CTA 2009 s35; CTA 2009 s46 |
| **Total profits** | **£88,294.50** | CT-PROFIT-01 | CTA 2009 s35; CTA 2009 s46 |
| **Taxable total profits** | **£88,294.50** | CT-PROFIT-01 | CTA 2009 s35; CTA 2009 s46 |
| **Upper and lower limits for the period** |  | CT-ASSOC-01, CT-FY-01 | CTA 2010 s18D; CTA 2010 s18E; CTA 2010 s8(3); CTA 2010 s8(5) |
| FY2025 (274 days): £66,281.35 at 25% | £16,570.34 | CT-RATE-01, CT-FY-01 | CTA 2010 s3; Finance Act 2021 s6; CTA 2010 s8(3); CTA 2010 s8(5) |
| Less marginal relief FY2025: (£187,671.23 - £66,281.35) x 3/200 | (£1,820.85) | CT-MR-01 | CTA 2010 s18B; CTA 2010 s18C |
| FY2026 (91 days): £22,013.15 at 25% | £5,503.29 | CT-RATE-01, CT-FY-01 | CTA 2010 s3; Finance Act 2021 s6; CTA 2010 s8(3); CTA 2010 s8(5) |
| Less marginal relief FY2026: (£62,328.77 - £22,013.15) x 3/200 | (£604.73) | CT-MR-01 | CTA 2010 s18B; CTA 2010 s18C |
| **Corporation tax liability** | **£19,648.05** | CT-PAY-01 | TMA 1970 s59D |

## Line detail

**Profit before tax per the accounts**
- Income £110,000.00 less expenses £20,505.50 from 54 ledger lines

**Add: depreciation and amortisation**
- 2026-06-30 Depreciation: £600.00

**Less: full expensing (100% FYA) on new main-rate plant**
- Parameter `ca.ct.full_expensing_rate` (2026-27) = 100 - CAA 2001 s45S - UNVERIFIED - https://www.gov.uk/guidance/check-if-you-can-claim-full-expensing-or-the-50-first-year-allowance

**Upper and lower limits for the period**
- 2 financial year slice(s); 365 days; 0 associated companies
- FY2025: 274 days, upper limit £187,671.23, lower limit £37,534.25
- FY2026: 91 days, upper limit £62,328.77, lower limit £12,465.75
- Parameter `ct.main_rate` (2025-26) = 25 - CTA 2010 s3; Finance Act 2021 s6-7 (FY charge) - UNVERIFIED - https://www.gov.uk/government/publications/rates-and-allowances-corporation-tax/rates-and-allowances-corporation-tax
- Parameter `ct.small_profits_rate` (2025-26) = 19 - CTA 2010 s18A - UNVERIFIED - https://www.gov.uk/government/publications/rates-and-allowances-corporation-tax/rates-and-allowances-corporation-tax
- Parameter `ct.upper_limit` (2025-26) = 250000 - CTA 2010 s18B(5) - UNVERIFIED - https://www.gov.uk/guidance/corporation-tax-marginal-relief
- Parameter `ct.lower_limit` (2025-26) = 50000 - CTA 2010 s18B(5) - UNVERIFIED - https://www.gov.uk/guidance/corporation-tax-marginal-relief
- Parameter `ct.mr_fraction` (2025-26) = {"num": 3, "den": 200} - CTA 2010 s18B(4) - UNVERIFIED - https://www.gov.uk/guidance/corporation-tax-marginal-relief
- Parameter `ct.main_rate` (2026-27) = 25 - CTA 2010 s3; Finance Act 2021 s6-7 (FY charge) - UNVERIFIED - https://www.gov.uk/government/publications/rates-and-allowances-corporation-tax/rates-and-allowances-corporation-tax
- Parameter `ct.small_profits_rate` (2026-27) = 19 - CTA 2010 s18A - UNVERIFIED - https://www.gov.uk/government/publications/rates-and-allowances-corporation-tax/rates-and-allowances-corporation-tax
- Parameter `ct.upper_limit` (2026-27) = 250000 - CTA 2010 s18B(5) - UNVERIFIED - https://www.gov.uk/guidance/corporation-tax-marginal-relief
- Parameter `ct.lower_limit` (2026-27) = 50000 - CTA 2010 s18B(5) - UNVERIFIED - https://www.gov.uk/guidance/corporation-tax-marginal-relief
- Parameter `ct.mr_fraction` (2026-27) = {"num": 3, "den": 200} - CTA 2010 s18B(4) - UNVERIFIED - https://www.gov.uk/guidance/corporation-tax-marginal-relief

**FY2025 (274 days): £66,281.35 at 25%**
- Parameter `ct.main_rate` (2025-26) = 25 - CTA 2010 s3; Finance Act 2021 s6-7 (FY charge) - UNVERIFIED - https://www.gov.uk/government/publications/rates-and-allowances-corporation-tax/rates-and-allowances-corporation-tax
- Parameter `ct.small_profits_rate` (2025-26) = 19 - CTA 2010 s18A - UNVERIFIED - https://www.gov.uk/government/publications/rates-and-allowances-corporation-tax/rates-and-allowances-corporation-tax
- Parameter `ct.main_rate` (2026-27) = 25 - CTA 2010 s3; Finance Act 2021 s6-7 (FY charge) - UNVERIFIED - https://www.gov.uk/government/publications/rates-and-allowances-corporation-tax/rates-and-allowances-corporation-tax
- Parameter `ct.small_profits_rate` (2026-27) = 19 - CTA 2010 s18A - UNVERIFIED - https://www.gov.uk/government/publications/rates-and-allowances-corporation-tax/rates-and-allowances-corporation-tax

**Less marginal relief FY2025: (£187,671.23 - £66,281.35) x 3/200**
- Parameter `ct.upper_limit` (2025-26) = 250000 - CTA 2010 s18B(5) - UNVERIFIED - https://www.gov.uk/guidance/corporation-tax-marginal-relief
- Parameter `ct.lower_limit` (2025-26) = 50000 - CTA 2010 s18B(5) - UNVERIFIED - https://www.gov.uk/guidance/corporation-tax-marginal-relief
- Parameter `ct.mr_fraction` (2025-26) = {"num": 3, "den": 200} - CTA 2010 s18B(4) - UNVERIFIED - https://www.gov.uk/guidance/corporation-tax-marginal-relief
- Parameter `ct.upper_limit` (2026-27) = 250000 - CTA 2010 s18B(5) - UNVERIFIED - https://www.gov.uk/guidance/corporation-tax-marginal-relief
- Parameter `ct.lower_limit` (2026-27) = 50000 - CTA 2010 s18B(5) - UNVERIFIED - https://www.gov.uk/guidance/corporation-tax-marginal-relief
- Parameter `ct.mr_fraction` (2026-27) = {"num": 3, "den": 200} - CTA 2010 s18B(4) - UNVERIFIED - https://www.gov.uk/guidance/corporation-tax-marginal-relief

**FY2026 (91 days): £22,013.15 at 25%**
- Parameter `ct.main_rate` (2025-26) = 25 - CTA 2010 s3; Finance Act 2021 s6-7 (FY charge) - UNVERIFIED - https://www.gov.uk/government/publications/rates-and-allowances-corporation-tax/rates-and-allowances-corporation-tax
- Parameter `ct.small_profits_rate` (2025-26) = 19 - CTA 2010 s18A - UNVERIFIED - https://www.gov.uk/government/publications/rates-and-allowances-corporation-tax/rates-and-allowances-corporation-tax
- Parameter `ct.main_rate` (2026-27) = 25 - CTA 2010 s3; Finance Act 2021 s6-7 (FY charge) - UNVERIFIED - https://www.gov.uk/government/publications/rates-and-allowances-corporation-tax/rates-and-allowances-corporation-tax
- Parameter `ct.small_profits_rate` (2026-27) = 19 - CTA 2010 s18A - UNVERIFIED - https://www.gov.uk/government/publications/rates-and-allowances-corporation-tax/rates-and-allowances-corporation-tax

**Less marginal relief FY2026: (£62,328.77 - £22,013.15) x 3/200**
- Parameter `ct.upper_limit` (2025-26) = 250000 - CTA 2010 s18B(5) - UNVERIFIED - https://www.gov.uk/guidance/corporation-tax-marginal-relief
- Parameter `ct.lower_limit` (2025-26) = 50000 - CTA 2010 s18B(5) - UNVERIFIED - https://www.gov.uk/guidance/corporation-tax-marginal-relief
- Parameter `ct.mr_fraction` (2025-26) = {"num": 3, "den": 200} - CTA 2010 s18B(4) - UNVERIFIED - https://www.gov.uk/guidance/corporation-tax-marginal-relief
- Parameter `ct.upper_limit` (2026-27) = 250000 - CTA 2010 s18B(5) - UNVERIFIED - https://www.gov.uk/guidance/corporation-tax-marginal-relief
- Parameter `ct.lower_limit` (2026-27) = 50000 - CTA 2010 s18B(5) - UNVERIFIED - https://www.gov.uk/guidance/corporation-tax-marginal-relief
- Parameter `ct.mr_fraction` (2026-27) = {"num": 3, "den": 200} - CTA 2010 s18B(4) - UNVERIFIED - https://www.gov.uk/guidance/corporation-tax-marginal-relief

**Corporation tax liability**
- Payable by 2027-04-01

## Capital allowances

| Allowance | £ | Rules |
|---|---:|---|
| Full expensing (100% FYA) on new main-rate plant | £1,800.00 | CA-FE-01 |

Pools carried forward: main £0.00, special £0.00

## Profit extraction (planning, 2026-27)

| | Current position | Optimised |
|---|---:|---:|
| Salary per director | £12,570.00 | £12,570.00 |
| Dividends | £68,646.45 | £68,646.45 |
| Corporation tax | £19,648.05 | £19,648.05 |
| Income tax incl. dividend tax | £15,062.36 | £15,062.36 |
| Employee + employer NIC | £1,135.50 | £1,135.50 |
| Total tax | £35,845.91 | £35,845.91 |
| Net value to shareholders | £66,154.09 | £66,154.09 |

Difference: £0.00. Elections only (EXT-SAL-01, EXT-PEN-01, EXT-DIV-01); anti-avoidance screened (AA-GAAR-01).

## Review queue

- [open] **Use of home - actual cost apportionment: Use of home office - payment to director** (EXP-HOME-02, judgment) - What part of the household costs relates to business use, and is that apportionment reasonable?
  - Proposed: {"ct": "allow"}. The claim is provisionally allowed for the business. For a company, only the employee flat rate per week is exempt for the director without evidence; any excess is at risk of being taxable earnings.
- [open] **Employment status: Halden Bank plc (via Stackline Recruitment)** (EXT-IR35-01, judgment) - Would the director be an employee of the end client if engaged directly (hypothetical contract)?
  - Proposed: {"status": "outside", "deemed_payment": 0}. No status determination is on file. No deemed employment payment is included in the computation; the review item shows the estimated Chapter 8 deemed payment and tax if the engagement is inside.
  - Impact: If inside IR35 (Chapter 8): deemed payment about £76,864.78, employer NIC £11,529.72, extra income tax and NIC for the director about £29,777.00. The deemed payment and its NIC are deductible for CT.

## Alerts

- **info** (CT-RATE-01): Planning period 2026-07-01 to 2027-06-30: no parameters yet for FY2027; the latest year's rates and limits are assumed.
- **info** (EXT-EA-01): Employment Allowance not available: the sole director is the only employee paid above the secondary threshold.

## Data health

- OK Trial balance balances: Debits £110,000.00, credits £110,000.00
- OK Ledger profit agrees to the trial balance: TB profit £89,494.50, ledger £89,494.50
- OK No uncategorised transactions: All transactions map to a BRG category
- OK Fixed asset register agrees to the ledger: Register additions £1,800.00, ledger fixed asset postings £1,800.00
- OK Director's loan account reconciles: No DLA account in the trial balance
- OK VAT returns agree to the ledger: 4 return(s) 2025-06-01 to 2026-05-31: box 1 £19,800.00 vs ledger output VAT £19,800.00; box 4 £470.00 vs ledger input VAT £470.00
- WARN Parameters exist and are verified: Years 2025-26, 2026-27: 0 of 184 values verified against GOV.UK - run `brg-tax params-update`
- OK Associated-company information present: 0 associated companies recorded

_Outputs are working papers to support professional review and are not advice until reviewed and signed off. Synthetic sample clients contain no real data._
