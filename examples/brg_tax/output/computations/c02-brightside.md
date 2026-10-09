# Brightside Design Ltd - Corporation tax computation

Period 2025-04-01 to 2026-03-31 (365 days) · as of 2026-10-09 · status: **Needs review**

| Line | £ | Rules | Authority |
|---|---:|---|---|
| Profit before tax per the accounts | £46,134.50 | CT-PROFIT-01 | CTA 2009 s35; CTA 2009 s46 |
| Add: depreciation and amortisation | £800.00 | EXP-DEP-01 | CTA 2009 s53; ITTOIA 2005 s33 |
| Add: business entertainment of non-employees | £600.00 | EXP-ENT-01 | CTA 2009 s1298; ITTOIA 2005 s45; SI 1992/3222 art 5 |
| Add: fines and penalties of the business | £60.00 | EXP-FINE-01 | CTA 2009 s54; ITTOIA 2005 s34 |
| Less: full expensing (100% FYA) on new main-rate plant | (£2,000.00) | CA-FE-01 | CAA 2001 s45S; CAA 2001 s46 |
| **Trading profit / (loss)** | **£45,594.50** | CT-PROFIT-01 | CTA 2009 s35; CTA 2009 s46 |
| **Total profits** | **£45,594.50** | CT-PROFIT-01 | CTA 2009 s35; CTA 2009 s46 |
| **Taxable total profits** | **£45,594.50** | CT-PROFIT-01 | CTA 2009 s35; CTA 2009 s46 |
| **Upper and lower limits for the period** |  | CT-ASSOC-01 | CTA 2010 s18D; CTA 2010 s18E |
| FY2025 (365 days): £45,594.50 at 19% | £8,662.96 | CT-SPR-01 | CTA 2010 s18A; CTA 2010 s18B |
| **Corporation tax liability** | **£8,662.96** | CT-PAY-01 | TMA 1970 s59D |

## Line detail

**Profit before tax per the accounts**
- Income £72,000.00 less expenses £25,865.50 from 67 ledger lines

**Add: depreciation and amortisation**
- 2026-03-31 Depreciation: £800.00

**Add: business entertainment of non-employees**
- 2025-10-09 Client dinner - pitch: £600.00

**Add: fines and penalties of the business**
- 2025-08-04 Parking penalty - company van bay: £60.00

**Less: full expensing (100% FYA) on new main-rate plant**
- Parameter `ca.ct.full_expensing_rate` (2025-26) = 100 - CAA 2001 s45S - UNVERIFIED - https://www.gov.uk/guidance/check-if-you-can-claim-full-expensing-or-the-50-first-year-allowance

**Upper and lower limits for the period**
- 1 financial year slice(s); 365 days; 0 associated companies
- FY2025: 365 days, upper limit £250,000.00, lower limit £50,000.00
- Parameter `ct.main_rate` (2025-26) = 25 - CTA 2010 s3; Finance Act 2021 s6-7 (FY charge) - UNVERIFIED - https://www.gov.uk/government/publications/rates-and-allowances-corporation-tax/rates-and-allowances-corporation-tax
- Parameter `ct.small_profits_rate` (2025-26) = 19 - CTA 2010 s18A - UNVERIFIED - https://www.gov.uk/government/publications/rates-and-allowances-corporation-tax/rates-and-allowances-corporation-tax
- Parameter `ct.upper_limit` (2025-26) = 250000 - CTA 2010 s18B(5) - UNVERIFIED - https://www.gov.uk/guidance/corporation-tax-marginal-relief
- Parameter `ct.lower_limit` (2025-26) = 50000 - CTA 2010 s18B(5) - UNVERIFIED - https://www.gov.uk/guidance/corporation-tax-marginal-relief
- Parameter `ct.mr_fraction` (2025-26) = {"num": 3, "den": 200} - CTA 2010 s18B(4) - UNVERIFIED - https://www.gov.uk/guidance/corporation-tax-marginal-relief

