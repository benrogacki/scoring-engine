# Ridgeway Joinery Ltd - Corporation tax computation

Period 2025-04-01 to 2026-03-31 (365 days) · as of 2026-10-09 · status: **Needs review**

| Line | £ | Rules | Authority |
|---|---:|---|---|
| Profit before tax per the accounts | £339,944.50 | CT-PROFIT-01 | CTA 2009 s35; CTA 2009 s46 |
| Less: irrecoverable input tax posted to the VAT account (accounts correction) | (£540.00) | EXP-CAR-01 | CTA 2009 s56; CTA 2009 s57; ITTOIA 2005 s48; ITTOIA 2005 s49 |
| Add: car lease rentals - high emission cars | £891.00 | EXP-CAR-01 | CTA 2009 s56; CTA 2009 s57; ITTOIA 2005 s48; ITTOIA 2005 s49 |
| Add: depreciation and amortisation | £45,000.00 | EXP-DEP-01 | CTA 2009 s53; ITTOIA 2005 s33 |
| Add: legal and professional fees of a capital nature | £5,000.00 | EXP-LEGAL-02 | CTA 2009 s53; ITTOIA 2005 s33 |
| Less: full expensing (100% FYA) on new main-rate plant | (£120,000.00) | CA-FE-01 | CAA 2001 s45S; CAA 2001 s46 |
| Less: annual investment allowance | (£28,000.00) | CA-AIA-01 | CAA 2001 s38A; CAA 2001 s38B; CAA 2001 s51A |
| Less: wDA - main pool | (£6,660.00) | CA-WDA-01 | CAA 2001 s55; CAA 2001 s56 |
| Less: wDA - special rate pool | (£1,920.00) | CA-WDA-02 | CAA 2001 s104D |
| Less: structures and buildings allowance - Workshop extension | (£2,991.78) | CA-SBA-01 | CAA 2001 s270AA; CAA 2001 s270BA; CAA 2001 s270CA |
| **Trading profit / (loss)** | **£230,723.72** | CT-PROFIT-01 | CTA 2009 s35; CTA 2009 s46 |
| **Total profits** | **£230,723.72** | CT-PROFIT-01 | CTA 2009 s35; CTA 2009 s46 |
| **Taxable total profits** | **£230,723.72** | CT-PROFIT-01 | CTA 2009 s35; CTA 2009 s46 |
| **Upper and lower limits for the period** |  | CT-ASSOC-01 | CTA 2010 s18D; CTA 2010 s18E |
| FY2025 (365 days): £230,723.72 at 25% | £57,680.93 | CT-RATE-01 | CTA 2010 s3; Finance Act 2021 s6 |
| Less marginal relief FY2025: (£250,000.00 - £230,723.72) x 3/200 | (£289.14) | CT-MR-01 | CTA 2010 s18B; CTA 2010 s18C |
| **Corporation tax liability** | **£57,391.79** | CT-PAY-01 | TMA 1970 s59D |

## Line detail

**Profit before tax per the accounts**
- Income £900,000.00 less expenses £560,055.50 from 117 ledger lines

**Less: irrecoverable input tax posted to the VAT account (accounts correction)**
- 2025-04-05 Car lease - estate car: £45.00
- 2025-05-05 Car lease - estate car: £45.00
- 2025-06-05 Car lease - estate car: £45.00
- 2025-07-05 Car lease - estate car: £45.00
- 2025-08-05 Car lease - estate car: £45.00
- 2025-09-05 Car lease - estate car: £45.00
- 2025-10-05 Car lease - estate car: £45.00
- 2025-11-05 Car lease - estate car: £45.00
- 2025-12-05 Car lease - estate car: £45.00
- 2026-01-05 Car lease - estate car: £45.00
- 2026-02-05 Car lease - estate car: £45.00
- 2026-03-05 Car lease - estate car: £45.00

