# Northgate Engineering Ltd - Corporation tax computation

Period 2025-10-01 to 2026-06-30 (273 days) · as of 2026-10-09 · status: **Needs review** · **provisional** (open review items)

| Line | £ | Rules | Authority |
|---|---:|---|---|
| Profit before tax per the accounts | £57,500.00 | CT-PROFIT-01 | CTA 2009 s35; CTA 2009 s46 |
| Add: depreciation and amortisation | £4,000.00 | EXP-DEP-01 | CTA 2009 s53; ITTOIA 2005 s33 |
| Less: annual investment allowance ⚠ provisional | (£1,500.00) | CA-AIA-01, CA-AIA-02 | CAA 2001 s38A; CAA 2001 s38B; CAA 2001 s51A; CAA 2001 s51B-51N |
| **Trading profit / (loss)** | **£60,000.00** | CT-PROFIT-01 | CTA 2009 s35; CTA 2009 s46 |
| **Total profits** | **£60,000.00** | CT-PROFIT-01 | CTA 2009 s35; CTA 2009 s46 |
| **Taxable total profits** | **£60,000.00** | CT-PROFIT-01 | CTA 2009 s35; CTA 2009 s46 |
| **Upper and lower limits for the period** |  | CT-ASSOC-01, CT-SHORT-01, CT-FY-01 | CTA 2010 s18D; CTA 2010 s18E; CTA 2010 s18D(2); CTA 2010 s8(3) |
| FY2025 (182 days): £40,000.00 at 25% | £10,000.00 | CT-RATE-01, CT-FY-01 | CTA 2010 s3; Finance Act 2021 s6; CTA 2010 s8(3); CTA 2010 s8(5) |
| Less marginal relief FY2025: (£62,328.77 - £40,000.00) x 3/200 | (£334.93) | CT-MR-01 | CTA 2010 s18B; CTA 2010 s18C |
| FY2026 (91 days): £20,000.00 at 25% | £5,000.00 | CT-RATE-01, CT-FY-01 | CTA 2010 s3; Finance Act 2021 s6; CTA 2010 s8(3); CTA 2010 s8(5) |
| Less marginal relief FY2026: (£31,164.38 - £20,000.00) x 3/200 | (£167.47) | CT-MR-01 | CTA 2010 s18B; CTA 2010 s18C |
| **Corporation tax liability** | **£14,497.60** | CT-PAY-01 | TMA 1970 s59D |

## Line detail

**Profit before tax per the accounts**
- Income £180,000.00 less expenses £122,500.00 from 68 ledger lines

**Add: depreciation and amortisation**
- 2026-06-30 Depreciation: £4,000.00

**Less: annual investment allowance**
- AIA limit for the period £747,945.21 (273 days / 365)
- Parameter `ca.ct.aia_limit` (2025-26) = 1000000 - CAA 2001 s51A - UNVERIFIED - https://www.gov.uk/capital-allowances/annual-investment-allowance
- Parameter `ca.ct.aia_limit` (2026-27) = 1000000 - CAA 2001 s51A - UNVERIFIED - https://www.gov.uk/capital-allowances/annual-investment-allowance
- Review item `c03-northgate:CA-AIA-02:aia`

**Upper and lower limits for the period**
- 2 financial year slice(s); 273 days; 1 associated company
- FY2025: 182 days, upper limit £62,328.77, lower limit £12,465.75
- FY2026: 91 days, upper limit £31,164.38, lower limit £6,232.88
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

**FY2025 (182 days): £40,000.00 at 25%**
- Parameter `ct.main_rate` (2025-26) = 25 - CTA 2010 s3; Finance Act 2021 s6-7 (FY charge) - UNVERIFIED - https://www.gov.uk/government/publications/rates-and-allowances-corporation-tax/rates-and-allowances-corporation-tax
- Parameter `ct.small_profits_rate` (2025-26) = 19 - CTA 2010 s18A - UNVERIFIED - https://www.gov.uk/government/publications/rates-and-allowances-corporation-tax/rates-and-allowances-corporation-tax
- Parameter `ct.main_rate` (2026-27) = 25 - CTA 2010 s3; Finance Act 2021 s6-7 (FY charge) - UNVERIFIED - https://www.gov.uk/government/publications/rates-and-allowances-corporation-tax/rates-and-allowances-corporation-tax
- Parameter `ct.small_profits_rate` (2026-27) = 19 - CTA 2010 s18A - UNVERIFIED - https://www.gov.uk/government/publications/rates-and-allowances-corporation-tax/rates-and-allowances-corporation-tax