**FY2025 (365 days): £45,594.50 at 19%**
- Parameter `ct.main_rate` (2025-26) = 25 - CTA 2010 s3; Finance Act 2021 s6-7 (FY charge) - UNVERIFIED - https://www.gov.uk/government/publications/rates-and-allowances-corporation-tax/rates-and-allowances-corporation-tax
- Parameter `ct.small_profits_rate` (2025-26) = 19 - CTA 2010 s18A - UNVERIFIED - https://www.gov.uk/government/publications/rates-and-allowances-corporation-tax/rates-and-allowances-corporation-tax

**Corporation tax liability**
- Payable by 2027-01-01

## Capital allowances

| Allowance | £ | Rules |
|---|---:|---|
| Full expensing (100% FYA) on new main-rate plant | £2,000.00 | CA-FE-01 |

Pools carried forward: main £0.00, special £0.00

## Director's loan account

- Jordan Hale: year-end balance £9,000.00; s455 base £9,000.00 at 33.75% = **£3,037.50** (exposure, due 2027-01-01). Peak £12,000.00.
  - Beneficial loan 2025-26: averaging £182.81, alternative method £214.21; benefit £182.81, Class 1A £27.42
  - AA-464C-01: repayment £6,000.00 on 2026-04-20 matched £6,000.00 (c02-brightside:AA-464C-01:d1:2026-04-20)

## Profit extraction (planning, 2026-27)

| | Current position | Optimised |
|---|---:|---:|
| Salary per director | £12,570.00 | £100,000.00 |
| Dividends | £36,931.54 | £0.00 |
| Corporation tax | £8,662.96 | £0.00 |
| Income tax incl. dividend tax | £3,916.39 | £27,432.00 |
| Employee + employer NIC | £1,135.50 | £18,260.60 |
| Total tax | £13,714.85 | £45,692.60 |
| Net value to shareholders | £45,585.15 | £68,557.40 |

Difference: £22,972.25. Elections only (EXT-SAL-01, EXT-PEN-01, EXT-DIV-01); anti-avoidance screened (AA-GAAR-01).

## Review queue

- [open] **s464C: repayment redrawn within 30 days (Jordan Hale)** (AA-464C-01, anti_avoidance) - Was a repayment of at least the s464C amount followed within 30 days by new advances of at least that amount?
  - Proposed: {"matched": 600000}. £6,000.00 repaid on 2026-04-20 and £6,000.00 redrawn by 2026-05-10. The repayment is matched to the new advance and does not reduce the s455 charge (s464C(1)).
  - Impact: s455 on the matched amount: £2,025.00

## Alerts

- **serious** (EXT-DLA-01): Jordan Hale: loan account overdrawn £9,000.00 at 2026-03-31; s455 exposure £3,037.50 unless cleared by 2027-01-01 (84 days)
- **info** (EXT-EA-01): Employment Allowance not available: the sole director is the only employee paid above the secondary threshold.
- **info** (VAT-DEREG-01): Expected turnover £74,000.00 is at or below the deregistration threshold £88,000.00: voluntary deregistration is an option.

## Data health

- OK Trial balance balances: Debits £87,900.00, credits £87,900.00
- OK Ledger profit agrees to the trial balance: TB profit £46,134.50, ledger £46,134.50
- OK No uncategorised transactions: All transactions map to a BRG category
- OK Fixed asset register agrees to the ledger: Register additions £2,000.00, ledger fixed asset postings £2,000.00
- OK Director's loan account reconciles: DLA schedule £9,000.00 (positive = owed by the director), TB £9,000.00
- OK VAT returns agree to the ledger: 4 return(s) 2025-04-01 to 2026-03-31: box 1 £14,400.00 vs ledger output VAT £14,400.00; box 4 £1,316.00 vs ledger input VAT £1,316.00
- WARN Parameters exist and are verified: Years 2024-25, 2025-26, 2026-27: 0 of 274 values verified against GOV.UK - run `brg-tax params-update`
- OK Associated-company information present: 0 associated companies recorded

_Outputs are working papers to support professional review and are not advice until reviewed and signed off. Synthetic sample clients contain no real data._