**Add: car lease rentals - high emission cars**
- 2025-04-05 Car lease - estate car: £74.25 (£45.00 input tax not recoverable - added to the cost; 15% restriction)
- 2025-05-05 Car lease - estate car: £74.25 (£45.00 input tax not recoverable - added to the cost; 15% restriction)
- 2025-06-05 Car lease - estate car: £74.25 (£45.00 input tax not recoverable - added to the cost; 15% restriction)
- 2025-07-05 Car lease - estate car: £74.25 (£45.00 input tax not recoverable - added to the cost; 15% restriction)
- 2025-08-05 Car lease - estate car: £74.25 (£45.00 input tax not recoverable - added to the cost; 15% restriction)
- 2025-09-05 Car lease - estate car: £74.25 (£45.00 input tax not recoverable - added to the cost; 15% restriction)
- 2025-10-05 Car lease - estate car: £74.25 (£45.00 input tax not recoverable - added to the cost; 15% restriction)
- 2025-11-05 Car lease - estate car: £74.25 (£45.00 input tax not recoverable - added to the cost; 15% restriction)
- 2025-12-05 Car lease - estate car: £74.25 (£45.00 input tax not recoverable - added to the cost; 15% restriction)
- 2026-01-05 Car lease - estate car: £74.25 (£45.00 input tax not recoverable - added to the cost; 15% restriction)
- 2026-02-05 Car lease - estate car: £74.25 (£45.00 input tax not recoverable - added to the cost; 15% restriction)
- 2026-03-05 Car lease - estate car: £74.25 (£45.00 input tax not recoverable - added to the cost; 15% restriction)
- Parameter `ca.car_lease_co2_threshold` (2025-26) = 50 - CTA 2009 s57(2); ITTOIA 2005 s49(2) - UNVERIFIED - https://www.gov.uk/hmrc-internal-manuals/business-income-manual/bim47714
- Parameter `ca.car_lease_disallow_pct` (2025-26) = 15 - CTA 2009 s56-58; ITTOIA 2005 s48-50 - UNVERIFIED - https://www.gov.uk/hmrc-internal-manuals/business-income-manual/bim47714

**Add: depreciation and amortisation**
- 2026-03-31 Depreciation: £45,000.00

**Add: legal and professional fees of a capital nature**
- 2025-09-22 Planning and building-contract legal fees - extension: £5,000.00

**Less: full expensing (100% FYA) on new main-rate plant**
- Parameter `ca.ct.full_expensing_rate` (2025-26) = 100 - CAA 2001 s45S - UNVERIFIED - https://www.gov.uk/guidance/check-if-you-can-claim-full-expensing-or-the-50-first-year-allowance

**Less: annual investment allowance**
- AIA limit for the period £1,000,000.00
- Parameter `ca.ct.aia_limit` (2025-26) = 1000000 - CAA 2001 s51A - UNVERIFIED - https://www.gov.uk/capital-allowances/annual-investment-allowance

**Less: wDA - main pool**
- b/f £40,000.00
- additions £0.00
- disposals £3,000.00
- rate 18% (2025-26)
- Parameter `ca.ct.wda_main_rate` (2025-26) = 18 - CAA 2001 s56(1) - UNVERIFIED - https://www.gov.uk/work-out-capital-allowances/rates-and-pools

**Less: wDA - special rate pool**
- b/f £0.00
- additions £32,000.00
- disposals £0.00
- rate 6% (2025-26)
- Parameter `ca.ct.wda_special_rate` (2025-26) = 6 - CAA 2001 s104D - UNVERIFIED - https://www.gov.uk/work-out-capital-allowances/rates-and-pools

**Less: structures and buildings allowance - Workshop extension**
- £200,000.00 x 3% x 182 days / 365
- Parameter `ca.ct.sba_rate` (2025-26) = 3 - CAA 2001 s270AA(2) - UNVERIFIED - https://www.gov.uk/guidance/claiming-capital-allowances-for-structures-and-buildings

**Upper and lower limits for the period**
- 1 financial year slice(s); 365 days; 0 associated companies
- FY2025: 365 days, upper limit £250,000.00, lower limit £50,000.00
- Parameter `ct.main_rate` (2025-26) = 25 - CTA 2010 s3; Finance Act 2021 s6-7 (FY charge) - UNVERIFIED - https://www.gov.uk/government/publications/rates-and-allowances-corporation-tax/rates-and-allowances-corporation-tax
- Parameter `ct.small_profits_rate` (2025-26) = 19 - CTA 2010 s18A - UNVERIFIED - https://www.gov.uk/government/publications/rates-and-allowances-corporation-tax/rates-and-allowances-corporation-tax
- Parameter `ct.upper_limit` (2025-26) = 250000 - CTA 2010 s18B(5) - UNVERIFIED - https://www.gov.uk/guidance/corporation-tax-marginal-relief
- Parameter `ct.lower_limit` (2025-26) = 50000 - CTA 2010 s18B(5) - UNVERIFIED - https://www.gov.uk/guidance/corporation-tax-marginal-relief
- Parameter `ct.mr_fraction` (2025-26) = {"num": 3, "den": 200} - CTA 2010 s18B(4) - UNVERIFIED - https://www.gov.uk/guidance/corporation-tax-marginal-relief