**Less marginal relief FY2025: (£62,328.77 - £40,000.00) x 3/200**
- Parameter `ct.upper_limit` (2025-26) = 250000 - CTA 2010 s18B(5) - UNVERIFIED - https://www.gov.uk/guidance/corporation-tax-marginal-relief
- Parameter `ct.lower_limit` (2025-26) = 50000 - CTA 2010 s18B(5) - UNVERIFIED - https://www.gov.uk/guidance/corporation-tax-marginal-relief
- Parameter `ct.mr_fraction` (2025-26) = {"num": 3, "den": 200} - CTA 2010 s18B(4) - UNVERIFIED - https://www.gov.uk/guidance/corporation-tax-marginal-relief
- Parameter `ct.upper_limit` (2026-27) = 250000 - CTA 2010 s18B(5) - UNVERIFIED - https://www.gov.uk/guidance/corporation-tax-marginal-relief
- Parameter `ct.lower_limit` (2026-27) = 50000 - CTA 2010 s18B(5) - UNVERIFIED - https://www.gov.uk/guidance/corporation-tax-marginal-relief
- Parameter `ct.mr_fraction` (2026-27) = {"num": 3, "den": 200} - CTA 2010 s18B(4) - UNVERIFIED - https://www.gov.uk/guidance/corporation-tax-marginal-relief

**FY2026 (91 days): £20,000.00 at 25%**
- Parameter `ct.main_rate` (2025-26) = 25 - CTA 2010 s3; Finance Act 2021 s6-7 (FY charge) - UNVERIFIED - https://www.gov.uk/government/publications/rates-and-allowances-corporation-tax/rates-and-allowances-corporation-tax
- Parameter `ct.small_profits_rate` (2025-26) = 19 - CTA 2010 s18A - UNVERIFIED - https://www.gov.uk/government/publications/rates-and-allowances-corporation-tax/rates-and-allowances-corporation-tax
- Parameter `ct.main_rate` (2026-27) = 25 - CTA 2010 s3; Finance Act 2021 s6-7 (FY charge) - UNVERIFIED - https://www.gov.uk/government/publications/rates-and-allowances-corporation-tax/rates-and-allowances-corporation-tax
- Parameter `ct.small_profits_rate` (2026-27) = 19 - CTA 2010 s18A - UNVERIFIED - https://www.gov.uk/government/publications/rates-and-allowances-corporation-tax/rates-and-allowances-corporation-tax

**Less marginal relief FY2026: (£31,164.38 - £20,000.00) x 3/200**
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
| Annual investment allowance | £1,500.00 | CA-AIA-01, CA-AIA-02 |

Pools carried forward: main £0.00, special £0.00

## Profit extraction (planning, 2026-27)

| | Current position | Optimised |
|---|---:|---:|
| Salary per director | £12,570.00, £12,570.00 | £100,000.00 |
| Dividends | £60,887.30 | £0.00 |
| Corporation tax | £19,401.55 | £0.00 |
| Income tax incl. dividend tax | £6,437.88 | £54,864.00 |
| Employee + employer NIC | £0.00 | £26,021.20 |
| Total tax | £25,839.43 | £80,885.20 |
| Net value to shareholders | £79,589.42 | £137,114.80 |

Difference: £57,525.38. Elections only (EXT-SAL-01, EXT-PEN-01, EXT-DIV-01); anti-avoidance screened (AA-GAAR-01).

## Review queue

- [open] **AIA shared with an associated company?** (CA-AIA-02, judgment) - Is this company related to another (common control and shared premises or similar activities), so one AIA is shared?
  - Proposed: {"aia_allocation": "full"}. An associated company is recorded. The full AIA is provisionally allocated to this company on the assumption that the related business claims none; the reviewer must confirm the allocation.
  - Impact: Changes the AIA available and so the capital allowances claimed.

## Alerts

- **info** (CT-RATE-01): Planning period 2026-07-01 to 2027-06-30: no parameters yet for FY2027; the latest year's rates and limits are assumed.

## Data health

- OK Trial balance balances: Debits £260,000.00, credits £260,000.00
- OK Ledger profit agrees to the trial balance: TB profit £57,500.00, ledger £57,500.00
- OK No uncategorised transactions: All transactions map to a BRG category
- OK Fixed asset register agrees to the ledger: Register additions £1,500.00, ledger fixed asset postings £1,500.00
- OK Director's loan account reconciles: No DLA account in the trial balance
- OK VAT returns agree to the ledger: 3 return(s) 2025-10-01 to 2026-06-30: box 1 £36,000.00 vs ledger output VAT £36,000.00; box 4 £15,048.00 vs ledger input VAT £15,048.00
- WARN Parameters exist and are verified: Years 2025-26, 2026-27: 0 of 184 values verified against GOV.UK - run `brg-tax params-update`
- OK Associated-company information present: 1 associated company recorded

_Outputs are working papers to support professional review and are not advice until reviewed and signed off. Synthetic sample clients contain no real data._