**FY2025 (365 days): £230,723.72 at 25%**
- Parameter `ct.main_rate` (2025-26) = 25 - CTA 2010 s3; Finance Act 2021 s6-7 (FY charge) - UNVERIFIED - https://www.gov.uk/government/publications/rates-and-allowances-corporation-tax/rates-and-allowances-corporation-tax
- Parameter `ct.small_profits_rate` (2025-26) = 19 - CTA 2010 s18A - UNVERIFIED - https://www.gov.uk/government/publications/rates-and-allowances-corporation-tax/rates-and-allowances-corporation-tax

**Less marginal relief FY2025: (£250,000.00 - £230,723.72) x 3/200**
- Parameter `ct.upper_limit` (2025-26) = 250000 - CTA 2010 s18B(5) - UNVERIFIED - https://www.gov.uk/guidance/corporation-tax-marginal-relief
- Parameter `ct.lower_limit` (2025-26) = 50000 - CTA 2010 s18B(5) - UNVERIFIED - https://www.gov.uk/guidance/corporation-tax-marginal-relief
- Parameter `ct.mr_fraction` (2025-26) = {"num": 3, "den": 200} - CTA 2010 s18B(4) - UNVERIFIED - https://www.gov.uk/guidance/corporation-tax-marginal-relief

**Corporation tax liability**
- Payable by 2027-01-01

## Capital allowances

| Allowance | £ | Rules |
|---|---:|---|
| Full expensing (100% FYA) on new main-rate plant | £120,000.00 | CA-FE-01 |
| Annual investment allowance | £28,000.00 | CA-AIA-01 |
| WDA - main pool | £6,660.00 | CA-WDA-01 |
| WDA - special rate pool | £1,920.00 | CA-WDA-02 |
| Structures and buildings allowance - Workshop extension | £2,991.78 | CA-SBA-01 |

Pools carried forward: main £30,340.00, special £30,080.00

## Profit extraction (planning, 2026-27)

| | Current position | Optimised |
|---|---:|---:|
| Salary per director | £12,570.00 | £1,000.00 |
| Dividends | £173,331.93 | £182,670.47 |
| Corporation tax | £57,391.79 | £60,758.75 |
| Income tax incl. dividend tax | £44,279.05 | £41,790.14 |
| Employee + employer NIC | £6,385.50 | £5,250.00 |
| Total tax | £108,056.34 | £107,798.89 |
| Net value to shareholders | £141,622.88 | £141,880.33 |

Difference: £257.45. Elections only (EXT-SAL-01, EXT-PEN-01, EXT-DIV-01); anti-avoidance screened (AA-GAAR-01).

## Review queue

- [open] **Possible R&D relief claim** (CT-RD-01, judgment) - Is a claim to R&D expenditure credit or enhanced R&D intensive support available?
  - Proposed: {"claim": "none"}. No relief is computed. A reviewer must decide whether to scope a claim.
  - Impact: No relief computed. A claim could reduce the CT liability or produce a credit.
- [open] **Settlements legislation: Alex Okafor** (AA-SETTLE-01, anti_avoidance) - Is dividend income arising to a spouse, civil partner or minor child from shares that are not an outright gift of ordinary share capital carrying full rights?
  - Proposed: {"flag": true, "tax_effect": "none_computed"}. Alex Okafor holds B shares (a separate class) and connected to d1, who works in the business and does not work in the business. Dividends to them may be taxed on the settlor (ITTOIA s624).

## Alerts

- **info** (CA-CAR-01): Company car (95g/km): a company car available to a director gives a car benefit (P11D) and Class 1A NIC - not computed in v1.
- **serious** (VAT-REC-01): Input tax of £540.00 posted in the books is not recoverable (EXP-CAR-01). Correct it on the next return within the error-correction limits (VAT Notice 700/45).

## Data health

- OK Trial balance balances: Debits £1,345,150.00, credits £1,345,150.00
- OK Ledger profit agrees to the trial balance: TB profit £339,944.50, ledger £339,944.50
- OK No uncategorised transactions: All transactions map to a BRG category
- OK Fixed asset register agrees to the ledger: Register additions £380,000.00, ledger fixed asset postings £380,000.00
- OK Director's loan account reconciles: No DLA account in the trial balance
- OK VAT returns agree to the ledger: 4 return(s) 2025-04-01 to 2026-03-31: box 1 £180,000.00 vs ledger output VAT £180,000.00; box 4 £132,980.00 vs ledger input VAT £132,980.00
- WARN Parameters exist and are verified: Years 2024-25, 2025-26, 2026-27: 0 of 274 values verified against GOV.UK - run `brg-tax params-update`
- OK Associated-company information present: 0 associated companies recorded

_Outputs are working papers to support professional review and are not advice until reviewed and signed off. Synthetic sample clients contain no real data._
